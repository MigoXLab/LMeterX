"""Tests for stop reason validation."""

import time
from unittest.mock import Mock

from engine.core import FieldMapping, GlobalConfig, StreamMetrics
from engine.request_processor import APIClient, StreamProcessor


class FakeResponse:
    """Fake response for testing."""

    def __init__(self, payload):
        """Initialize FakeResponse."""
        self.status_code = 200
        self._payload = payload
        self.success = Mock()
        self.failure = Mock()

    def __enter__(self):
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit context manager."""
        return False

    def json(self):
        """Return the JSON payload."""
        return self._payload


class FakeClient:
    """Fake client for testing."""

    def __init__(self, response):
        """Initialize FakeClient."""
        self.response = response

    def post(self, *args, **kwargs):
        """Simulate a POST request."""
        return self.response


def test_stream_stop_reason_error_returns_failure_message():
    """Test that stream processing returns failure when stop_reason is error."""
    field_mapping = FieldMapping(stream_prefix="data:", data_format="json")
    metrics = StreamMetrics()

    should_break, error_message, _ = StreamProcessor.process_stream_chunk(
        b'data: {"delta": {"stop_reason": "error"}}',
        field_mapping,
        time.perf_counter(),
        metrics,
        Mock(),
        api_type="openai-chat",
    )

    assert should_break is True
    assert "stop_reason is error" in error_message


def test_non_stream_stop_reason_error_marks_response_failure(monkeypatch):
    """Test that non-stream processing marks response failure on error stop_reason."""
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_failure_event",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "engine.request_processor.EventManager.fire_metric_event",
        lambda *args, **kwargs: None,
    )

    config = GlobalConfig()
    config.api_type = "claude-chat"
    config.stream_mode = False
    response = FakeResponse(
        {
            "content": [{"type": "text", "text": "partial"}],
            "stop_reason": "error",
        }
    )
    api_client = APIClient(config, Mock())

    reasoning_content, content, usage = api_client.handle_non_stream_request(
        FakeClient(response),
        {"json": {"messages": []}, "name": "chat"},
        time.perf_counter(),
    )

    assert reasoning_content == ""
    assert content == ""
    assert usage["completion_tokens"] == 0
    response.failure.assert_called_once()
    response.success.assert_not_called()
    assert "stop_reason is error" in response.failure.call_args.args[0]
