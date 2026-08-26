"""Regression tests for Locust transport-error reporting."""

import time
from unittest.mock import MagicMock, Mock

import requests

from engine.core import GlobalConfig
from service.llm_task_service import _failed_requests_message
from utils.error_handler import ErrorResponse
from utils.event_handler import EventManager
from utils.stats_manager import StatsManager


def test_locust_status_zero_reports_original_request_exception(monkeypatch):
    """status_code=0 must be described as transport failure, not HTTP 0."""
    task_logger = MagicMock()
    handler = ErrorResponse(GlobalConfig(), task_logger)
    response = MagicMock()
    response.status_code = 0
    response.error = requests.exceptions.ConnectTimeout("connect timed out")
    fallback_failure_event = Mock()
    monkeypatch.setattr(EventManager, "fire_failure_event", fallback_failure_event)

    handled = handler._handle_status_code_error(
        response,
        start_time=time.perf_counter() - 0.01,
        request_name="/v1/chat/completions",
        req_id="deadbeef",
    )

    assert handled is True
    logged_message = task_logger.error.call_args.args[0]
    assert "Network error (no HTTP response)" in logged_message
    assert "ConnectTimeout: connect timed out" in logged_message
    assert "status_code 0" not in logged_message
    response.failure.assert_called_once()
    fallback_failure_event.assert_not_called()


def test_real_http_error_keeps_status_code_reporting():
    """Normal HTTP responses continue through the HTTP status branch."""
    task_logger = MagicMock()
    handler = ErrorResponse(GlobalConfig(), task_logger)
    response = MagicMock()
    response.status_code = 503
    response.error = None
    response.text = "upstream unavailable"

    assert handler._handle_status_code_error(response) is True

    logged_message = task_logger.error.call_args.args[0]
    assert "status_code 503" in logged_message
    assert "Network error" not in logged_message


def test_network_error_is_carried_into_result_summary():
    stats_error = MagicMock()
    stats_error.method = "POST"
    stats_error.name = "/v1/chat/completions"
    stats_error.error = (
        "Network error (no HTTP response) - ConnectTimeout: connect timed out"
    )
    stats_error.occurrences = 5
    environment_stats = MagicMock()
    environment_stats.errors = {"key": stats_error}

    request_errors = StatsManager().get_locust_errors(environment_stats)

    assert request_errors == [
        {
            "method": "POST",
            "name": "/v1/chat/completions",
            "error": (
                "Network error (no HTTP response) - "
                "ConnectTimeout: connect timed out"
            ),
            "occurrences": 5,
            "category": "network_error",
        }
    ]
    summary = _failed_requests_message("task-1", {"request_errors": request_errors})
    assert summary.startswith("Network error (no HTTP response): 5 request(s)")
    assert "ConnectTimeout: connect timed out" in summary
