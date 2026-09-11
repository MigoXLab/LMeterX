"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import threading
import time
from typing import Dict, List, Optional, Tuple

import requests

from utils.engine_identity import resolve_engine_id
from utils.logger import logger

# VictoriaMetrics endpoint (configurable via environment variable)
_VM_URL: str = os.environ.get("VICTORIA_METRICS_URL", "http://localhost:8428")
_IMPORT_PATH: str = "/api/v1/import/prometheus"
_PUSH_TIMEOUT: float = 3.0  # seconds
_PUSH_MAX_ATTEMPTS: int = 2  # initial request plus one retry
_PUSH_RETRY_BACKOFF: float = 0.2  # seconds


# requests.Session is not guaranteed to be thread-safe. Keep one persistent
# session per calling thread (or greenlet when threading.local is monkey-patched
# by gevent) so normal pushes reuse TCP connections without sharing mutable
# session state across concurrent collectors.
_SESSION_LOCAL = threading.local()


# Engine identity
ENGINE_ID: str = resolve_engine_id()


def _get_session() -> requests.Session:
    """Return the persistent requests session for the current execution context."""
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _SESSION_LOCAL.session = session
    return session


def _discard_session(session: requests.Session) -> None:
    """Close and forget a session after a connection-level failure."""
    try:
        session.close()
    except Exception as error:  # pragma: no cover - defensive cleanup
        logger.debug(
            "Failed to close VM push session: "
            f"type={type(error).__name__}, error={error!r}"
        )
    finally:
        if getattr(_SESSION_LOCAL, "session", None) is session:
            delattr(_SESSION_LOCAL, "session")


def _extract_errno(error: BaseException) -> Optional[int]:
    """Find a nested OS errno inside requests/urllib3 exception wrappers."""
    pending = [error]
    visited = set()

    while pending:
        current = pending.pop()
        current_id = id(current)
        if current_id in visited:
            continue
        visited.add(current_id)

        error_number = getattr(current, "errno", None)
        if error_number is not None:
            return error_number

        for attribute in ("__cause__", "__context__", "reason"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException):
                pending.append(nested)

        for argument in getattr(current, "args", ()):
            if isinstance(argument, BaseException):
                pending.append(argument)

    return None


def _log_connection_error(
    error: requests.exceptions.ConnectionError,
    *,
    url: str,
    attempt: int,
) -> None:
    """Log the original connection exception and retry state."""
    will_retry = attempt < _PUSH_MAX_ATTEMPTS
    logger.warning(
        "VM push connection error: "
        f"type={type(error).__name__}, "
        f"errno={_extract_errno(error)!r}, "
        f"url={url}, "
        f"attempt={attempt}/{_PUSH_MAX_ATTEMPTS}, "
        f"will_retry={will_retry}, "
        f"error={error!r}"
    )


def push_metrics(
    lines: List[str],
    *,
    extra_labels: Optional[Dict[str, str]] = None,
) -> bool:
    """Push Prometheus-format metric lines to VictoriaMetrics.

    Each element of *lines* should be a single Prometheus text line, e.g.::

        'engine_cpu_percent{engine_id="e1"} 45.2 1700000000000'

    Args:
        lines: List of Prometheus exposition lines.
        extra_labels: Not used currently but reserved for future label injection.

    Returns:
        True on success, False on failure (never raises).
    """
    if not lines:
        return True

    url = f"{_VM_URL}{_IMPORT_PATH}"
    body = "\n".join(lines) + "\n"

    for attempt in range(1, _PUSH_MAX_ATTEMPTS + 1):
        session = None
        try:
            session = _get_session()
            resp = session.post(
                url,
                data=body.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=_PUSH_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.warning(
                    f"VM push failed: HTTP {resp.status_code} - {resp.text[:200]}"
                )
                return False
            return True
        except requests.exceptions.ConnectionError as error:
            _log_connection_error(error, url=url, attempt=attempt)
            if session is not None:
                _discard_session(session)
            if attempt >= _PUSH_MAX_ATTEMPTS:
                return False
            time.sleep(_PUSH_RETRY_BACKOFF)
        except Exception as error:
            logger.warning(
                "VM push error: "
                f"type={type(error).__name__}, url={url}, error={error!r}"
            )
            return False

    return False  # pragma: no cover - the loop always returns on its final attempt


def _escape_label_value(value: str) -> str:
    """Escape special characters in a Prometheus label value."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def build_metric_line(
    name: str,
    value: float,
    labels: Dict[str, str],
    timestamp_ms: Optional[int] = None,
) -> str:
    """Build a single Prometheus exposition line.

    Args:
        name: Metric name (e.g. ``engine_cpu_percent``).
        value: Metric value.
        labels: Dict of label key-value pairs.
        timestamp_ms: Optional Unix timestamp in **milliseconds**.
            If not provided, the current time is used.

    Returns:
        A formatted Prometheus metric line.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    label_parts = ",".join(
        f'{k}="{_escape_label_value(str(v))}"' for k, v in sorted(labels.items())
    )
    label_str = f"{{{label_parts}}}" if label_parts else ""
    return f"{name}{label_str} {value} {timestamp_ms}"


def push_realtime_perf_metrics(
    task_id: str,
    task_type: str,
    snapshot: Dict,
    timestamp_ms: Optional[int] = None,
) -> bool:
    """Push a single real-time performance snapshot to VictoriaMetrics.

    This replaces JSONL file writing and MySQL batch insertion for
    real-time performance metrics.

    Args:
        task_id: The task identifier.
        task_type: Either ``"llm"`` or ``"http"``.
        snapshot: A metrics snapshot dict as returned by
            ``collect_realtime_snapshot()``.
        timestamp_ms: Optional explicit timestamp in milliseconds.

    Returns:
        True on success, False on failure.
    """
    if timestamp_ms is None:
        ts = snapshot.get("timestamp")
        timestamp_ms = int(ts * 1000) if ts else int(time.time() * 1000)

    base_labels = {
        "task_id": task_id,
        "task_type": task_type,
        "engine_id": ENGINE_ID,
    }

    # List of (metric_name, snapshot_key, default_value)
    metric_defs: List[Tuple[str, str, float]] = [
        ("lmeterx_current_users", "current_users", 0),
        ("lmeterx_current_rps", "current_rps", 0),
        ("lmeterx_current_fail_per_sec", "current_fail_per_sec", 0),
        ("lmeterx_avg_response_time", "avg_response_time", 0),
        ("lmeterx_min_response_time", "min_response_time", 0),
        ("lmeterx_max_response_time", "max_response_time", 0),
        ("lmeterx_median_response_time", "median_response_time", 0),
        ("lmeterx_p95_response_time", "p95_response_time", 0),
        ("lmeterx_total_requests", "total_requests", 0),
        ("lmeterx_total_failures", "total_failures", 0),
    ]

    lines: List[str] = []
    for metric_name, key, default in metric_defs:
        val = float(snapshot.get(key, default))
        lines.append(build_metric_line(metric_name, val, base_labels, timestamp_ms))

    # Handle per-entry detail metrics (LLM specific)
    per_entry_metrics = snapshot.get("metrics")
    if per_entry_metrics and isinstance(per_entry_metrics, dict):
        for entry_name, entry_data in per_entry_metrics.items():
            entry_labels = {**base_labels, "metric_name": entry_name}
            for sub_key in ("avg_response_time", "current_rps", "current_fail_per_sec"):
                val = float(entry_data.get(sub_key, 0))
                lines.append(
                    build_metric_line(
                        f"lmeterx_entry_{sub_key}",
                        val,
                        entry_labels,
                        timestamp_ms,
                    )
                )

    return push_metrics(lines)
