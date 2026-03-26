"""
Locustfile for common HTTP API load testing (non-LLM).
Supports both fixed concurrency and stepped load patterns.
"""

import json
import logging
import os
import queue
import tempfile
from typing import Any, Dict, Optional

import gevent
import urllib3
from locust import HttpUser, events, task
from urllib3.exceptions import InsecureRequestWarning

from utils.logger import logger
from utils.realtime_metrics import realtime_metrics_greenlet

# Disable the specific InsecureRequestWarning from urllib3
# This warning appears when verify=False is used for SSL certificate verification
urllib3.disable_warnings(InsecureRequestWarning)


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
        parts.append(f"request_json: {json_payload}")
    elif text_payload is not None and text_payload != "":
        parts.append(f"request_data: {text_payload}")
    if response_body is not None and response_body != "":
        parts.append(f"response_body: {response_body[:1000]}")  # cap length

    # If nothing was added, return empty to avoid noisy blank context lines
    return " | ".join(parts) if parts else ""


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
    method: str,
    api_path: str,
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


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Override Locust's default log format to remove hostname and module name."""
    _clean_fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for _handler in logging.root.handlers:
        _handler.setFormatter(_clean_fmt)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start and spawn real-time metrics greenlet.

    In multiprocess mode (``--processes N``), only the **master** process
    reports metrics.  Worker processes are skipped because:
    1. The master's ``runner.user_count`` already reflects the total across
       all workers, while each worker only sees its own subset.
    2. All processes share identical VictoriaMetrics labels so worker pushes
       would overwrite the master's correct aggregated values.
    """
    # Only collect metrics on master (multiprocess) or local (single-process).
    from locust.runners import WorkerRunner

    if isinstance(environment.runner, WorkerRunner):
        return

    task_id = environment.parsed_options.task_id or os.environ.get("TASK_ID", "unknown")
    task_logger = logger.bind(task_id=task_id)
    load_mode = os.environ.get("LOAD_MODE", "fixed")
    task_logger.info(f"Common API load test started. load_mode={load_mode}")
    # Spawn background greenlet for real-time metrics collection (shared module)
    environment._realtime_greenlet = gevent.spawn(
        realtime_metrics_greenlet, environment
    )


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Aggregate stats and write result file when the test ends."""
    options = environment.parsed_options
    task_id = options.task_id or os.environ.get("TASK_ID", "unknown")
    task_logger = logger.bind(task_id=task_id)

    # Stop real-time metrics greenlet
    greenlet = getattr(environment, "_realtime_greenlet", None)
    if greenlet and not greenlet.dead:
        greenlet.kill(block=False)

    locust_stats = []
    try:
        for name, stat in environment.stats.entries.items():
            if name in ("Aggregated", "Total"):
                continue
            row = _build_stat_row(task_id, name, stat)
            if row:
                locust_stats.append(row)

        total_stat = environment.stats.total
        if total_stat:
            total_row = _build_stat_row(task_id, "total", total_stat)
            if total_row:
                locust_stats.append(total_row)
        # task_logger.debug(f"locust_stats: {locust_stats}")
        result_file = _write_result_file(task_id, locust_stats)
    except Exception as e:  # pragma: no cover - defensive
        task_logger.error(f"Failed to aggregate HTTP stats: {e}", exc_info=True)


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
        self.dataset_file = getattr(options, "dataset_file", "") or ""
        self.dataset_queue = None

        # Disable SSL certificate verification for self-signed certificates
        self.client.verify = False

        # Shared dataset queue across users to achieve round-robin usage
        if self.dataset_file:
            if (
                not hasattr(self.environment, "dataset_queue")
                or self.environment.dataset_queue is None
            ):
                try:
                    dq: queue.Queue = queue.Queue()
                    with open(self.dataset_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                payload = json.loads(line)
                                dq.put({"json": payload})
                            except Exception:
                                dq.put({"text": line})
                    if dq.qsize() > 0:
                        self.environment.dataset_queue = dq
                        logger.info(
                            f"Loaded dataset file {self.dataset_file} with {dq.qsize()} records (shared queue)."
                        )
                    else:
                        logger.warning(
                            f"Dataset file {self.dataset_file} contained no valid records."
                        )
                except Exception as e:  # pragma: no cover - defensive
                    logger.error(
                        f"Failed to load dataset file {self.dataset_file}: {e}"
                    )
                    self.environment.dataset_queue = None

            # Attach the shared queue for this user
            if hasattr(self.environment, "dataset_queue"):
                self.dataset_queue = self.environment.dataset_queue

        self.task_logger = logger.bind(task_id=self.task_id)

    @task
    def invoke_api(self):
        """Execute a single HTTP request."""
        try:
            json_payload = None
            text_payload = None
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
                self.method,
                self.api_path,
                self.headers,
                self.cookies,
                json_payload,
                text_payload,
            )
            # Log the outgoing request parameters at debug level
            # self.task_logger.debug(
            #     _format_context(
            #         headers=self.headers,
            #         cookies=self.cookies,
            #         json_payload=json_payload,
            #         text_payload=text_payload,
            #         include_sensitive=True,
            #     )
            # )

            response = self.client.request(
                self.method,
                self.api_path,
                name=(
                    f"{self.api_path}" if len(self.api_path) < 40 else f"{self.method}"
                ),
                **req_kwargs,
            )

            # Log non-2xx responses with details
            if response.status_code >= 400:
                self.task_logger.error(
                    _format_context(
                        json_payload=json_payload,
                        text_payload=text_payload,
                        status=response.status_code,
                        response_body=response.text,
                    )
                )
        except Exception as e:  # pragma: no cover - network dependent
            # Log failure with request context
            self.task_logger.error(
                f"Common API request failed: {e} | "
                + _format_context(
                    json_payload=json_payload,
                    text_payload=text_payload,
                )
            )
