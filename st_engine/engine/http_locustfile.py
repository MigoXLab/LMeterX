"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import queue
import tempfile
import uuid
from collections import Counter
from typing import Any, Dict, Optional

import gevent
import urllib3
from locust import HttpUser, events, task
from urllib3.exceptions import InsecureRequestWarning

from config.base import (
    HTTP_OUTCOME_EXACT_LATENCY_MS,
    HTTP_OUTCOME_LATENCY_BUCKET_MS,
    MAX_QUEUE_SIZE,
)
from utils.error_handler import _safe_repr_truncate
from utils.logger import logger, setup_clean_log_format
from utils.realtime_metrics import realtime_metrics_greenlet

# Disable the specific InsecureRequestWarning from urllib3
# This warning appears when verify=False is used for SSL certificate verification
urllib3.disable_warnings(InsecureRequestWarning)


class _OutcomeBucket:
    """Aggregate response-time stats without keeping one item per request."""

    def __init__(self) -> None:
        self.count = 0
        self.total_latency = 0.0
        self.total_content_length = 0
        self.min_latency: Optional[float] = None
        self.max_latency: Optional[float] = None
        self.response_times: Counter[int] = Counter()

    @staticmethod
    def _bucket_latency(latency: float) -> int:
        rounded_latency = int(round(max(0.0, latency)))
        if rounded_latency <= HTTP_OUTCOME_EXACT_LATENCY_MS:
            return rounded_latency
        bucket_size = max(1, HTTP_OUTCOME_LATENCY_BUCKET_MS)
        return int(round(rounded_latency / bucket_size) * bucket_size)

    def record(
        self,
        response_time: Optional[float],
        response_length: Optional[int] = None,
    ) -> None:
        latency = float(response_time or 0.0)
        self.count += 1
        self.total_latency += latency
        self.total_content_length += int(response_length or 0)
        self.min_latency = (
            latency if self.min_latency is None else min(self.min_latency, latency)
        )
        self.max_latency = (
            latency if self.max_latency is None else max(self.max_latency, latency)
        )
        self.response_times[self._bucket_latency(latency)] += 1

    def merge(self, payload: Dict[str, Any]) -> None:
        count = int(payload.get("count", 0) or 0)
        self.count += count
        self.total_latency += float(payload.get("total_latency", 0.0) or 0.0)
        self.total_content_length += int(payload.get("total_content_length", 0) or 0)

        min_latency = payload.get("min_latency")
        if min_latency is not None:
            min_latency = float(min_latency)
            self.min_latency = (
                min_latency
                if self.min_latency is None
                else min(self.min_latency, min_latency)
            )

        max_latency = payload.get("max_latency")
        if max_latency is not None:
            max_latency = float(max_latency)
            self.max_latency = (
                max_latency
                if self.max_latency is None
                else max(self.max_latency, max_latency)
            )

        for latency, latency_count in (payload.get("response_times") or {}).items():
            self.response_times[self._bucket_latency(float(latency))] += int(
                latency_count
            )

    def avg(self) -> float:
        return self.total_latency / self.count if self.count else 0.0

    def avg_content_length(self) -> float:
        return self.total_content_length / self.count if self.count else 0.0

    def percentile(self, percentile: float) -> float:
        if not self.count:
            return 0.0
        threshold = self.count * percentile
        seen = 0
        for latency in sorted(self.response_times):
            seen += self.response_times[latency]
            if seen >= threshold:
                return float(latency)
        return float(max(self.response_times.keys(), default=0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "total_latency": self.total_latency,
            "total_content_length": self.total_content_length,
            "min_latency": self.min_latency,
            "max_latency": self.max_latency,
            "response_times": dict(self.response_times),
        }


class _OutcomeStats:
    """Track success/failure stats per request name and for the total row."""

    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, _OutcomeBucket]] = {}

    def record(
        self,
        name: Optional[str],
        response_time: Optional[float],
        response_length: Optional[int],
        failed: bool,
    ) -> None:
        metric_name = str(name or "unknown")
        for row_name in (metric_name, "total"):
            buckets = self.rows.setdefault(
                row_name,
                {"success": _OutcomeBucket(), "failure": _OutcomeBucket()},
            )
            buckets["failure" if failed else "success"].record(
                response_time, response_length
            )

    def merge(self, payload: Dict[str, Any]) -> None:
        for row_name, row_payload in (payload or {}).items():
            buckets = self.rows.setdefault(
                str(row_name),
                {"success": _OutcomeBucket(), "failure": _OutcomeBucket()},
            )
            for outcome in ("success", "failure"):
                if outcome in row_payload:
                    buckets[outcome].merge(row_payload[outcome])

    def build_rows(self, task_id: str, name: str, total_rps: float) -> list[Dict]:
        buckets = self.rows.get(name)
        if not buckets:
            return []

        success = buckets["success"]
        failure = buckets["failure"]
        total_requests = success.count + failure.count

        def proportional_rps(count: int) -> float:
            if total_requests <= 0:
                return 0.0
            return float(total_rps or 0.0) * count / total_requests

        rows = []
        for suffix, bucket in (("success", success), ("failure", failure)):
            if bucket.count == 0:
                continue
            rows.append(
                {
                    "task_id": task_id,
                    "metric_type": f"{name}::{suffix}",
                    "num_requests": bucket.count,
                    "num_failures": bucket.count if suffix == "failure" else 0,
                    "avg_latency": bucket.avg(),
                    "min_latency": bucket.min_latency or 0.0,
                    "max_latency": bucket.max_latency or 0.0,
                    "median_latency": bucket.percentile(0.5),
                    "p95_latency": bucket.percentile(0.95),
                    "rps": proportional_rps(bucket.count),
                    "avg_content_length": bucket.avg_content_length(),
                }
            )
        return rows

    def to_dict(self) -> Dict[str, Any]:
        return {
            row_name: {
                "success": buckets["success"].to_dict(),
                "failure": buckets["failure"].to_dict(),
            }
            for row_name, buckets in self.rows.items()
        }


_OUTCOME_STATS = _OutcomeStats()
_WORKER_OUTCOME_STATS: Dict[str, Dict[str, Any]] = {}


def _parse_kv(json_str: str) -> Dict[str, str]:
    """Safely parse headers/cookies JSON string."""
    if not json_str:
        return {}
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        logger.warning(f"Failed to parse kv json: {json_str}")
    return {}


def _write_result_file(task_id: str, locust_stats) -> str:
    """Persist aggregated metrics to a temporary location."""
    result_file = os.path.join(
        tempfile.gettempdir(), "locust_result", task_id, "result.json"
    )
    os.makedirs(os.path.dirname(result_file), exist_ok=True)

    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({"custom_metrics": {}, "locust_stats": locust_stats}, f, indent=4)

    return result_file


def _format_context(
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    json_payload: Optional[dict] = None,
    text_payload: Optional[str] = None,
    status: Optional[int] = None,
    response_body: Optional[str] = None,
    include_sensitive: bool = False,
) -> str:
    """
    Build a compact log string with key request/response context.
    include_sensitive=True will log headers/cookies (only for debug).
    """
    parts = []
    if status is not None:
        parts.append(f"status={status}")
    if include_sensitive:
        if headers:
            parts.append(f"headers: {headers}")
        if cookies:
            parts.append(f"cookies: {cookies}")
    if json_payload is not None:
        req_json_str = repr(json_payload)
        parts.append(
            f"request_json: {req_json_str[:500] + ('... (truncated)' if len(req_json_str) > 500 else '')}"
        )
    elif text_payload is not None and text_payload != "":
        parts.append(
            f"request_data: {text_payload[:500] + ('... (truncated)' if len(text_payload) > 500 else '')}"
        )
    if response_body is not None and response_body != "":
        parts.append(f"response_body: {response_body[:500]}")  # cap length

    # If nothing was added, return empty to avoid noisy blank context lines
    return " | ".join(parts) if parts else ""


def _resolve_json_field(data: dict, field_path: str):
    """Resolve a dot-separated field path (e.g. 'data.code') from a dict.

    Returns (True, value) if found, (False, None) otherwise.
    """
    keys = field_path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return False, None
    return True, current


def _check_success_assert(assert_rule: dict, response_body: str) -> tuple:
    """Check if the response body satisfies the success assertion rule.

    Returns:
        (is_success: bool, reason: str)
        - (True, "") if the assertion passes
        - (False, "reason") if the assertion fails
    """
    try:
        body = json.loads(response_body)
    except (json.JSONDecodeError, TypeError):
        return False, "Response body is not valid JSON"

    if not isinstance(body, dict):
        return False, "Response body is not a JSON object"

    field = assert_rule.get("field", "")
    operator = assert_rule.get("operator", "eq")
    expected = assert_rule.get("value")

    found, actual = _resolve_json_field(body, field)
    if not found:
        return False, f"Field '{field}' not found in response"

    if actual is None:
        return False, f"Field '{field}' is null in response"
    if expected is None:
        return False, "Assertion 'value' is not configured"

    try:
        # For equality / membership operators, compare as strings to avoid
        # type-mismatch issues (e.g. int 0 vs str "0", str "success" vs int).
        # For numeric ordering operators, convert to float.
        if operator == "eq":
            ok = str(actual) == str(expected)
        elif operator == "neq":
            ok = str(actual) != str(expected)
        elif operator == "gt":
            ok = float(str(actual)) > float(str(expected))
        elif operator == "gte":
            ok = float(str(actual)) >= float(str(expected))
        elif operator == "lt":
            ok = float(str(actual)) < float(str(expected))
        elif operator == "lte":
            ok = float(str(actual)) <= float(str(expected))
        elif operator == "in":
            expected_list = expected if isinstance(expected, list) else [expected]
            ok = str(actual) in [str(v) for v in expected_list]
        elif operator == "not_in":
            expected_list = expected if isinstance(expected, list) else [expected]
            ok = str(actual) not in [str(v) for v in expected_list]
        else:
            return False, f"Unknown operator: {operator}"
    except (TypeError, ValueError) as e:
        return False, f"Assertion comparison error: {e}"

    if ok:
        return True, ""
    else:
        return False, (
            f"Business assertion failed: {field}={actual}, "
            f"expected {operator} {expected}"
        )


def _parse_request_body(request_body: str):
    """Parse request_body string into (json_payload, text_payload) tuple.

    Attempts JSON parsing first; falls back to raw text on failure.
    """
    if request_body:
        try:
            return json.loads(request_body), None
        except (json.JSONDecodeError, TypeError):
            return None, request_body
    return None, request_body


def _build_request_kwargs(
    headers: Dict[str, str],
    cookies: Dict[str, str],
    json_payload: Optional[dict],
    text_payload: Optional[str],
) -> Dict[str, Any]:
    """
    Build request kwargs safely: prefer json if present, otherwise use data.
    Avoid sending both to prevent unexpected server behavior.
    """
    req_kwargs: Dict[str, Any] = {
        "headers": headers,
        "cookies": cookies,
    }
    if json_payload is not None:
        req_kwargs["json"] = json_payload
    elif text_payload is not None:
        req_kwargs["data"] = text_payload
    return req_kwargs


def _build_stat_row(task_id: str, name: str, stat) -> Dict:
    """Convert Locust internal stats to the expected shape."""
    try:
        return {
            "task_id": task_id,
            "metric_type": name,
            "num_requests": stat.num_requests,
            "num_failures": stat.num_failures,
            "avg_latency": stat.avg_response_time,
            "min_latency": stat.min_response_time,
            "max_latency": stat.max_response_time,
            "median_latency": stat.median_response_time,
            "p95_latency": stat.get_response_time_percentile(0.95),
            "rps": stat.total_rps,
            "avg_content_length": stat.avg_content_length,
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Failed to build stat row: {e}")
        return {}


@events.init_command_line_parser.add_listener
def init_parser(parser):
    """Add custom CLI options for HTTP API tasks."""
    parser.add_argument("--task-id", type=str, default="", help="Task identifier")
    parser.add_argument("--api_path", type=str, default="/", help="Request path")
    parser.add_argument("--method", type=str, default="GET", help="HTTP method")
    parser.add_argument("--headers", type=str, default="", help="Headers JSON")
    parser.add_argument("--cookies", type=str, default="", help="Cookies JSON")
    parser.add_argument("--request_body", type=str, default="", help="Request body")
    parser.add_argument(
        "--dataset_file",
        type=str,
        default="",
        help="Path to dataset file (JSONL, one request body per line)",
    )
    parser.add_argument(
        "--success_assert",
        type=str,
        default="",
        help='Business-level success assertion rule (JSON). e.g. {"field":"code","operator":"eq","value":0}',
    )


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Override Locust's default log format to remove hostname and module name."""
    setup_clean_log_format()


@events.request.add_listener
def on_request(
    request_type=None,
    name=None,
    response_time=None,
    response_length=None,
    response=None,
    context=None,
    exception=None,
    start_time=None,
    url=None,
    **kwargs,
):
    """Collect success/failure split metrics for final HTTP results."""
    _OUTCOME_STATS.record(
        name,
        response_time,
        response_length,
        exception is not None,
    )


@events.report_to_master.add_listener
def on_report_to_master(client_id, data, **kwargs):
    """Send worker-local success/failure split metrics to the master."""
    data["http_outcome_stats"] = _OUTCOME_STATS.to_dict()


@events.worker_report.add_listener
def on_worker_report(client_id, data, **kwargs):
    """Keep the latest cumulative split metrics received from each worker."""
    _WORKER_OUTCOME_STATS[str(client_id)] = data.get("http_outcome_stats") or {}


def _preload_dataset(environment) -> None:
    """Pre-load dataset file into a shared queue on the environment.

    Called once during ``test_start`` so that all users share the same queue
    without racing during ``on_start``.
    In multiprocess mode, uses mmap-backed SharedDatasetReader for memory efficiency.
    """
    options = environment.parsed_options
    dataset_file = getattr(options, "dataset_file", "") or ""
    if not dataset_file:
        return

    task_id = options.task_id or os.environ.get("TASK_ID", "unknown")
    task_logger = logger.bind(task_id=task_id)

    is_multiprocess = os.environ.get("LMETERX_PROCESS_COUNT", "1") != "1"

    try:
        if is_multiprocess:
            from utils.shared_dataset import DatasetQueueAdapter, SharedDatasetReader

            items = []
            with open(dataset_file, "r", encoding="utf-8") as f:
                for line in f:
                    if len(items) >= MAX_QUEUE_SIZE:
                        task_logger.warning(
                            f"Dataset file {dataset_file} exceeded "
                            f"MAX_QUEUE_SIZE={MAX_QUEUE_SIZE}; remaining records skipped."
                        )
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                        items.append({"json": payload})
                    except Exception:
                        items.append({"text": line})

            if items:
                reader = SharedDatasetReader.from_items(items, task_logger)
                environment.dataset_queue = DatasetQueueAdapter(reader)
                task_logger.info(
                    f"Using SharedDatasetReader ({len(reader)} items) "
                    f"for multiprocess HTTP mode"
                )
                return
            else:
                environment.dataset_queue = None
                task_logger.warning(
                    f"Dataset file {dataset_file} contained no valid records."
                )
                return

        # Single-process fallback: standard queue
        dq: queue.Queue = queue.Queue()
        with open(dataset_file, "r", encoding="utf-8") as f:
            for line in f:
                if dq.qsize() >= MAX_QUEUE_SIZE:
                    task_logger.warning(
                        f"Dataset file {dataset_file} exceeded "
                        f"MAX_QUEUE_SIZE={MAX_QUEUE_SIZE}; remaining records skipped."
                    )
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    dq.put({"json": payload})
                except Exception:
                    dq.put({"text": line})
        if dq.qsize() > 0:
            environment.dataset_queue = dq
            task_logger.info(
                f"Pre-loaded dataset file {dataset_file} "
                f"with {dq.qsize()} records (shared queue)."
            )
        else:
            environment.dataset_queue = None
            task_logger.warning(
                f"Dataset file {dataset_file} contained no valid records."
            )
    except Exception as e:  # pragma: no cover - defensive
        task_logger.error(f"Failed to pre-load dataset file {dataset_file}: {e}")
        environment.dataset_queue = None


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start, pre-load dataset, and spawn real-time metrics greenlet.

    In multiprocess mode (``--processes N``), only the **master** process
    reports metrics.  Worker processes are skipped because:
    1. The master's ``runner.user_count`` already reflects the total across
       all workers, while each worker only sees its own subset.
    2. All processes share identical VictoriaMetrics labels so worker pushes
       would overwrite the master's correct aggregated values.

    Dataset pre-loading runs on ALL processes (master, worker, local) because
    each process has its own address space and its own User instances.
    """
    global _OUTCOME_STATS, _WORKER_OUTCOME_STATS
    _OUTCOME_STATS = _OutcomeStats()
    _WORKER_OUTCOME_STATS = {}

    task_id = environment.parsed_options.task_id or os.environ.get("TASK_ID", "unknown")
    task_logger = logger.bind(task_id=task_id)
    load_mode = os.environ.get("LOAD_MODE", "fixed")
    task_logger.info(f"Common API load test started. load_mode={load_mode}")

    # Pre-load dataset into a shared queue (avoids race in on_start).
    # Must run on ALL processes (including workers) because each process
    # has its own memory space and its own CommonApiUser instances.
    _preload_dataset(environment)

    # Only collect real-time metrics on master (multiprocess) or local
    # (single-process).  Workers skip to avoid duplicate metric pushes.
    from locust.runners import WorkerRunner

    if isinstance(environment.runner, WorkerRunner):
        return

    # Spawn background greenlet for real-time metrics collection (shared module)
    environment._realtime_greenlet = gevent.spawn(
        realtime_metrics_greenlet, environment
    )


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Aggregate stats and write result file when the test ends.

    In multiprocess mode (``--processes N``):
    - Worker processes skip result writing entirely (they only contribute
      stats to the master via Locust's built-in stats sync).
    - The Master process waits briefly for worker stats to sync before
      aggregating and writing the final result file.
    """
    options = environment.parsed_options
    task_id = options.task_id or os.environ.get("TASK_ID", "unknown")
    task_logger = logger.bind(task_id=task_id)

    # Stop real-time metrics greenlet
    greenlet = getattr(environment, "_realtime_greenlet", None)
    if greenlet and not greenlet.dead:
        greenlet.kill(block=False)

    # In multiprocess mode, only the Master (or LocalRunner in single-
    # process mode) should aggregate stats and write the result file.
    # Worker processes hold only partial stats and must NOT write results.
    from locust.runners import LocalRunner, MasterRunner

    runner = environment.runner
    if not isinstance(runner, (MasterRunner, LocalRunner)):
        task_logger.debug("Worker process — skipping result file writing.")
        return

    # If running as Master, wait for workers to finish reporting their
    # stats so that `environment.stats` reflects the full aggregated data.
    if isinstance(runner, MasterRunner):
        task_logger.info("Master waiting for worker stats sync...")
        from utils.common import wait_time_for_stats_sync

        concurrent_users = int(os.environ.get("LOCUST_CONCURRENT_USERS", "0"))
        wait_time = wait_time_for_stats_sync(runner, concurrent_users)
        gevent.sleep(wait_time)

    locust_stats = []
    try:
        outcome_stats = _OutcomeStats()
        outcome_stats.merge(_OUTCOME_STATS.to_dict())
        for worker_payload in _WORKER_OUTCOME_STATS.values():
            outcome_stats.merge(worker_payload)

        # Locust `stats.entries` keys are (name, method) tuples.
        # Use `stat.name` for a clean string metric_type.
        for entry_key, stat in environment.stats.entries.items():
            stat_name = stat.name if hasattr(stat, "name") else str(entry_key)
            if stat_name in ("Aggregated",):
                continue
            try:
                row = _build_stat_row(task_id, stat_name, stat)
                if row:
                    locust_stats.append(row)
                    locust_stats.extend(
                        outcome_stats.build_rows(task_id, stat_name, stat.total_rps)
                    )
            except Exception as e:  # pragma: no cover - defensive
                task_logger.warning(f"Failed to build stat row for '{stat_name}': {e}")

        total_stat = environment.stats.total
        if total_stat:
            try:
                total_row = _build_stat_row(task_id, "total", total_stat)
                if total_row:
                    locust_stats.append(total_row)
                    locust_stats.extend(
                        outcome_stats.build_rows(task_id, "total", total_stat.total_rps)
                    )
            except Exception as e:  # pragma: no cover - defensive
                task_logger.warning(f"Failed to build total stat row: {e}")
    except Exception as e:  # pragma: no cover - defensive
        task_logger.error(f"Failed to aggregate HTTP stats: {e}", exc_info=True)
    finally:
        # Always attempt to write whatever stats were collected,
        # even if some entries failed during aggregation.
        if locust_stats:
            try:
                _write_result_file(task_id, locust_stats)
            except Exception as e:  # pragma: no cover - defensive
                task_logger.error(f"Failed to write result file: {e}", exc_info=True)

        # Release shared dataset mmap resources if applicable
        dataset_queue = getattr(environment, "dataset_queue", None)
        if dataset_queue and hasattr(dataset_queue, "close"):
            dataset_queue.close()


# ---------------------------------------------------------------------------
# Stepped load shape (conditionally activated via LOAD_MODE env var)
# Reuses the shared SteppedLoadShape from utils/stepped_load.py
# ---------------------------------------------------------------------------
_LOAD_MODE = os.environ.get("LOAD_MODE", "fixed")

if _LOAD_MODE == "stepped":
    from utils.stepped_load import SteppedLoadShape  # noqa: F401 – imported for Locust


class CommonApiUser(HttpUser):
    """Simple user class that replays a single API request."""

    def wait_time(self):  # type: ignore[override]
        """Disable wait time between requests for HTTP API tasks."""
        return 0

    def on_start(self):
        """Initialize runtime options before the task starts."""
        options = self.environment.parsed_options
        self.task_id = options.task_id or os.environ.get("TASK_ID", "unknown")
        self.api_path = options.api_path or "/"
        self.method = (options.method or "GET").upper()
        self.headers = _parse_kv(getattr(options, "headers", ""))
        self.cookies = _parse_kv(getattr(options, "cookies", ""))
        self.request_body = getattr(options, "request_body", "") or ""
        self.success_assert_rule = None

        # Parse success assertion rule
        success_assert_str = getattr(options, "success_assert", "") or ""
        if success_assert_str:
            try:
                self.success_assert_rule = json.loads(success_assert_str)
                logger.info(f"Success assertion enabled: {self.success_assert_rule}")
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    f"Invalid success_assert JSON, ignoring: {success_assert_str}"
                )

        # Disable SSL certificate verification for self-signed certificates
        self.client.verify = False

        # Attach the shared dataset queue pre-loaded during test_start
        self.dataset_queue = getattr(self.environment, "dataset_queue", None)

        self.task_logger = logger.bind(task_id=self.task_id)

    @task
    def invoke_api(self):
        """Execute a single HTTP request."""
        # Initialize payload variables outside try block so they are always
        # bound, even if an exception occurs before assignment inside try.
        json_payload = None
        text_payload = None
        req_id = uuid.uuid4().hex[:8]
        try:
            if self.dataset_queue:
                try:
                    record = self.dataset_queue.get_nowait()
                    # Round-robin: put back the record for other users
                    self.dataset_queue.put_nowait(record)
                    if "json" in record:
                        json_payload = record["json"]
                    else:
                        text_payload = record.get("text", "")
                except queue.Empty:
                    json_payload, text_payload = _parse_request_body(self.request_body)
            else:
                # Try to parse request_body as JSON so it is sent with
                # Content-Type: application/json (matching the test-API behaviour).
                json_payload, text_payload = _parse_request_body(self.request_body)

            req_kwargs = _build_request_kwargs(
                self.headers,
                self.cookies,
                json_payload,
                text_payload,
            )

            # Include HTTP method in request_name so different methods on
            # the same path are tracked as separate metrics.
            if len(self.api_path) < 40:
                request_name = f"{self.method} {self.api_path}"
            else:
                request_name = self.method

            # Always use catch_response=True so we can explicitly control
            # success/failure marking for both HTTP-level and business-level checks.
            req_kwargs["catch_response"] = True

            payload_data = req_kwargs.get("json") or req_kwargs.get("data")

            with self.client.request(
                self.method,
                self.api_path,
                name=request_name,
                **req_kwargs,
            ) as resp:
                self.task_logger.debug(
                    f"[{req_id}] Response: status={resp.status_code}, body={repr(resp.text)}"
                )
                if resp.status_code >= 300:
                    # Non-2xx HTTP status → mark as failure
                    resp.failure(f"HTTP {resp.status_code}: {resp.text[:500]}")
                    self.task_logger.error(
                        f"[{req_id}] HTTP error | "
                        + _format_context(
                            json_payload=json_payload,
                            text_payload=text_payload,
                            status=resp.status_code,
                            response_body=resp.text,
                        )
                    )
                elif (
                    self.success_assert_rule is not None
                    and resp.status_code != 204
                    and resp.text
                ):
                    # 2xx (non-204) + business assertion enabled → validate
                    is_success, reason = _check_success_assert(
                        self.success_assert_rule, resp.text
                    )
                    if is_success:
                        resp.success()
                        if payload_data:
                            self.task_logger.opt(lazy=True).debug(
                                "[{req_id}] Request Payload: {payload}",
                                req_id=lambda: req_id,
                                payload=lambda: _safe_repr_truncate(payload_data, 500),
                            )
                    else:
                        resp.failure(reason)
                        self.task_logger.error(
                            f"[{req_id}] Business assertion failed | "
                            + _format_context(
                                json_payload=json_payload,
                                text_payload=text_payload,
                                status=resp.status_code,
                                response_body=resp.text,
                            )
                        )
                else:
                    # 2xx (or 204 / empty body with assert) → success
                    resp.success()
                    if payload_data:
                        self.task_logger.opt(lazy=True).debug(
                            "[{req_id}] Request Payload: {payload}",
                            req_id=lambda: req_id,
                            payload=lambda: _safe_repr_truncate(payload_data, 500),
                        )
        except Exception as e:  # pragma: no cover - network dependent
            # Log failure with request context
            self.task_logger.error(
                f"[{req_id}] Common API request failed: {e} | "
                + _format_context(
                    json_payload=json_payload,
                    text_payload=text_payload,
                )
            )
