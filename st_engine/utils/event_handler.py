"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Optional

from locust import events

from utils.logger import logger


# === EVENT MANAGEMENT ===
class EventManager:
    """Manages Locust events and metrics."""

    @staticmethod
    def fire_failure_event(
        name: str = "failure",
        response_time: float = 0.0,
        response_length: int = 0,
        exception: Optional[Exception] = None,
    ) -> None:
        """Fire failure events with proper Locust event format."""
        # Enhanced safety checks for all parameters
        try:
            response_time = (
                float(response_time)
                if isinstance(response_time, (int, float)) and response_time >= 0
                else 0.0
            )
        except Exception:
            response_time = 0.0

        try:
            response_length = (
                int(response_length)
                if isinstance(response_length, (int, float)) and response_length >= 0
                else 0
            )
        except Exception:
            response_length = 0

        exception_info = exception or Exception("Request failed")

        try:
            # Use the correct Locust event API based on version
            if hasattr(events, "request_failure"):
                # Legacy Locust version
                events.request_failure.fire(
                    request_type="POST",
                    name=name,
                    response_time=int(response_time),
                    response_length=int(response_length),
                    exception=exception_info,
                )
            else:
                # Modern Locust version
                events.request.fire(
                    request_type="POST",
                    name=name,
                    response_time=int(response_time),
                    response_length=int(response_length),
                    exception=exception_info,
                    success=False,
                )
        except Exception as e:
            # Never crash on metrics emission
            logger.warning(f"Failed to fire failure event: {e}")

    @staticmethod
    def fire_metric_event(
        name: str, response_time: float, response_length: int
    ) -> None:
        """Fire metric events."""
        # Enhanced safety checks for all parameters
        try:
            response_time = (
                float(response_time)
                if isinstance(response_time, (int, float)) and response_time >= 0
                else 0.0
            )
        except Exception:
            response_time = 0.0

        try:
            response_length = (
                int(response_length)
                if isinstance(response_length, (int, float)) and response_length >= 0
                else 0
            )
        except Exception:
            response_length = 0

        name = str(name) if name is not None else "metric"

        try:
            # Use the correct Locust event API based on version
            if hasattr(events, "request_success"):
                # Legacy Locust version
                events.request_success.fire(
                    request_type="metric",
                    name=name,
                    response_time=int(response_time),
                    response_length=int(response_length),
                )
            else:
                # Modern Locust version
                events.request.fire(
                    request_type="metric",
                    name=name,
                    response_time=int(response_time),
                    response_length=int(response_length),
                    success=True,
                )
        except Exception as e:
            logger.warning(f"Failed to fire metric event '{name}': {e}")
