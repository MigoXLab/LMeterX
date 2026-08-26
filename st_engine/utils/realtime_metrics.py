"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import time
from collections import Counter
from math import ceil
from typing import Any, Dict

import gevent

from utils.logger import logger
from utils.vm_push import push_realtime_perf_metrics

# Default interval (seconds) used for short tests or when duration is unknown.
_DEFAULT_METRICS_INTERVAL = 2


def calc_metrics_interval() -> int:
    """Calculate an adaptive metrics collection interval based on test duration and load mode.

    Returns the interval in seconds.
    """
    load_mode = os.environ.get("LOAD_MODE", "fixed")
    duration_str = os.environ.get("TASK_DURATION", "")

    if not duration_str:
        return _DEFAULT_METRICS_INTERVAL

    try:
        duration = int(duration_str)
    except (ValueError, TypeError):
        return _DEFAULT_METRICS_INTERVAL

    if duration <= 0:
        return _DEFAULT_METRICS_INTERVAL

    if load_mode == "stepped":
        # Stepped mode: tighter intervals to preserve step-transition visibility
        if duration <= 1800:  # ≤ 30 min
            return 2
        elif duration <= 3600:  # 30 – 60 min
            return 3
        else:  # > 60 min
            return 5

    # Fixed concurrency — unified intervals for both HTTP & LLM API
    if duration <= 600:  # ≤ 10 min
        return 2
    elif duration <= 1800:  # 10 – 30 min
        return 3
    elif duration <= 7200:  # 30min – 2h
        return 5
    else:  # > 2h
        return 10


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
    runner = environment.runner
    current_users = runner.user_count if runner else 0
    now = time.time()

    # Custom LLM timings/tokens are emitted as request_type="metric" so Locust
    # can aggregate them across workers. They also enter stats.total, however,
    # and must be excluded from real request RPS/count/latency calculations.
    request_entries = [
        entry
        for (_name, method), entry in environment.stats.entries.items()
        if method != "metric"
    ]
    total_requests = sum(entry.num_requests for entry in request_entries)
    total_failures = sum(entry.num_failures for entry in request_entries)
    total_response_time = sum(
        getattr(entry, "total_response_time", 0) for entry in request_entries
    )
    response_times: Counter = Counter()
    for entry in request_entries:
        response_times.update(getattr(entry, "response_times", {}) or {})

    def percentile(percent: float) -> float:
        if total_requests <= 0 or not response_times:
            return 0
        target = max(1, ceil(total_requests * percent))
        seen = 0
        for response_time in sorted(response_times):
            seen += response_times[response_time]
            if seen >= target:
                return float(response_time)
        return float(max(response_times))

    min_values = [
        entry.min_response_time
        for entry in request_entries
        if entry.min_response_time is not None
    ]
    max_values = [
        entry.max_response_time
        for entry in request_entries
        if entry.max_response_time is not None
    ]

    snapshot: Dict[str, Any] = {
        "timestamp": now,
        "current_users": current_users,
        "current_rps": round(sum(entry.current_rps for entry in request_entries), 2),
        "current_fail_per_sec": round(
            sum(entry.current_fail_per_sec for entry in request_entries), 2
        ),
        "avg_response_time": round(
            total_response_time / total_requests if total_requests else 0, 2
        ),
        "min_response_time": round(min(min_values) if min_values else 0, 2),
        "max_response_time": round(max(max_values) if max_values else 0, 2),
        "median_response_time": round(percentile(0.5), 2),
        "p95_response_time": round(percentile(0.95), 2),
        "total_requests": total_requests,
        "total_failures": total_failures,
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


def realtime_metrics_greenlet(environment, *, include_entries: bool = False):
    """Background greenlet that periodically collects real-time metrics and
    pushes them to VictoriaMetrics.

    The collection interval is dynamically adjusted based on the test duration
    and load mode (via ``calc_metrics_interval``), so long-running stability
    tests produce far fewer data points than short benchmark runs.

    Args:
        environment: The Locust Environment instance providing runner and stats.
        include_entries: Forwarded to ``collect_realtime_snapshot`` to add
            per-metric detail (used by LLM API tests).
    """
    task_id = getattr(environment.parsed_options, "task_id", "") or os.environ.get(
        "TASK_ID", "unknown"
    )
    task_logger = logger.bind(task_id=task_id)

    task_type = "llm" if include_entries else "http"
    interval = calc_metrics_interval()
    task_logger.info(
        f"Real-time metrics collector started (interval={interval}s, sink=VictoriaMetrics)"
    )

    while True:
        try:
            gevent.sleep(interval)
            snapshot = collect_realtime_snapshot(
                environment, include_entries=include_entries
            )

            # Push to VictoriaMetrics (fire-and-forget)
            try:
                push_realtime_perf_metrics(task_id, task_type, snapshot)
            except Exception as e:
                task_logger.debug(f"VM push failure (non-fatal): {e}")
        except gevent.GreenletExit:
            break
        except Exception as e:  # pragma: no cover
            task_logger.debug(f"Realtime metrics push error: {e}")
