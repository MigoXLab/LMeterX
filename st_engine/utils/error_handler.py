"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import time
from typing import Any, Dict, Optional

from config.base import DEFAULT_STREAM_IDLE_TIMEOUT
from engine.core import GlobalConfig
from utils.event_handler import EventManager

_PAYLOAD_LOG_LIMIT = 500


def _safe_repr_truncate(obj: Any, limit: int = _PAYLOAD_LOG_LIMIT) -> str:
    """Return a truncated repr without allocating the full string first.

    For large objects (e.g. dicts containing base64 images), calling repr()
    then slicing still creates the entire multi-MB string in memory.  This
    implementation builds a bounded preview by iterating dict keys and
    truncating individual values, avoiding the full allocation.
    """
    if isinstance(obj, str):
        if len(obj) <= limit:
            return obj
        return obj[:limit] + "... (truncated)"

    try:
        if isinstance(obj, dict):
            parts = ["{"]
            length = 1
            for key, value in obj.items():
                val_repr = repr(value)
                if len(val_repr) > 80:
                    val_repr = val_repr[:80] + "..."
                entry = f"{repr(key)}: {val_repr}, "
                if length + len(entry) > limit:
                    parts.append("...")
                    break
                parts.append(entry)
                length += len(entry)
            parts.append("}")
            preview = "".join(parts)
        elif isinstance(obj, (list, tuple)):
            preview = repr(obj)
            if len(preview) > limit:
                preview = preview[:limit]
        else:
            preview = repr(obj)
            if len(preview) > limit:
                preview = preview[:limit]
    except Exception:
        preview = "<unrepresentable>"
    if len(preview) >= limit:
        return preview[:limit] + "... (truncated)"
    return preview


# === ERROR HANDLING ===
class ErrorResponse:
    """Centralized error handling for various scenarios."""

    def __init__(self, config: GlobalConfig, task_logger):
        """Store configuration and task-specific logger for later use."""
        self.config = config
        self.task_logger = task_logger

    @staticmethod
    def _handle_json_error(json_data: Dict[str, Any]) -> Optional[str]:
        """Check if JSON data contains error conditions."""
        if not isinstance(json_data, dict):
            return None

        try:
            # Check for various error indicators
            code = json_data.get("code", 0)
            error = json_data.get("error", "")
            output_object = json_data.get("object", "")
            event_error = json_data.get("event", "")

            # API-specific error checks
            error_msg = json_data.get("error", {})
            if isinstance(error_msg, dict):
                error_type = error_msg.get("type", "")
                error_message = error_msg.get("message", "")
                if error_type or error_message:
                    return f"API error - type: {error_type}, message: {error_message}"

            if isinstance(code, (int, float)) and code < 0:
                return f"Response contains error code: {json_data}"

            if error and str(error).strip():
                return f"Response contains error: {json_data}"

            if output_object == "error":
                return f"Response object type is error: {json_data}"

            if event_error == "error":
                return f"Response event type is error: {json_data}"

            return None
        except Exception as e:
            # Enhanced logging for parsing errors
            return f"Error parsing response JSON for error checking: {e}"

    def _handle_general_exception_event(
        self,
        error_msg: str,
        response=None,
        response_time: float = 0,
        additional_context: Optional[Dict[str, Any]] = None,
        req_id: Optional[str] = None,
        payload_data: Any = None,
        request_name: Optional[str] = None,
    ) -> None:
        """Centralized handler for logging exceptions during requests."""
        # Enhanced error logging with context
        context_info = ""
        if additional_context:
            context_info = f" | Context: {additional_context}"

        full_error_msg = f"{error_msg}{context_info}"

        log_msg = full_error_msg
        if req_id:
            log_msg = f"[{req_id}] {log_msg}"
        traceparent = self._extract_traceparent(response)
        if traceparent:
            log_msg += f" | traceparent: {traceparent}"
        if response_time > 0:
            log_msg += f" | Request elapsed: {response_time:.2f} ms"
        if payload_data is not None:
            payload_str = _safe_repr_truncate(payload_data, 500)
            log_msg += f" | Payload: {payload_str}"

        self.task_logger.error(log_msg)

        failure_reported_by_response = False
        if response is not None and hasattr(response, "failure"):
            try:
                response.failure(full_error_msg)
                # Locust's ResponseContextManager reports this failure when
                # its context exits. Firing another global request event here
                # would count the same failed request twice.
                failure_reported_by_response = True
            except Exception as failure_err:
                self.task_logger.warning(
                    f"Failed to mark response as failure: {failure_err}"
                )

        if not failure_reported_by_response:
            try:
                EventManager.fire_failure_event(
                    name=request_name or self.config.api_path or "failure",
                    response_time=response_time,
                    response_length=0,
                    exception=Exception(full_error_msg),
                )
            except Exception as fire_err:
                # Never let event firing escalate; log and continue
                self.task_logger.warning(f"Failed to emit failure event: {fire_err}")

    def _handle_status_code_error(
        self,
        response,
        start_time: float = 0,
        request_name: str = "failure",
        req_id: Optional[str] = None,
        payload_data: Any = None,
    ) -> bool:
        """Handle HTTP status code errors."""
        # Add safety checks for response object
        if response is None:
            error_msg = "Response object is None"
            response_time = (
                (time.perf_counter() - start_time) * 1000 if start_time > 0 else 0
            )
            self._handle_general_exception_event(
                error_msg=error_msg,
                response=None,
                response_time=response_time,
                req_id=req_id,
                payload_data=payload_data,
                request_name=request_name,
            )
            return True

        # Safely get status code with fallback
        try:
            # Locust converts requests.RequestException instances into a
            # LocustResponse with status_code=0 and stores the original
            # exception on ``response.error``.  Zero is an internal sentinel,
            # not an HTTP status code, so report the transport failure before
            # applying normal HTTP status handling.
            transport_error = getattr(response, "error", None)
            if isinstance(transport_error, BaseException) or (
                isinstance(transport_error, str) and transport_error.strip()
            ):
                response_time = (
                    (time.perf_counter() - start_time) * 1000 if start_time > 0 else 0
                )
                error_type = type(transport_error).__name__
                if isinstance(transport_error, str):
                    error_type = "RequestException"
                error_detail = str(transport_error).strip() or repr(transport_error)
                error_msg = (
                    "Network error (no HTTP response) - "
                    f"{error_type}: {error_detail}"
                )
                self._handle_general_exception_event(
                    error_msg=error_msg,
                    response=response,
                    response_time=response_time,
                    req_id=req_id,
                    payload_data=payload_data,
                    request_name=request_name,
                )
                return True

            status_code = getattr(response, "status_code", None)
            if status_code is None:
                error_msg = "Response object has no status_code attribute"
                response_time = (
                    (time.perf_counter() - start_time) * 1000 if start_time > 0 else 0
                )
                self._handle_general_exception_event(
                    error_msg=error_msg,
                    response=response,
                    response_time=response_time,
                    req_id=req_id,
                    payload_data=payload_data,
                    request_name=request_name,
                )
                return True

            if not isinstance(status_code, int) or not 200 <= status_code < 300:
                # Safely get response text
                response_text = getattr(
                    response, "text", "Unable to retrieve response text"
                )
                error_msg = f"Request failed with status_code {status_code}. Response: {response_text}"
                response_time = (
                    (time.perf_counter() - start_time) * 1000 if start_time > 0 else 0
                )
                self._handle_general_exception_event(
                    error_msg=error_msg,
                    response=response,
                    response_time=response_time,
                    req_id=req_id,
                    payload_data=payload_data,
                    request_name=request_name,
                )
                return True
        except Exception as e:
            error_msg = f"Error checking response status: {e}"
            response_time = (
                (time.perf_counter() - start_time) * 1000 if start_time > 0 else 0
            )
            self._handle_general_exception_event(
                error_msg=error_msg,
                response=response,
                response_time=response_time,
                req_id=req_id,
                payload_data=payload_data,
                request_name=request_name,
            )
            return True

        return False

    def _handle_stream_error(
        self,
        e: OSError,
        response,
        start_time: float,
        request_name: str,
        req_id: Optional[str] = None,
        payload_data: Any = None,
    ) -> None:
        """Handle specific stream processing errors."""
        error_msg = str(e)
        response_time = (time.perf_counter() - start_time) * 1000
        traceparent = self._extract_traceparent(response)

        if "Read timed out" in error_msg or "timed out" in error_msg.lower():
            error_msg = (
                f"[Client idle timeout] No response data received from server for "
                f"{DEFAULT_STREAM_IDLE_TIMEOUT} seconds, client triggered fallback "
                f"timeout mechanism. Original error: {error_msg}"
            )
            warning_msg = error_msg
            if traceparent:
                warning_msg = f"{warning_msg} | traceparent: {traceparent}"
            self.task_logger.warning(warning_msg)
        elif "Connection" in error_msg:
            error_msg = f"Network connection error: {error_msg}"
        else:
            error_msg = f"Stream processing network error: {error_msg}"

        self._handle_general_exception_event(
            error_msg=error_msg,
            response=response,
            response_time=response_time,
            req_id=req_id,
            payload_data=payload_data,
            request_name=request_name,
        )

    @staticmethod
    def _extract_traceparent(response) -> Optional[str]:
        """Return a log-safe traceparent response header when present."""
        headers = getattr(response, "headers", None)
        if not headers:
            return None
        try:
            traceparent = headers.get("traceparent")
        except (AttributeError, TypeError):
            return None
        if not traceparent:
            return None
        return str(traceparent).replace("\r", "").replace("\n", "")
