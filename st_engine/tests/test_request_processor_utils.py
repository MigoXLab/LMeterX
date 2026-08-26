"""Tests for request processor utils and memory release logic."""

import inspect
import time
from unittest.mock import MagicMock, Mock, patch

from engine.core import GlobalConfig
from engine.request_processor import APIClient
from utils.error_handler import ErrorResponse, _safe_repr_truncate
from utils.event_handler import EventManager


# =====================================================================
# Tests for _safe_repr_truncate
# =====================================================================
def test_safe_repr_truncate_string():
    """Test truncate logic for string objects."""
    short_str = "hello"
    assert _safe_repr_truncate(short_str, limit=10) == "hello"

    long_str = "abcdefghij"  # len = 10
    assert _safe_repr_truncate(long_str, limit=5) == "abcde... (truncated)"


def test_safe_repr_truncate_dict():
    """Test truncate logic for dictionary objects."""
    # 1. Simple small dict
    small_dict = {"a": 1, "b": 2}
    res = _safe_repr_truncate(small_dict, limit=50)
    assert "'a': 1" in res
    assert "'b': 2" in res

    # 2. Dict with extremely long value
    long_val = "x" * 200
    long_val_dict = {"a": long_val}
    res = _safe_repr_truncate(long_val_dict, limit=150)
    assert "..." in res  # Inside the value
    assert len(res) < 150

    # 3. Dict overshooting total limit
    large_dict = {f"key_{i}": "value" for i in range(100)}
    res = _safe_repr_truncate(large_dict, limit=50)
    assert res.endswith("...}")
    assert len(res) <= 50


def test_safe_repr_truncate_list_tuple():
    """Test truncate logic for list and tuple objects."""
    lst = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    res = _safe_repr_truncate(lst, limit=10)
    assert "truncated" in res

    tup = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    res = _safe_repr_truncate(tup, limit=10)
    assert "truncated" in res


def test_safe_repr_truncate_unrepresentable():
    """Test fallback when object representation raises Exception."""

    class BadRepr:
        def __repr__(self):
            raise ValueError("bad repr")

    assert _safe_repr_truncate(BadRepr()) == "<unrepresentable>"


# =====================================================================
# Tests for request_kwargs payload release (memory optimization)
# =====================================================================
class FakeResponse:
    """Fake response context manager for testing."""

    def __init__(self):
        """Initialize FakeResponse."""
        self.status_code = 200
        self.headers = {}

        # Verify request_kwargs is popped before response.success() completes
        def success_side_effect():
            frame = inspect.currentframe()
            while frame is not None and "request_kwargs" not in frame.f_locals:
                frame = frame.f_back
            if frame is None:
                raise AssertionError("request_kwargs not found")
            req_kwargs = frame.f_locals["request_kwargs"]
            assert "json" not in req_kwargs
            assert "data" not in req_kwargs

        self.success = Mock(side_effect=success_side_effect)
        self.failure = Mock()

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit context manager."""
        return False

    def json(self):
        """Return fake response json."""
        return {"choices": [{"message": {"content": "response text"}}]}


class FakeClient:
    """Fake HTTP client to verify that post() popped json and data."""

    def __init__(self, response):
        """Initialize FakeClient."""
        self.response = response
        self.called_with_kwargs = None

    def post(self, url, **kwargs):
        """Mock post request."""
        self.called_with_kwargs = kwargs
        return self.response


@patch(
    "engine.request_processor.EventManager.fire_failure_event",
    lambda *args, **kwargs: None,
)
@patch(
    "engine.request_processor.EventManager.fire_metric_event",
    lambda *args, **kwargs: None,
)
def test_handle_non_stream_request_releases_payload(monkeypatch):
    """Verify handle_non_stream_request pops json and data."""
    config = GlobalConfig()
    config.api_type = "openai-chat"
    config.stream_mode = False
    config.api_path = "/v1/chat/completions"

    api_client = APIClient(config, Mock())

    fake_response = FakeResponse()
    fake_client = FakeClient(fake_response)

    request_kwargs = {
        "json": {
            "model": "test",
            "messages": [{"role": "user", "content": "hi" * 100}],
        },
        "data": "some_raw_data",
        "headers": {},
    }

    # Execute request
    _, _, usage = api_client.handle_non_stream_request(
        fake_client,
        request_kwargs,
        time.perf_counter(),
    )

    # Note that in APIClient, the original request_kwargs passed to
    # handle_non_stream_request is a base_request_kwargs dictionary.
    # The success_side_effect assertion verifies that it is mutated.
    fake_response.success.assert_called_once()
    assert usage.request_succeeded is True


@patch(
    "engine.request_processor.EventManager.fire_metric_event",
    lambda *args, **kwargs: None,
)
def test_non_stream_finalization_failure_keeps_positive_usage_unsuccessful():
    """Provider usage must not make a request successful after finalization fails."""
    config = GlobalConfig()
    config.api_type = "openai-chat"
    config.stream_mode = False
    config.api_path = "/v1/chat/completions"
    response = FakeResponse()
    response.json = Mock(
        return_value={
            "choices": [{"message": {"content": "partial"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 9,
                "completion_tokens": 2,
                "total_tokens": 11,
            },
        }
    )
    response.success = Mock(side_effect=RuntimeError("finalization failed"))

    _, _, usage = APIClient(config, MagicMock()).handle_non_stream_request(
        FakeClient(response),
        {"json": {"messages": []}, "name": "/v1/chat/completions"},
        time.perf_counter(),
    )

    assert usage == {
        "prompt_tokens": 9,
        "completion_tokens": 2,
        "total_tokens": 11,
    }
    assert usage.request_succeeded is False
    response.failure.assert_called_once()


def _make_stream_client(lines):
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.iter_lines.return_value = iter(lines)

    client = MagicMock()
    client.post.return_value.__enter__.return_value = response
    client.post.return_value.__exit__.return_value = False
    return client, response


def _stream_request_kwargs():
    return {
        "json": {"messages": [{"role": "user", "content": "hi"}]},
        "headers": {"Content-Type": "application/json"},
        "catch_response": True,
        "name": "/v1/chat/completions",
        "verify": False,
    }


def test_stream_finalization_error_marks_response_failure(monkeypatch):
    """A completion-metric error must not turn an incomplete result into success."""
    config = GlobalConfig()
    config.api_path = "/v1/chat/completions"
    config.stream_mode = True
    config.api_type = "openai-chat"
    api_client = APIClient(config, MagicMock())
    client, response = _make_stream_client([b"data: [DONE]"])

    monkeypatch.setattr(
        EventManager,
        "fire_metric_event",
        Mock(side_effect=RuntimeError("metric failure")),
    )
    fallback_failure_event = Mock()
    monkeypatch.setattr(EventManager, "fire_failure_event", fallback_failure_event)

    result = api_client.handle_stream_request(
        client, _stream_request_kwargs(), time.perf_counter()
    )

    assert result == ("", "", {"completion_tokens": 0, "total_tokens": 0})
    assert result[2].request_succeeded is False
    response.success.assert_not_called()
    response.failure.assert_called_once()
    fallback_failure_event.assert_not_called()


def test_stream_without_terminal_marker_marks_response_failure(monkeypatch):
    """A clean HTTP EOF without the protocol terminal marker is incomplete."""
    config = GlobalConfig()
    config.api_path = "/v1/chat/completions"
    config.stream_mode = True
    config.api_type = "openai-chat"
    api_client = APIClient(config, MagicMock())
    client, response = _make_stream_client([])
    fallback_failure_event = Mock()
    monkeypatch.setattr(EventManager, "fire_failure_event", fallback_failure_event)

    result = api_client.handle_stream_request(
        client, _stream_request_kwargs(), time.perf_counter()
    )

    assert result == ("", "", {"completion_tokens": 0, "total_tokens": 0})
    assert result[2].request_succeeded is False
    response.success.assert_not_called()
    response.failure.assert_called_once_with(
        "Stream ended without terminal marker"
        " | Context: {'api_path': '/v1/chat/completions'}"
    )
    fallback_failure_event.assert_not_called()


def test_error_response_does_not_emit_duplicate_failure_event(monkeypatch):
    """response.failure owns Locust reporting when a response context exists."""
    task_logger = MagicMock()
    handler = ErrorResponse(GlobalConfig(), task_logger)
    response = MagicMock()
    fallback_failure_event = Mock()
    monkeypatch.setattr(EventManager, "fire_failure_event", fallback_failure_event)

    handler._handle_general_exception_event(
        "network error", response=response, response_time=123
    )

    response.failure.assert_called_once_with("network error")
    fallback_failure_event.assert_not_called()


def test_error_log_includes_response_traceparent(monkeypatch):
    """Error logs include a sanitized traceparent response header."""
    task_logger = MagicMock()
    handler = ErrorResponse(GlobalConfig(), task_logger)
    response = MagicMock()
    response.headers = {"traceparent": "00-trace-id-span-id-01\r\n"}
    monkeypatch.setattr(EventManager, "fire_failure_event", Mock())

    handler._handle_general_exception_event("request failed", response=response)

    error_log = task_logger.error.call_args.args[0]
    assert error_log == "request failed | traceparent: 00-trace-id-span-id-01"


def test_error_log_omits_missing_traceparent(monkeypatch):
    """Error logs remain unchanged when traceparent is absent."""
    task_logger = MagicMock()
    handler = ErrorResponse(GlobalConfig(), task_logger)
    response = MagicMock()
    response.headers = {"content-type": "application/json"}
    monkeypatch.setattr(EventManager, "fire_failure_event", Mock())

    handler._handle_general_exception_event("request failed", response=response)

    assert task_logger.error.call_args.args[0] == "request failed"


def test_error_response_emits_fallback_event_without_response(monkeypatch):
    """Failures outside a response context still need an explicit Locust event."""
    handler = ErrorResponse(GlobalConfig(), MagicMock())
    fallback_failure_event = Mock()
    monkeypatch.setattr(EventManager, "fire_failure_event", fallback_failure_event)

    handler._handle_general_exception_event(
        "setup error", response=None, response_time=123
    )

    fallback_failure_event.assert_called_once()
