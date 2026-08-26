"""Tests for HTTP request timeout mechanism.

Verifies that:
1. Timeout constants are correctly defined
2. Stream requests use (connect_timeout=600, read_timeout=1800)
3. Non-stream requests use (connect_timeout=600, read_timeout=7200)
4. Timeout errors produce WARNING-level log with correct message
5. Non-timeout connection errors are not misidentified as timeouts
"""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from config.base import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_NON_STREAM_TIMEOUT,
    DEFAULT_STREAM_IDLE_TIMEOUT,
)
from engine.core import GlobalConfig
from engine.request_processor import APIClient


# =====================================================================
# 1. Constant values
# =====================================================================
class TestTimeoutConstants:
    """Verify timeout constants are set to expected values."""

    def test_connect_timeout_value(self):
        assert DEFAULT_CONNECT_TIMEOUT == 600

    def test_stream_idle_timeout_value(self):
        assert DEFAULT_STREAM_IDLE_TIMEOUT == 1800

    def test_non_stream_timeout_value(self):
        assert DEFAULT_NON_STREAM_TIMEOUT == 7200


# =====================================================================
# 2. Timeout passed to client.post()
# =====================================================================
class TestTimeoutApplied:
    """Verify that timeout tuple is correctly passed to the HTTP client."""

    @pytest.fixture
    def api_client(self):
        config = GlobalConfig()
        config.api_path = "/v1/chat/completions"
        config.stream_mode = True
        config.api_type = "openai-chat"
        task_logger = MagicMock()
        return APIClient(config, task_logger)

    def test_stream_request_timeout_tuple(self, api_client):
        """Stream request should use (600, 1800) timeout."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter([b"data: [DONE]"])
        mock_client.post.return_value.__enter__ = Mock(return_value=mock_response)
        mock_client.post.return_value.__exit__ = Mock(return_value=False)

        base_kwargs = {
            "json": {"messages": [{"role": "user", "content": "hi"}]},
            "headers": {"Content-Type": "application/json"},
            "catch_response": True,
            "name": "/v1/chat/completions",
            "verify": False,
        }

        api_client.handle_stream_request(mock_client, base_kwargs, time.perf_counter())

        # Verify client.post was called with timeout
        call_kwargs = mock_client.post.call_args
        # call_args is (args, kwargs) — post(api_path, **request_kwargs)
        passed_kwargs = call_kwargs[1] if call_kwargs[1] else {}
        # If positional + keyword mixed, check kwargs
        if "timeout" in passed_kwargs:
            assert passed_kwargs["timeout"] == (600, 1800)
        else:
            # timeout may be in the merged kwargs passed as **request_kwargs
            # Let's check all call arguments
            all_kwargs = (
                call_kwargs.kwargs if hasattr(call_kwargs, "kwargs") else call_kwargs[1]
            )
            assert all_kwargs.get("timeout") == (600, 1800)

    def test_non_stream_request_timeout_tuple(self, api_client):
        """Non-stream request should use (600, 7200) timeout."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]
        }
        mock_client.post.return_value.__enter__ = Mock(return_value=mock_response)
        mock_client.post.return_value.__exit__ = Mock(return_value=False)

        base_kwargs = {
            "json": {"messages": [{"role": "user", "content": "hi"}]},
            "headers": {"Content-Type": "application/json"},
            "catch_response": True,
            "name": "/v1/chat/completions",
            "verify": False,
        }

        api_client.handle_non_stream_request(
            mock_client, base_kwargs, time.perf_counter()
        )

        call_kwargs = mock_client.post.call_args
        passed_kwargs = call_kwargs[1] if call_kwargs[1] else {}
        if "timeout" in passed_kwargs:
            assert passed_kwargs["timeout"] == (600, 7200)
        else:
            all_kwargs = (
                call_kwargs.kwargs if hasattr(call_kwargs, "kwargs") else call_kwargs[1]
            )
            assert all_kwargs.get("timeout") == (600, 7200)


# =====================================================================
# 3. Timeout error handling and WARNING log
# =====================================================================
class TestTimeoutErrorHandling:
    """Verify timeout errors produce correct WARNING log messages."""

    @pytest.fixture
    def api_client(self):
        config = GlobalConfig()
        config.api_path = "/v1/chat/completions"
        config.stream_mode = True
        config.api_type = "openai-chat"
        task_logger = MagicMock()
        return APIClient(config, task_logger), task_logger

    def test_stream_read_timeout_logs_warning(self, api_client):
        """When stream read times out, should log WARNING with idle timeout info."""
        client_obj, task_logger = api_client
        mock_client = MagicMock()

        # Simulate ReadTimeout during connection
        mock_client.post.side_effect = requests.exceptions.Timeout("Read timed out")

        base_kwargs = {
            "json": {"messages": [{"role": "user", "content": "hi"}]},
            "headers": {"Content-Type": "application/json"},
            "catch_response": True,
            "name": "/v1/chat/completions",
            "verify": False,
        }

        result = client_obj.handle_stream_request(
            mock_client, base_kwargs, time.perf_counter()
        )

        # Should return empty result (not crash)
        assert result == ("", "", {"completion_tokens": 0, "total_tokens": 0})

        # Should log WARNING (not just ERROR)
        task_logger.warning.assert_called_once()
        warning_msg = task_logger.warning.call_args[0][0]
        assert "[Client idle timeout]" in warning_msg
        assert "1800 seconds" in warning_msg
        assert "Read timed out" in warning_msg

    def test_non_stream_timeout_logs_warning(self, api_client):
        """When non-stream request times out, should log WARNING with 7200s info."""
        client_obj, task_logger = api_client
        mock_client = MagicMock()

        mock_client.post.side_effect = requests.exceptions.Timeout(
            "HTTPSConnectionPool: Read timed out. (read timeout=7200)"
        )

        base_kwargs = {
            "json": {"messages": [{"role": "user", "content": "hi"}]},
            "headers": {"Content-Type": "application/json"},
            "catch_response": True,
            "name": "/v1/chat/completions",
            "verify": False,
        }

        result = client_obj.handle_non_stream_request(
            mock_client, base_kwargs, time.perf_counter()
        )

        assert result == ("", "", {"completion_tokens": 0, "total_tokens": 0})

        task_logger.warning.assert_called_once()
        warning_msg = task_logger.warning.call_args[0][0]
        assert "[Client timeout]" in warning_msg
        assert "7200 seconds" in warning_msg

    def test_connection_error_not_flagged_as_timeout(self, api_client):
        """Pure connection errors should NOT be flagged as timeout."""
        client_obj, task_logger = api_client
        mock_client = MagicMock()

        mock_client.post.side_effect = requests.exceptions.ConnectionError(
            "Connection refused: [Errno 111]"
        )

        base_kwargs = {
            "json": {"messages": [{"role": "user", "content": "hi"}]},
            "headers": {"Content-Type": "application/json"},
            "catch_response": True,
            "name": "/v1/chat/completions",
            "verify": False,
        }

        result = client_obj.handle_stream_request(
            mock_client, base_kwargs, time.perf_counter()
        )

        assert result == ("", "", {"completion_tokens": 0, "total_tokens": 0})
        # Should NOT log warning for non-timeout connection errors
        task_logger.warning.assert_not_called()


# =====================================================================
# 4. Stream error handler in error_handler.py
# =====================================================================
class TestErrorHandlerStreamTimeout:
    """Verify _handle_stream_error correctly identifies timeout vs other errors."""

    @pytest.fixture
    def error_handler(self):
        from utils.error_handler import ErrorResponse

        config = GlobalConfig()
        config.api_path = "/v1/chat/completions"
        task_logger = MagicMock()
        return ErrorResponse(config, task_logger), task_logger

    def test_read_timed_out_produces_warning(self, error_handler):
        """OSError with 'Read timed out' should trigger WARNING log."""
        handler, task_logger = error_handler
        error = OSError("Read timed out. (read timeout=1800)")
        mock_response = MagicMock()
        mock_response.headers = {}

        handler._handle_stream_error(
            error, mock_response, time.perf_counter(), "/v1/chat/completions"
        )

        task_logger.warning.assert_called_once()
        warning_msg = task_logger.warning.call_args[0][0]
        assert "[Client idle timeout]" in warning_msg
        assert "1800 seconds" in warning_msg
        assert "fallback timeout mechanism" in warning_msg
        error_log = task_logger.error.call_args[0][0]
        assert "traceparent" not in error_log

    def test_read_timeout_warning_includes_traceparent(self, error_handler):
        """Read timeout warning should include a log-safe traceparent when present."""
        handler, task_logger = error_handler
        error = OSError("Read timed out. (read timeout=1800)")
        mock_response = MagicMock()
        mock_response.headers = {
            "traceparent": (
                "00-4bf92f3577b34da6a3ce929d0e0e4736-" "00f067aa0ba902b7-01\r\n"
            )
        }

        handler._handle_stream_error(
            error, mock_response, time.perf_counter(), "/v1/chat/completions"
        )

        warning_msg = task_logger.warning.call_args[0][0]
        assert (
            "traceparent: "
            "00-4bf92f3577b34da6a3ce929d0e0e4736-"
            "00f067aa0ba902b7-01" in warning_msg
        )
        assert "\r" not in warning_msg
        assert "\n" not in warning_msg

    def test_connection_reset_not_flagged_as_timeout(self, error_handler):
        """OSError with 'Connection reset' should NOT trigger timeout warning."""
        handler, task_logger = error_handler
        error = OSError("Connection reset by peer")
        mock_response = MagicMock()
        mock_response.headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }

        handler._handle_stream_error(
            error, mock_response, time.perf_counter(), "/v1/chat/completions"
        )

        # Should NOT call warning for connection reset
        task_logger.warning.assert_not_called()
        # Should still log error via _handle_general_exception_event
        task_logger.error.assert_called_once()
        error_log = task_logger.error.call_args[0][0]
        assert "Network connection error: Connection reset by peer" in error_log
        assert " | Request elapsed: " in error_log
        assert error_log.endswith(" ms")
        assert (
            "traceparent: "
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" in error_log
        )
