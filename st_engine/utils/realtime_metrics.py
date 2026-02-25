"""
Shared real-time metrics collection utilities for Locust load tests.

This module provides functions that are shared between the LLM API locustfile
and the common API locustfile to avoid code duplication.

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import tempfile
import time
from typing import Any, Dict

import gevent

from utils.logger import logger

# Default interval (seconds) used for short tests or when duration is unknown.
_DEFAULT_METRICS_INTERVAL = 2
# Maximum number of data points we want to store per task.
_MAX_METRICS_DATA_POINTS = 1080


def calc_metrics_interval(*, is_llm: bool = False) -> int:
    """Calculate an adaptive metrics collection interval based on test duration and load mode.

    Common (business) API strategy:
    - Short tests (≤5 min): 2 s
    - Medium tests (5–30 min): 5 s
    - Long tests (30–120 min): 10 s
    - Very long tests (>2 h): 30 s

    LLM API strategy (larger intervals because LLM requests are long-running
    streaming connections — single-request latency is typically seconds to
    tens of seconds, so very frequent snapshots add noise without value):
    - Short tests (≤5 min): 5 s
    - Medium tests (5–30 min): 10 s
    - Long tests (30–120 min): 15 s
    - Very long tests (>2 h): 30 s

    In stepped mode the interval is capped at 5 s (common) / 8 s (LLM) to
    preserve step-transition visibility.

    Args:
        is_llm: When *True*, use the wider LLM interval strategy.

    Returns the interval in seconds.
    """
    load_mode = os.environ.get("LOAD_MODE", "fixed")
    duration_str = os.environ.get("TASK_DURATION", "")

    default_interval = 5 if is_llm else _DEFAULT_METRICS_INTERVAL

    if not duration_str:
        return default_interval

    try:
        duration = int(duration_str)
    except (ValueError, TypeError):
        return default_interval

    if duration <= 0:
        return default_interval

    if load_mode == "stepped":
        if is_llm:
            # LLM stepped: wider intervals but still show transitions
            if duration <= 300:
                return 5
            elif duration <= 1800:
                return 6
            else:
                return 8
        # Common API stepped
        if duration <= 300:
            return 2
        elif duration <= 1800:
            return 3
        else:
            return 5

    if is_llm:
        # LLM fixed concurrency — wider intervals
        if duration <= 300:  # ≤ 5 min
            return 5
        elif duration <= 1800:  # 5 – 30 min
            return 10
        elif duration <= 7200:  # 30 min – 2 h
            return 15
        else:  # > 2 h
            return 30

    # Common API fixed concurrency — original intervals
    if duration <= 300:  # ≤ 5 min
        return 2
    elif duration <= 1800:  # 5 – 30 min
        return 5
    elif duration <= 7200:  # 30 min – 2 h
        return 10
    else:  # > 2 h
        return 30


def get_realtime_metrics_path(task_id: str) -> str:
    """Return the path for the real-time metrics JSONL file."""
    return os.path.join(
        tempfile.gettempdir(), "locust_result", task_id, "realtime_metrics.jsonl"
    )


def collect_realtime_snapshot(
    environment, *, include_entries: bool = False
) -> Dict[str, Any]:
    """Collect a single snapshot of current metrics from Locust stats.

    Args:
        environment: Locust environment with ``stats`` and ``runner``.
        include_entries: When *True*, iterate over per-name stat entries and
            add a ``metrics`` dict mapping each entry name to its
            ``avg_response_time``, ``current_rps`` and ``current_fail_per_sec``.
            This is used by LLM API tests which register multiple named
            metrics (e.g. ``Total_time``, ``Time_to_first_reasoning_token``).
    """
    total = environment.stats.total
    runner = environment.runner
    current_users = runner.user_count if runner else 0
    now = time.time()

    snapshot: Dict[str, Any] = {
        "timestamp": now,
        "current_users": current_users,
        "current_rps": round(total.current_rps, 2) if total else 0,
        "current_fail_per_sec": round(total.current_fail_per_sec, 2) if total else 0,
        "avg_response_time": round(total.avg_response_time, 2) if total else 0,
        "min_response_time": round(total.min_response_time or 0, 2) if total else 0,
        "max_response_time": round(total.max_response_time or 0, 2) if total else 0,
        "median_response_time": (
            round(total.median_response_time or 0, 2) if total else 0
        ),
        "p95_response_time": (
            round(total.get_response_time_percentile(0.95) or 0, 2) if total else 0
        ),
        "total_requests": total.num_requests if total else 0,
        "total_failures": total.num_failures if total else 0,
    }

    if include_entries:
        metrics: Dict[str, Dict[str, Any]] = {}
        for (name, _method), entry in environment.stats.entries.items():
            if name in ("Aggregated", "Total") or entry.num_requests == 0:
                continue
            metrics[name] = {
                "avg_response_time": round(entry.avg_response_time, 2),
                "current_rps": round(entry.current_rps, 2),
                "current_fail_per_sec": round(entry.current_fail_per_sec, 2),
            }
        snapshot["metrics"] = metrics

    return snapshot


def realtime_metrics_greenlet(
    environment, *, include_entries: bool = False, is_llm: bool = False
):
    """Background greenlet that periodically writes real-time metrics to a JSONL file.

    The collection interval is dynamically adjusted based on the test duration
    and load mode (via ``calc_metrics_interval``), so long-running stability
    tests produce far fewer data points than short benchmark runs.

    Args:
        include_entries: Forwarded to ``collect_realtime_snapshot`` to add
            per-metric detail (used by LLM API tests).
        is_llm: When *True*, use wider collection intervals suitable for
            LLM API tests where single-request latency is much higher.
    """
    task_id = getattr(environment.parsed_options, "task_id", "") or os.environ.get(
        "TASK_ID", "unknown"
    )
    metrics_path = get_realtime_metrics_path(task_id)
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    task_logger = logger.bind(task_id=task_id)

    interval = calc_metrics_interval(is_llm=is_llm)
    task_logger.info(
        f"Real-time metrics writer started -> {metrics_path} (interval={interval}s)"
    )

    while True:
        try:
            gevent.sleep(interval)
            snapshot = collect_realtime_snapshot(
                environment, include_entries=include_entries
            )
            with open(metrics_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot) + "\n")
        except gevent.GreenletExit:
            break
        except Exception as e:  # pragma: no cover
            task_logger.debug(f"Realtime metrics write error: {e}")
