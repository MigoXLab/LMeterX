"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import time
from typing import Any, Dict, Optional

from config.base import DEFAULT_TIMEOUT, HTTP_OK
from engine.core import GlobalConfig
from utils.event_handler import EventManager


# === ERROR HANDLING ===
class ErrorResponse:
    """Centralized error handling for various scenarios."""

    def __init__(self, config: GlobalConfig, task_logger):
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

            if code < 0:
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
    ) -> None:
        """Centralized handler for logging exceptions during requests."""
        # Enhanced error logging with context
        context_info = ""
        if additional_context:
            context_info = f" | Context: {additional_context}"

        full_error_msg = f"{error_msg}{context_info}"
        self.task_logger.error(full_error_msg)

        if response is not None and hasattr(response, "failure"):
            try:
                response.failure(full_error_msg)
            except Exception as failure_err:
                self.task_logger.warning(
                    f"Failed to mark response as failure: {failure_err}"
                )

        try:
            EventManager.fire_failure_event(
                name="failure",
                response_time=response_time,
                response_length=0,
                exception=Exception(full_error_msg),
            )
        except Exception as fire_err:
            # Never let event firing escalate; log and continue
            self.task_logger.warning(f"Failed to emit failure event: {fire_err}")

    def _handle_status_code_error(
        self, response, start_time: float = 0, request_name: str = "failure"
    ) -> bool:
        """Handle HTTP status code errors."""
        # Add safety checks for response object
        if response is None:
            error_msg = "Response object is None"
            response_time = (time.time() - start_time) * 1000 if start_time > 0 else 0
            self._handle_general_exception_event(
                error_msg=error_msg,
                response=None,
                response_time=response_time,
                additional_context={
                    "api_path": self.config.api_path,
                    "request_name": request_name,
                },
            )
            return True

        # Safely get status code with fallback
        try:
            status_code = getattr(response, "status_code", None)
            if status_code is None:
                error_msg = "Response object has no status_code attribute"
                response_time = (
                    (time.time() - start_time) * 1000 if start_time > 0 else 0
                )
                self._handle_general_exception_event(
                    error_msg=error_msg,
                    response=response,
                    response_time=response_time,
                    additional_context={
                        "api_path": self.config.api_path,
                        "request_name": request_name,
                    },
                )
                return True

            if status_code != HTTP_OK:
                # Safely get response text
                response_text = getattr(
                    response, "text", "Unable to retrieve response text"
                )
                error_msg = f"Request failed with status_code {status_code}. Response: {response_text}"
                response_time = (
                    (time.time() - start_time) * 1000 if start_time > 0 else 0
                )
                self._handle_general_exception_event(
                    error_msg=error_msg,
                    response=response,
                    response_time=response_time,
                    additional_context={
                        "api_path": self.config.api_path,
                        "request_name": request_name,
                    },
                )
                return True
        except Exception as e:
            error_msg = f"Error checking response status: {e}"
            response_time = (time.time() - start_time) * 1000 if start_time > 0 else 0
            self._handle_general_exception_event(
                error_msg=error_msg,
                response=response,
                response_time=response_time,
                additional_context={
                    "api_path": self.config.api_path,
                    "request_name": request_name,
                },
            )
            return True

        return False

    def _handle_stream_error(
        self, e: OSError, response, start_time: float, request_name: str
    ) -> None:
        """Handle specific stream processing errors."""
        error_msg = str(e)
        response_time = (time.time() - start_time) * 1000

        if "Read timed out" in error_msg:
            self.task_logger.error(
                f"Stream request timeout (current timeout: {DEFAULT_TIMEOUT} seconds): {error_msg}."
            )
        elif "Connection" in error_msg:
            self.task_logger.error(f"Network connection error: {error_msg}.")
        else:
            self.task_logger.error(f"Stream processing network error: {error_msg}")

        self._handle_general_exception_event(
            error_msg=error_msg,
            response=response,
            response_time=response_time,
            additional_context={
                "api_path": self.config.api_path,
                "request_name": request_name,
            },
        )
