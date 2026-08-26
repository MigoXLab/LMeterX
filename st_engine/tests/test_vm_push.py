from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
import requests

from utils import vm_push


def _response(status_code=204, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


@pytest.fixture(autouse=True)
def clear_persistent_session():
    """Prevent a persistent session from leaking between unit tests."""
    session = getattr(vm_push._SESSION_LOCAL, "session", None)
    if session is not None:
        vm_push._discard_session(session)
    yield
    session = getattr(vm_push._SESSION_LOCAL, "session", None)
    if session is not None:
        vm_push._discard_session(session)


def test_push_metrics_reuses_session_between_successful_pushes():
    session = MagicMock(spec=requests.Session)
    session.post.return_value = _response()

    with patch("utils.vm_push.requests.Session", return_value=session) as constructor:
        first_result = vm_push.push_metrics(["metric_name 1 1700000000000"])
        second_result = vm_push.push_metrics(["metric_name 2 1700000002000"])
        vm_push._discard_session(session)

    assert first_result is True
    assert second_result is True
    constructor.assert_called_once_with()
    assert session.post.call_count == 2
    session.close.assert_called_once_with()


def test_push_metrics_retries_connection_error_once_then_succeeds():
    first_session = MagicMock(spec=requests.Session)
    second_session = MagicMock(spec=requests.Session)
    connection_error = requests.exceptions.ConnectionError("connection reset")
    first_session.post.side_effect = connection_error
    second_session.post.return_value = _response()

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "utils.vm_push.requests.Session",
                side_effect=[first_session, second_session],
            )
        )
        sleep = stack.enter_context(patch("utils.vm_push.time.sleep"))
        warning = stack.enter_context(patch("utils.vm_push.logger.warning"))
        result = vm_push.push_metrics(["metric_name 1 1700000000000"])

    assert result is True
    first_session.close.assert_called_once_with()
    second_session.close.assert_not_called()
    sleep.assert_called_once_with(vm_push._PUSH_RETRY_BACKOFF)
    warning.assert_called_once()
    message = warning.call_args.args[0]
    assert "type=ConnectionError" in message
    assert "attempt=1/2" in message
    assert "will_retry=True" in message
    assert "connection reset" in message


def test_push_metrics_logs_errno_when_both_attempts_fail():
    sessions = [MagicMock(spec=requests.Session), MagicMock(spec=requests.Session)]
    errors = []
    for error_number in (99, 111):
        underlying_error = OSError(error_number, "socket failure")
        connection_error = requests.exceptions.ConnectionError("push failed")
        connection_error.__cause__ = underlying_error
        errors.append(connection_error)

    sessions[0].post.side_effect = errors[0]
    sessions[1].post.side_effect = errors[1]

    with ExitStack() as stack:
        stack.enter_context(
            patch("utils.vm_push.requests.Session", side_effect=sessions)
        )
        sleep = stack.enter_context(patch("utils.vm_push.time.sleep"))
        warning = stack.enter_context(patch("utils.vm_push.logger.warning"))
        result = vm_push.push_metrics(["metric_name 1 1700000000000"])

    assert result is False
    sessions[0].close.assert_called_once_with()
    sessions[1].close.assert_called_once_with()
    sleep.assert_called_once_with(vm_push._PUSH_RETRY_BACKOFF)
    assert warning.call_count == 2
    first_message = warning.call_args_list[0].args[0]
    final_message = warning.call_args_list[1].args[0]
    assert "errno=99" in first_message
    assert "attempt=1/2" in first_message
    assert "will_retry=True" in first_message
    assert "errno=111" in final_message
    assert "attempt=2/2" in final_message
    assert "will_retry=False" in final_message


def test_push_metrics_does_not_retry_http_error_response():
    session = MagicMock(spec=requests.Session)
    session.post.return_value = _response(503, "temporarily unavailable")

    with ExitStack() as stack:
        stack.enter_context(
            patch("utils.vm_push.requests.Session", return_value=session)
        )
        sleep = stack.enter_context(patch("utils.vm_push.time.sleep"))
        result = vm_push.push_metrics(["metric_name 1 1700000000000"])

    assert result is False
    session.post.assert_called_once()
    session.close.assert_not_called()
    sleep.assert_not_called()
