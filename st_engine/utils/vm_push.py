"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import socket
import time
from typing import Dict, List, Optional, Tuple

import requests

from utils.logger import logger

# VictoriaMetrics endpoint (configurable via environment variable)
_VM_URL: str = os.environ.get("VICTORIA_METRICS_URL", "http://localhost:8428")
_IMPORT_PATH: str = "/api/v1/import/prometheus"
_PUSH_TIMEOUT: float = 3.0  # seconds


def _resolve_engine_id() -> str:
    """Resolve engine identity from environment or system hostname.

    Priority:
        1. ENGINE_ID env var (Docker Compose / manual override)
        2. ENGINE_POD_NAME env var (Kubernetes)
        3. HOSTNAME env var (Docker container hostname — unique per container)
        4. socket.gethostname() — reliable fallback for local development

    When falling back to HOSTNAME or socket.gethostname(), the value is
    prefixed with ``engine-`` so that auto-generated IDs are easily
    recognisable in the monitoring dashboard.
    """
    # Explicit ENGINE_ID always wins (user-controlled)
    explicit_id = os.environ.get("ENGINE_ID")
    if explicit_id:
        return explicit_id

    # Kubernetes pod name (already contains a meaningful identifier)
    pod_name = os.environ.get("ENGINE_POD_NAME")
    if pod_name:
        return pod_name

    # Fallback: use hostname with a readable prefix
    hostname = os.environ.get("HOSTNAME") or socket.gethostname()
    return f"engine-{hostname}" if hostname else "engine-local"


# Engine identity
ENGINE_ID: str = _resolve_engine_id()


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

    try:
        resp = requests.post(
            url,
            data=body.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=_PUSH_TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.debug(f"VM push failed: HTTP {resp.status_code} - {resp.text[:200]}")
            return False
        return True
    except requests.exceptions.ConnectionError:
        logger.debug("VM push connection error (VictoriaMetrics may not be available)")
        return False
    except Exception as e:
        logger.debug(f"VM push error: {e}")
        return False


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
        task_type: Either ``"llm"`` or ``"common"``.
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
