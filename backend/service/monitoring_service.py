"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from utils.logger import logger

# VictoriaMetrics URL (same as engine side, but from backend's perspective)
VM_URL: str = os.environ.get("VICTORIA_METRICS_URL", "http://localhost:8428")
_QUERY_TIMEOUT: float = 10.0

# Default max points for frontend rendering (avoids browser freeze)
DEFAULT_MAX_POINTS: int = 1200


async def _vm_query_range(
    query: str,
    start: float,
    end: float,
    step: str = "2s",
) -> List[Dict[str, Any]]:
    """Execute a range query against VictoriaMetrics.

    Args:
        query: PromQL query string.
        start: Start timestamp (Unix seconds).
        end: End timestamp (Unix seconds).
        step: Query resolution step.

    Returns:
        List of result dicts from the ``data.result`` array.
    """
    url = f"{VM_URL}/api/v1/query_range"
    params = {
        "query": query,
        "start": str(start),
        "end": str(end),
        "step": step,
    }

    try:
        async with httpx.AsyncClient(timeout=_QUERY_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(f"VM query_range failed: HTTP {resp.status_code}")
                return []
            data = resp.json()
            if data.get("status") != "success":
                logger.warning(f"VM query_range error: {data.get('error', 'unknown')}")
                return []
            return data.get("data", {}).get("result", [])
    except httpx.ConnectError:
        logger.debug("VictoriaMetrics not reachable for query_range")
        return []
    except Exception as e:
        logger.debug(f"VM query_range error: {e}")
        return []


async def _vm_query_instant(query: str) -> List[Dict[str, Any]]:
    """Execute an instant query against VictoriaMetrics.

    Args:
        query: PromQL query string.

    Returns:
        List of result dicts from the ``data.result`` array.
    """
    url = f"{VM_URL}/api/v1/query"
    params = {"query": query}

    try:
        async with httpx.AsyncClient(timeout=_QUERY_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            if data.get("status") != "success":
                return []
            return data.get("data", {}).get("result", [])
    except Exception as e:
        logger.debug(f"VM instant query error: {e}")
        return []


def _calc_step(start: float, end: float, max_points: int = DEFAULT_MAX_POINTS) -> str:
    """Calculate an appropriate step for a range query to limit point count."""
    duration = max(end - start, 1)
    step_sec = max(int(duration / max_points), 1)
    return f"{step_sec}s"


def lttb_downsample(
    data: List[Tuple[float, float]], threshold: int
) -> List[Tuple[float, float]]:
    """Largest-Triangle-Three-Buckets (LTTB) downsampling algorithm.

    Reduces a time-series to *threshold* points while preserving visual shape.

    Args:
        data: List of (timestamp, value) tuples, sorted by timestamp.
        threshold: Target number of output points.

    Returns:
        Downsampled list of (timestamp, value) tuples.
    """
    n = len(data)
    if n <= threshold or threshold < 3:
        return data

    sampled: List[Tuple[float, float]] = [data[0]]  # Always keep first

    bucket_size = (n - 2) / (threshold - 2)

    a_index = 0
    for i in range(1, threshold - 1):
        # Calculate bucket boundaries
        avg_range_start = int(math.floor((i + 0) * bucket_size)) + 1
        avg_range_end = int(math.floor((i + 1) * bucket_size)) + 1
        avg_range_end = min(avg_range_end, n)

        # Calculate point average for next bucket
        avg_x = 0.0
        avg_y = 0.0
        count = avg_range_end - avg_range_start
        if count <= 0:
            continue
        for j in range(avg_range_start, avg_range_end):
            avg_x += data[j][0]
            avg_y += data[j][1]
        avg_x /= count
        avg_y /= count

        # Find the point in current bucket with max triangle area
        range_start = int(math.floor((i - 1) * bucket_size)) + 1
        range_end = int(math.floor(i * bucket_size)) + 1
        range_end = min(range_end, n)

        max_area = -1.0
        max_area_index = range_start
        point_a = data[a_index]

        for j in range(range_start, range_end):
            area = abs(
                (point_a[0] - avg_x) * (data[j][1] - point_a[1])
                - (point_a[0] - data[j][0]) * (avg_y - point_a[1])
            )
            if area > max_area:
                max_area = area
                max_area_index = j

        sampled.append(data[max_area_index])
        a_index = max_area_index

    sampled.append(data[-1])  # Always keep last
    return sampled


def _extract_series(
    results: List[Dict[str, Any]],
    max_points: int = DEFAULT_MAX_POINTS,
) -> List[Dict[str, Any]]:
    """Extract and downsample time-series from VM query results.

    Args:
        results: VM query_range result array.
        max_points: Maximum number of points per series.

    Returns:
        List of dicts with ``metric`` labels and ``values`` as
        ``[[timestamp, value], ...]``.
    """
    series_list = []
    for result in results:
        metric_labels = result.get("metric", {})
        values = result.get("values", [])

        # Convert to (timestamp, value) tuples
        data_points: List[Tuple[float, float]] = []
        for v in values:
            try:
                ts = float(v[0])
                val = float(v[1])
                data_points.append((ts, val))
            except (ValueError, IndexError, TypeError):
                continue

        # Apply LTTB downsampling if needed
        if len(data_points) > max_points:
            data_points = lttb_downsample(data_points, max_points)

        series_list.append(
            {
                "metric": metric_labels,
                "values": [[p[0], p[1]] for p in data_points],
            }
        )

    return series_list


# ----- Public API functions -----


async def get_engine_resource_metrics(
    engine_id: Optional[str] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
    max_points: int = DEFAULT_MAX_POINTS,
) -> Dict[str, Any]:
    """Get Engine system resource metrics (CPU, Memory, Network).

    Args:
        engine_id: Filter by specific engine. If None, returns all engines.
        start: Start timestamp (Unix seconds). Defaults to 5 minutes ago.
        end: End timestamp (Unix seconds). Defaults to now.
        max_points: Maximum number of data points per series.

    Returns:
        Dict with ``cpu``, ``memory``, ``network`` series data.
    """
    now = time.time()
    if end is None:
        end = now
    if start is None:
        start = end - 300  # default 5 min

    step = _calc_step(start, end, max_points)
    label_filter = f'engine_id="{engine_id}"' if engine_id else ""

    queries = {
        "cpu_percent": f"engine_cpu_percent{{{label_filter}}}",
        "cpu_limit_cores": f"engine_cpu_limit_cores{{{label_filter}}}",
        "memory_used_bytes": f"engine_memory_used_bytes{{{label_filter}}}",
        "memory_total_bytes": f"engine_memory_total_bytes{{{label_filter}}}",
        "memory_percent": f"engine_memory_percent{{{label_filter}}}",
        "network_sent_bytes_per_sec": f"engine_network_sent_bytes_per_sec{{{label_filter}}}",
        "network_recv_bytes_per_sec": f"engine_network_recv_bytes_per_sec{{{label_filter}}}",
    }

    result: Dict[str, Any] = {}
    for key, query in queries.items():
        raw = await _vm_query_range(query, start, end, step)
        result[key] = _extract_series(raw, max_points)

    return result


def _calc_perf_step(
    start: float,
    end: float,
    max_points: int,
) -> str:
    """Calculate step for perf queries, capped at the collection interval."""
    raw_step = _calc_step(start, end, max_points)
    step_seconds = int(raw_step.rstrip("s"))
    max_perf_step = 2
    return raw_step if step_seconds <= max_perf_step else f"{max_perf_step}s"


#: Base metric names queried from VictoriaMetrics.
_BASE_METRIC_NAMES: List[str] = [
    "lmeterx_current_users",
    "lmeterx_current_rps",
    "lmeterx_current_fail_per_sec",
    "lmeterx_avg_response_time",
    "lmeterx_min_response_time",
    "lmeterx_max_response_time",
    "lmeterx_median_response_time",
    "lmeterx_p95_response_time",
    "lmeterx_total_requests",
    "lmeterx_total_failures",
]

#: Per-entry sub-keys for LLM API detail metrics.
_ENTRY_SUB_KEYS: List[str] = [
    "avg_response_time",
    "current_rps",
    "current_fail_per_sec",
]


async def _query_base_metrics(
    label_filter: str,
    start: float,
    end: float,
    step: str,
) -> Dict[str, List[Tuple[float, float]]]:
    """Query base performance metrics and return parsed time-series."""
    all_series: Dict[str, List[Tuple[float, float]]] = {}
    for metric_name in _BASE_METRIC_NAMES:
        query = f"{metric_name}{{{label_filter}}}"
        raw = await _vm_query_range(query, start, end, step)
        if raw:
            values = raw[0].get("values", [])
            points: List[Tuple[float, float]] = []
            for v in values:
                try:
                    points.append((float(v[0]), float(v[1])))
                except (ValueError, IndexError, TypeError):
                    continue
            short_name = metric_name.replace("lmeterx_", "")
            all_series[short_name] = points
    return all_series


async def _query_entry_metrics(
    label_filter: str,
    start: float,
    end: float,
    step: str,
) -> Dict[str, Dict[str, Dict[float, float]]]:
    """Query per-entry detail metrics (LLM API only)."""
    entry_data: Dict[str, Dict[str, Dict[float, float]]] = {}
    for sub_key in _ENTRY_SUB_KEYS:
        query = f"lmeterx_entry_{sub_key}{{{label_filter}}}"
        raw = await _vm_query_range(query, start, end, step)
        for series in raw:
            metric_name_label = series.get("metric", {}).get("metric_name", "")
            if not metric_name_label:
                continue
            entry_data.setdefault(metric_name_label, {})
            entry_data[metric_name_label].setdefault(sub_key, {})
            for v in series.get("values", []):
                try:
                    ts = float(v[0])
                    val = float(v[1])
                    entry_data[metric_name_label][sub_key][ts] = val
                except (ValueError, IndexError, TypeError):
                    continue
    return entry_data


def _collect_timestamps(
    all_series: Dict[str, List[Tuple[float, float]]],
    entry_data: Dict[str, Dict[str, Dict[float, float]]],
) -> List[float]:
    """Collect and sort the union of all timestamps."""
    all_timestamps: set = set()
    for points in all_series.values():
        for ts, _ in points:
            all_timestamps.add(ts)
    for metric_name_data in entry_data.values():
        for sub_key_data in metric_name_data.values():
            all_timestamps.update(sub_key_data.keys())
    return sorted(all_timestamps)


def _build_entry_at_ts(
    entry_data: Dict[str, Dict[str, Dict[float, float]]],
    ts: float,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Build the per-entry metrics dict for a single timestamp."""
    metrics_at_ts: Dict[str, Dict[str, Any]] = {}
    for entry_name, sub_data in entry_data.items():
        entry: Dict[str, Any] = {}
        has_value = False
        for sub_key in _ENTRY_SUB_KEYS:
            entry_val: Optional[float] = sub_data.get(sub_key, {}).get(ts)
            if entry_val is not None:
                entry[sub_key] = entry_val
                has_value = True
            else:
                entry[sub_key] = 0
        if has_value:
            metrics_at_ts[entry_name] = entry
    return metrics_at_ts if metrics_at_ts else None


def _build_snapshots(
    all_series: Dict[str, List[Tuple[float, float]]],
    entry_data: Dict[str, Dict[str, Dict[float, float]]],
    sorted_timestamps: List[float],
) -> List[Dict[str, Any]]:
    """Reconstruct snapshot-format dicts from series data."""
    series_lookup: Dict[str, Dict[float, float]] = {}
    for name, points in all_series.items():
        series_lookup[name] = dict(points)

    data_points: List[Dict[str, Any]] = []
    for ts in sorted_timestamps:
        point: Dict[str, Any] = {"timestamp": ts}
        for name in all_series:
            point[name] = series_lookup.get(name, {}).get(ts, 0)
        if entry_data:
            entry_metrics = _build_entry_at_ts(entry_data, ts)
            if entry_metrics:
                point["metrics"] = entry_metrics
        data_points.append(point)
    return data_points


def _downsample_snapshots(
    data_points: List[Dict[str, Any]],
    max_points: int,
) -> List[Dict[str, Any]]:
    """Apply LTTB downsampling on snapshot list using current_rps."""
    if len(data_points) <= max_points:
        return data_points
    representative = [(p["timestamp"], p.get("current_rps", 0)) for p in data_points]
    downsampled = lttb_downsample(representative, max_points)
    kept_timestamps = {p[0] for p in downsampled}
    return [p for p in data_points if p["timestamp"] in kept_timestamps]


async def get_task_perf_metrics_from_vm(
    task_id: str,
    since: float = 0.0,
    max_points: int = DEFAULT_MAX_POINTS,
) -> List[Dict[str, Any]]:
    """Get real-time performance metrics for a task from VictoriaMetrics.

    This is the VM-based replacement for JSONL file reading and MySQL queries.

    Args:
        task_id: The task identifier.
        since: Only return data points after this timestamp (Unix seconds).
        max_points: Maximum number of data points per metric.

    Returns:
        List of metric snapshot dicts, similar to the old JSONL format.
        Each dict contains base metrics and an optional ``metrics`` dict
        with per-entry breakdowns (LLM API only).
    """
    now = time.time()
    start = since if since > 0 else now - 7200  # default last 2 h
    end = now
    step = _calc_perf_step(start, end, max_points)
    label_filter = f'task_id="{task_id}"'

    all_series = await _query_base_metrics(label_filter, start, end, step)
    entry_data = await _query_entry_metrics(label_filter, start, end, step)

    if not all_series and not entry_data:
        return []

    sorted_timestamps = _collect_timestamps(all_series, entry_data)
    data_points = _build_snapshots(all_series, entry_data, sorted_timestamps)
    return _downsample_snapshots(data_points, max_points)


async def get_available_engines() -> List[Dict[str, Any]]:
    """Get list of engines that have reported metrics recently.

    Returns:
        List of dicts with ``engine_id`` and ``last_seen`` timestamp.
    """
    results = await _vm_query_instant("engine_cpu_percent")
    engines = []
    for r in results:
        metric = r.get("metric", {})
        value = r.get("value", [0, 0])
        engines.append(
            {
                "engine_id": metric.get("engine_id", "unknown"),
                "last_seen": float(value[0]) if value else 0,
                "cpu_percent": float(value[1]) if len(value) > 1 else 0,
            }
        )
    return engines
