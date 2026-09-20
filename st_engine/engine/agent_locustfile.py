"""Locust workload for MCP Streamable HTTP and A2A 1.0 JSON-RPC."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections import Counter, defaultdict
from typing import Any, Optional

import gevent
from locust import HttpUser, events, task
from locust.exception import StopUser

# grpcio's C core drives I/O completion through background threads.  Locust
# runs under gevent monkey-patching, which turns those threads into greenlets.
# Because gevent is cooperative, the background greenlet that signals channel
# readiness / response completion never runs while the main greenlet is blocked
# in ``channel_ready_future().result()`` or ``unary_unary()()``, deadlocking the
# user.  ``init_gevent()`` swaps grpc's pollset for a gevent-compatible one so
# the two cooperate.  Must be called after gevent is patched (Locust patches
# before importing the locustfile) and before any channel is created.
try:
    import gevent.monkey as _gevent_monkey

    if _gevent_monkey.is_module_patched("socket"):
        import grpc.experimental.gevent as _grpc_gevent

        _grpc_gevent.init_gevent()
except ImportError:
    pass

from engine.agent_protocol import (
    A2A_INTERRUPTED_STATES,
    A2A_REST_METHODS,
    A2A_TERMINAL_STATES,
    WeightedScenarioCursor,
    a2a_message_request,
    a2a_task_id,
    a2a_task_state,
    is_a2a_send_response,
    is_stateless_mcp,
    jsonrpc_request,
    load_protocol_dataset,
    mcp_call_observation,
    mcp_content_bytes,
    mcp_header_value,
    mcp_parameter_headers,
    mcp_request_metadata,
    parse_json_or_sse,
    rpc_payload,
    sample_summary,
    token_count_observation,
)

logger = logging.getLogger(__name__)


class ProtocolMetrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.started_at = time.perf_counter()
        self.counters: Counter[str] = Counter()
        self.samples: dict[str, list[float]] = defaultdict(list)
        self.transitions: dict[str, list[float]] = defaultdict(list)
        self.scenario_weights: dict[str, int] = {}

    def increment(self, key: str, value: int = 1) -> None:
        with self.lock:
            self.counters[key] += value

    def sample(self, key: str, value: float) -> None:
        with self.lock:
            self.samples[key].append(float(value))

    def transition(self, before: str, after: str, elapsed_ms: float) -> None:
        with self.lock:
            self.transitions[f"{before}->{after}"].append(float(elapsed_ms))

    def summary(self, protocol: str) -> dict[str, Any]:
        with self.lock:
            counters = dict(self.counters)
            samples = {key: list(values) for key, values in self.samples.items()}
            transitions = {
                key: list(values) for key, values in self.transitions.items()
            }
        elapsed = max(time.perf_counter() - self.started_at, 0.001)
        top_level = counters.get("top_level_requests", 0)
        submitted = counters.get("submissions", 0)
        submitted_ok = counters.get("submission_successes", 0)
        terminal = counters.get("terminal_tasks", 0)
        completed = counters.get("completed_tasks", 0)
        result: dict[str, Any] = {
            "protocol": protocol,
            "top_level_requests": top_level,
            "failed_requests": counters.get("failed_requests", 0),
            "top_level_rps": top_level / elapsed,
            "elapsed_seconds": elapsed,
            "scenario_weights": dict(self.scenario_weights),
            "scenario_selections": {
                key.removeprefix("scenario_selected:"): value
                for key, value in counters.items()
                if key.startswith("scenario_selected:")
            },
            # Keep the selected dataset-row ids separate from scenario counts.
            # Scenario counts validate the configured traffic split; row counts
            # make an uploaded JSONL's actual use observable in a finished run.
            "dataset_row_selections": {
                key.removeprefix("dataset_row_selected:"): value
                for key, value in counters.items()
                if key.startswith("dataset_row_selected:")
            },
        }
        if protocol == "a2a":
            observable = counters.get("cascade_observable_requests", 0)
            request_attempts = counters.get("a2a_request_attempts", 0)
            request_failures = counters.get("a2a_request_failures", 0)
            failed_tasks = counters.get("failed_tasks", 0)
            total_failure_events = request_failures + failed_tasks
            total_failure_opportunities = request_attempts + terminal
            task_acceptance_rate = submitted_ok / submitted if submitted else 0.0
            terminal_task_completion_rate = completed / terminal if terminal else 0.0
            terminal_task_failure_rate = failed_tasks / terminal if terminal else 0.0
            composite_failure_rate = (
                total_failure_events / total_failure_opportunities
                if total_failure_opportunities
                else 0.0
            )
            result.update(
                {
                    "task_submission_rate": submitted / elapsed,
                    "task_acceptance_rate": task_acceptance_rate,
                    # Deprecated compatibility alias.
                    "task_submission_success_rate": task_acceptance_rate,
                    "submissions": submitted,
                    "submission_successes": submitted_ok,
                    "terminal_tasks": terminal,
                    "completed_tasks": completed,
                    "terminal_task_completion_rate": terminal_task_completion_rate,
                    # Deprecated compatibility alias.
                    "terminal_completion_rate": terminal_task_completion_rate,
                    "terminal_task_throughput": terminal / elapsed,
                    "failed_tasks": failed_tasks,
                    "terminal_task_failure_rate": terminal_task_failure_rate,
                    # Deprecated compatibility alias.
                    "terminal_failure_rate": terminal_task_failure_rate,
                    "a2a_request_attempts": request_attempts,
                    "a2a_request_failures": request_failures,
                    "composite_failure_rate": composite_failure_rate,
                    # Deprecated compatibility alias.
                    "total_failure_rate": composite_failure_rate,
                    "task_states": {
                        key.removeprefix("state_"): value
                        for key, value in counters.items()
                        if key.startswith("state_")
                    },
                    "end_to_end_latency_ms": sample_summary(
                        samples.get("a2a_e2e_ms", [])
                    ),
                    "time_to_first_event_ms": sample_summary(
                        samples.get("a2a_ttfe_ms", [])
                    ),
                    "state_transition_latency_ms": {
                        key: sample_summary(values)
                        for key, values in transitions.items()
                    },
                    "cascade_amplification_factor": (
                        counters.get("observed_mcp_calls", 0) / observable
                        if observable
                        else None
                    ),
                    "observed_mcp_calls": counters.get("observed_mcp_calls", 0),
                    "cascade_observable_requests": observable,
                    "cascade_observability_rate": (
                        observable / top_level if top_level else 0.0
                    ),
                }
            )
        else:
            calls = counters.get("mcp_tool_calls", 0)
            completed_calls = counters.get("mcp_completed_tool_calls", 0)
            successful = counters.get("mcp_tool_successes", 0)
            token_total = counters.get("tokens", 0)
            token_available = counters.get("token_measurements", 0) > 0
            tool_call_request_rate = calls / elapsed
            tool_call_throughput = completed_calls / elapsed
            successful_tool_call_throughput = successful / elapsed
            result.update(
                {
                    "tool_call_success_rate": successful / calls if calls else 0.0,
                    "tool_calls": calls,
                    "completed_tool_calls": completed_calls,
                    "successful_tool_calls": successful,
                    "tool_call_request_rate": tool_call_request_rate,
                    "tool_call_throughput": tool_call_throughput,
                    "successful_tool_call_throughput": (
                        successful_tool_call_throughput
                    ),
                    # Deprecated compatibility aliases.
                    "tool_call_rps": tool_call_request_rate,
                    "completion_throughput": tool_call_throughput,
                    "successful_throughput": successful_tool_call_throughput,
                    "tool_calls_per_second": calls / elapsed,
                    "time_to_first_event_ms": sample_summary(
                        samples.get("mcp_ttfe_ms", [])
                    ),
                    "end_to_end_latency_ms": sample_summary(
                        samples.get("mcp_e2e_ms", [])
                    ),
                    # Prefer dedicated TTFT samples; fall back to TTFE for older runs
                    # that only recorded mcp_ttfe_ms (same first-byte timing on MCP).
                    "ttft_ms": sample_summary(
                        samples.get("mcp_ttft_ms") or samples.get("mcp_ttfe_ms", [])
                    ),
                    "response_time_ms": sample_summary(samples.get("mcp_e2e_ms", [])),
                    "content_throughput_bytes_per_second": counters.get(
                        "content_bytes", 0
                    )
                    / elapsed,
                    "tokens": token_total,
                    "tokens_per_second": (
                        token_total / elapsed if token_available else None
                    ),
                    "tokens_per_second_available": token_available,
                    "token_count_path_configured": bool(
                        counters.get("token_count_configured", 0)
                    ),
                    "token_measurements": counters.get("token_measurements", 0),
                }
            )
        return result


METRICS = ProtocolMetrics()
WORKLOAD: Optional[WeightedScenarioCursor] = None


def _result_file(task_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), "locust_result", task_id, "result.json")


def _stat_row(task_id: str, name: str, stat) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "metric_type": name,
        "num_requests": stat.num_requests,
        "num_failures": stat.num_failures,
        "avg_latency": stat.avg_response_time,
        "min_latency": stat.min_response_time or 0.0,
        "max_latency": stat.max_response_time or 0.0,
        "median_latency": stat.median_response_time,
        "p95_latency": stat.get_response_time_percentile(0.95),
        "rps": stat.total_rps,
        "avg_content_length": stat.avg_content_length,
    }


@events.init_command_line_parser.add_listener
def init_parser(parser):
    parser.add_argument("--task-id", type=str, default="")
    parser.add_argument("--config-file", type=str, required=True)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    global METRICS, WORKLOAD
    METRICS = ProtocolMetrics()
    WORKLOAD = None
    with open(environment.parsed_options.config_file, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    protocol = str(config.get("protocol") or "")
    scenario_key = "a2a_scenarios" if protocol == "a2a" else "mcp_calls"
    scenarios = config.get(scenario_key) or []
    scenario_ids = {str(item.get("id") or "") for item in scenarios}
    dataset_rows = None
    if config.get("dataset_file"):
        dataset_rows = load_protocol_dataset(
            str(config["dataset_file"]), protocol, scenario_ids
        )
    WORKLOAD = WeightedScenarioCursor(protocol, scenarios, dataset_rows)
    METRICS.scenario_weights = {
        str(item["id"]): int(item.get("weight", 1)) for item in scenarios
    }


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    options = environment.parsed_options
    task_id = options.task_id or os.environ.get("TASK_ID", "unknown")
    rows = []
    for entry, stat in environment.stats.entries.items():
        name = stat.name if hasattr(stat, "name") else str(entry)
        if name != "Aggregated":
            rows.append(_stat_row(task_id, name, stat))
    if environment.stats.total:
        rows.append(_stat_row(task_id, "total", environment.stats.total))
    with open(options.config_file, "r", encoding="utf-8") as handle:
        protocol = json.load(handle)["protocol"]
    output = _result_file(task_id)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(
            {"locust_stats": rows, "custom_metrics": METRICS.summary(protocol)},
            handle,
            ensure_ascii=False,
            indent=2,
        )


class AgentProtocolUser(HttpUser):
    def wait_time(self):  # type: ignore[override]
        return 0

    def on_start(self) -> None:
        with open(
            self.environment.parsed_options.config_file, "r", encoding="utf-8"
        ) as handle:
            self.config = json.load(handle)
        self.protocol = self.config["protocol"]
        self.protocol_version = self.config["protocol_version"]
        self.endpoint = self.config["api_path"]
        self.a2a_binding = self.config.get("a2a_binding", "jsonrpc")
        self.headers = dict(self.config.get("headers") or {})
        self.request_timeout = float(self.config.get("request_timeout", 30))
        self.rpc_id = 0
        self.session_id: Optional[str] = None
        self.mcp_tools: dict[str, dict[str, Any]] = {}
        self.task_id = self.environment.parsed_options.task_id
        self._grpc_channel = None
        if self.protocol == "mcp":
            if self.config.get("token_count_path"):
                METRICS.increment("token_count_configured")
            try:
                if is_stateless_mcp(self.protocol_version):
                    self._mcp_discover()
                else:
                    self._mcp_initialize()
            except Exception as exc:
                METRICS.increment("failed_requests")
                raise StopUser() from exc

    def on_stop(self) -> None:
        self._close_grpc_channel()

    def _close_grpc_channel(self) -> None:
        channel = self._grpc_channel
        self._grpc_channel = None
        if channel is None:
            return
        try:
            channel.close()
        except Exception:
            logger.debug("error closing gRPC channel", exc_info=True)

    def _next_id(self) -> int:
        self.rpc_id += 1
        return self.rpc_id

    def _trace_headers(self) -> dict[str, str]:
        return {
            "traceparent": f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01",
            "X-LMeterX-Run-Id": self.task_id,
            "X-LMeterX-Request-Id": uuid.uuid4().hex,
        }

    def _read_response(
        self, response, started: float
    ) -> tuple[list[dict[str, Any]], float, float]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type.lower():
            content = response.content
            if content is None:
                # Locust can stop a user while a streamed response is still
                # being initialized.  In that case FastHttpSession exposes no
                # buffered body.  Treat it as a failed protocol response so
                # _post_rpc records the request failure instead of leaking an
                # AttributeError from the response parser.
                raise ValueError("response body was unavailable before completion")
            body = (
                content
                if isinstance(content, str)
                else content.decode(response.encoding or "utf-8", errors="replace")
            )
            elapsed = (time.perf_counter() - started) * 1000
            self._last_event_arrivals_ms = [elapsed]
            return parse_json_or_sse(content_type, body), elapsed, elapsed
        lines = []
        event_arrivals = []
        event_has_data = False
        first_ms: Optional[float] = None
        for raw_line in response.iter_lines(decode_unicode=True):
            line = (
                raw_line
                if isinstance(raw_line, str)
                else raw_line.decode("utf-8", errors="replace")
            )
            lines.append(line)
            if first_ms is None and line.startswith("data:") and line[5:].strip():
                first_ms = (time.perf_counter() - started) * 1000
            if line.startswith("data:") and line[5:].strip():
                event_has_data = True
            elif line == "" and event_has_data:
                event_arrivals.append((time.perf_counter() - started) * 1000)
                event_has_data = False
        elapsed = (time.perf_counter() - started) * 1000
        if event_has_data:
            event_arrivals.append(elapsed)
        self._last_event_arrivals_ms = event_arrivals
        return (
            parse_json_or_sse(content_type, "\n".join(lines)),
            first_ms or elapsed,
            elapsed,
        )

    def _post_rpc(
        self,
        method: str,
        params: dict[str, Any],
        metric_name: str,
        *,
        notification: bool = False,
        timeout: Optional[float] = None,
        include_protocol_version: bool = True,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> tuple[list[dict[str, Any]], float, float, int]:
        headers = {
            **self.headers,
            **self._trace_headers(),
            "Content-Type": "application/json",
        }
        if self.protocol == "mcp":
            headers["Accept"] = "application/json, text/event-stream"
            if is_stateless_mcp(self.protocol_version):
                params = dict(params)
                params["_meta"] = {
                    **mcp_request_metadata(self.protocol_version),
                    **(params.get("_meta") or {}),
                }
                headers.update(
                    {
                        "MCP-Protocol-Version": self.protocol_version,
                        "Mcp-Method": method,
                    }
                )
                if method in {"tools/call", "resources/read", "prompts/get"}:
                    name = params.get("name") or params.get("uri")
                    if name is not None:
                        headers["Mcp-Name"] = mcp_header_value(name)
            elif include_protocol_version:
                headers["MCP-Protocol-Version"] = self.protocol_version
            if self.session_id:
                headers["MCP-Session-Id"] = self.session_id
        else:
            headers.update(
                {
                    "Accept": "application/json, text/event-stream",
                    "A2A-Version": self.protocol_version,
                }
            )
        if extra_headers:
            headers.update(extra_headers)
        request_id = None if notification else self._next_id()
        body = jsonrpc_request(method, params, request_id)
        started = time.perf_counter()
        with self.client.post(
            self.endpoint,
            json=body,
            headers=headers,
            name=metric_name,
            timeout=timeout or self.request_timeout,
            catch_response=True,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"HTTP {response.status_code}")
                return (
                    [],
                    0.0,
                    (time.perf_counter() - started) * 1000,
                    response.status_code,
                )
            self.session_id = response.headers.get("mcp-session-id") or self.session_id
            if notification and response.status_code in {200, 202, 204}:
                response.success()
                return (
                    [],
                    0.0,
                    (time.perf_counter() - started) * 1000,
                    response.status_code,
                )
            try:
                messages, ttft, _ = self._read_response(response, started)
                elapsed = (time.perf_counter() - started) * 1000
                response.request_meta["response_time"] = elapsed
                for message in messages:
                    if message.get("jsonrpc") != "2.0":
                        raise ValueError("response is not JSON-RPC 2.0")
                    if message.get("error"):
                        raise ValueError(str(message["error"]))
                final = messages[-1]
                if request_id is not None and (
                    final.get("id") != request_id
                    or ("result" not in final and "error" not in final)
                ):
                    raise ValueError(
                        "final JSON-RPC response id does not match request"
                    )
                response.success()
                return messages, ttft, elapsed, response.status_code
            except (ValueError, json.JSONDecodeError) as exc:
                response.failure(str(exc))
                return (
                    [],
                    0.0,
                    (time.perf_counter() - started) * 1000,
                    response.status_code,
                )

    def _post_rest(
        self,
        rest_path: str,
        body: dict[str, Any],
        metric_name: str,
        *,
        timeout: Optional[float] = None,
    ) -> tuple[list[dict[str, Any]], float, float, int]:
        """HTTP+JSON (REST) binding – POST directly without JSON-RPC envelope."""
        headers = {
            **self.headers,
            **self._trace_headers(),
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "A2A-Version": self.protocol_version,
        }
        endpoint = self.endpoint.rstrip("/") + rest_path
        started = time.perf_counter()
        with self.client.post(
            endpoint,
            json=body,
            headers=headers,
            name=metric_name,
            timeout=timeout or self.request_timeout,
            catch_response=True,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                response.failure(f"HTTP {response.status_code}")
                return (
                    [],
                    0.0,
                    (time.perf_counter() - started) * 1000,
                    response.status_code,
                )
            try:
                messages, ttft, _ = self._read_response(response, started)
                elapsed = (time.perf_counter() - started) * 1000
                response.request_meta["response_time"] = elapsed
                response.success()
                return messages, ttft, elapsed, response.status_code
            except (ValueError, json.JSONDecodeError) as exc:
                response.failure(str(exc))
                return (
                    [],
                    0.0,
                    (time.perf_counter() - started) * 1000,
                    response.status_code,
                )

    def _post_grpc(
        self,
        method: str,
        params: dict[str, Any],
        metric_name: str,
        *,
        timeout: Optional[float] = None,
    ) -> tuple[list[dict[str, Any]], float, float, int]:
        """gRPC binding – call A2AService/{method} via grpcio."""
        try:
            import grpc  # type: ignore[import-untyped]
        except ImportError:
            logger.error("grpcio not installed; gRPC binding unavailable")
            return [], 0.0, 0.0, 500

        if self._grpc_channel is None:
            host = self.client.base_url
            target = (
                str(host).replace("http://", "").replace("https://", "").rstrip("/")
            )
            self._grpc_channel = grpc.insecure_channel(target)
            try:
                grpc.channel_ready_future(self._grpc_channel).result(timeout=10)
            except grpc.FutureTimeoutError:
                logger.error("gRPC channel not ready after 10s")
                self._grpc_channel = None
                return [], 0.0, 0.0, 503

        full_method = f"/a2a.A2AService/{method}"
        request_bytes = json.dumps(params).encode("utf-8")
        started = time.perf_counter()
        try:
            response_bytes = self._grpc_channel.unary_unary(
                full_method,
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x,
            )(request_bytes, timeout=timeout or self.request_timeout)
            elapsed = (time.perf_counter() - started) * 1000
            response_data = json.loads(response_bytes)
            events.request.fire(
                request_type="gRPC",
                name=metric_name,
                response_time=elapsed,
                response_length=len(response_bytes),
                exception=None,
            )
            return [response_data], elapsed, elapsed, 200
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            events.request.fire(
                request_type="gRPC",
                name=metric_name,
                response_time=elapsed,
                response_length=0,
                exception=exc,
            )
            return [], 0.0, elapsed, 500

    def _mcp_initialize(self) -> None:
        messages, _, _, status = self._post_rpc(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "LMeterX", "version": "1.0"},
            },
            "MCP initialize",
            include_protocol_version=False,
        )
        if status >= 400 or not messages:
            raise RuntimeError("MCP initialize failed")
        negotiated = rpc_payload(messages[-1]).get("protocolVersion")
        if negotiated:
            self.protocol_version = str(negotiated)
        self._post_rpc(
            "notifications/initialized",
            {},
            "MCP notifications/initialized",
            notification=True,
        )

    def _mcp_discover(self) -> None:
        cursor: Optional[str] = None
        for _ in range(100):
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            messages, _, _, status = self._post_rpc(
                "tools/list", params, "MCP tools/list"
            )
            if status >= 400 or not messages:
                raise RuntimeError("MCP tools/list failed")
            result = rpc_payload(messages[-1])
            if result.get("resultType") != "complete":
                raise RuntimeError("MCP tools/list did not return a complete result")
            for tool in result.get("tools") or []:
                if isinstance(tool, dict) and tool.get("name"):
                    try:
                        mcp_parameter_headers(tool.get("inputSchema") or {}, {})
                    except ValueError as exc:
                        logger.warning(
                            "Ignoring invalid MCP tool %s: %s", tool["name"], exc
                        )
                        continue
                    self.mcp_tools[str(tool["name"])] = tool
            cursor = result.get("nextCursor")
            if not cursor:
                break
        configured = {
            str(item.get("tool_name")) for item in self.config.get("mcp_calls") or []
        }
        missing = sorted(configured - set(self.mcp_tools))
        if missing:
            raise RuntimeError(f"MCP tools not found: {', '.join(missing)}")

    @task
    def protocol_request(self) -> None:
        if self.protocol == "mcp":
            self._mcp_call()
        else:
            self._a2a_call()

    def _mcp_call(self) -> None:
        if WORKLOAD is None:
            raise StopUser()
        case = WORKLOAD.next()
        METRICS.increment(f"scenario_selected:{case['id']}")
        if case.get("dataset_row_id"):
            METRICS.increment(f"dataset_row_selected:{case['dataset_row_id']}")
        METRICS.increment("top_level_requests")
        arguments = case.get("arguments") or {}
        parameter_headers: dict[str, str] = {}
        if is_stateless_mcp(self.protocol_version):
            tool = self.mcp_tools.get(str(case["tool_name"])) or {}
            parameter_headers = mcp_parameter_headers(
                tool.get("inputSchema") or {}, arguments
            )
        METRICS.increment("mcp_tool_calls")
        messages, ttfe, elapsed, status = self._post_rpc(
            "tools/call",
            {"name": case["tool_name"], "arguments": arguments},
            f"MCP tools/call [{case['name']}]",
            extra_headers=parameter_headers,
        )
        METRICS.increment("mcp_completed_tool_calls")
        METRICS.sample("mcp_e2e_ms", elapsed)
        # MCP streamable HTTP has no separate token stream: first event == TTFT.
        if ttfe > 0:
            METRICS.sample("mcp_ttfe_ms", ttfe)
            METRICS.sample("mcp_ttft_ms", ttfe)
        if status == 404 and self.session_id:
            self.session_id = None
            self._mcp_initialize()
            METRICS.increment("mcp_tool_calls")
            messages, ttfe, elapsed, status = self._post_rpc(
                "tools/call",
                {"name": case["tool_name"], "arguments": arguments},
                f"MCP tools/call [{case['name']}]",
                extra_headers=parameter_headers,
            )
            METRICS.increment("mcp_completed_tool_calls")
            METRICS.sample("mcp_e2e_ms", elapsed)
            if ttfe > 0:
                METRICS.sample("mcp_ttfe_ms", ttfe)
                METRICS.sample("mcp_ttft_ms", ttfe)
        success = bool(messages) and status < 400
        result_payload: dict[str, Any] = {}
        if success:
            try:
                result_payload = rpc_payload(messages[-1])
                result_type = result_payload.get("resultType")
                expected_result_types = (
                    {"complete"}
                    if is_stateless_mcp(self.protocol_version)
                    else {None, "complete"}
                )
                success = (
                    not bool(result_payload.get("isError"))
                    and result_type in expected_result_types
                )
                if result_type == "input_required":
                    METRICS.increment("mcp_input_required")
            except ValueError:
                success = False
        if success:
            METRICS.increment("mcp_tool_successes")
            METRICS.increment("content_bytes", mcp_content_bytes(messages[-1]))
            measured_tokens, token_observable = token_count_observation(
                messages[-1], self.config.get("token_count_path")
            )
            if token_observable:
                METRICS.increment("tokens", measured_tokens)
                METRICS.increment("token_measurements")
        else:
            METRICS.increment("failed_requests")

    def _a2a_call(self) -> None:
        if WORKLOAD is None:
            raise StopUser()
        case = WORKLOAD.next()
        METRICS.increment(f"scenario_selected:{case['id']}")
        if case.get("dataset_row_id"):
            METRICS.increment(f"dataset_row_selected:{case['dataset_row_id']}")
        mode = self.config.get("a2a_mode", "async_poll")
        METRICS.increment("top_level_requests")
        METRICS.increment("submissions")
        METRICS.increment("a2a_request_attempts")
        started = time.perf_counter()
        method = "SendStreamingMessage" if mode == "stream" else "SendMessage"
        params = a2a_message_request(
            case["message"],
            return_immediately=mode == "async_poll",
            tenant=self.config.get("a2a_tenant"),
        )
        binding = self.a2a_binding
        task_timeout = (
            float(self.config.get("task_timeout", 300)) if mode == "stream" else None
        )
        metric_label = f"A2A {method} [{case['name']}]"
        if binding == "http_json":
            rest_path = A2A_REST_METHODS.get(method, "/message:send")
            messages, first_event, submit_elapsed, status = self._post_rest(
                rest_path,
                params,
                metric_label,
                timeout=task_timeout,
            )
        elif binding == "grpc":
            messages, first_event, submit_elapsed, status = self._post_grpc(
                method,
                params,
                metric_label,
                timeout=task_timeout,
            )
        else:
            messages, first_event, submit_elapsed, status = self._post_rpc(
                method,
                params,
                metric_label,
                timeout=task_timeout,
            )
        if status >= 400 or not is_a2a_send_response(messages):
            METRICS.increment("failed_requests")
            METRICS.increment("a2a_request_failures")
            return
        METRICS.increment("submission_successes")
        if first_event:
            METRICS.sample("a2a_ttfe_ms", first_event)
        cascade_cumulative = 0
        cascade_delta = 0
        cascade_observable = False
        for message in messages:
            cumulative, delta, observable = mcp_call_observation(
                message, self.config.get("cascade_count_paths") or []
            )
            cascade_cumulative = max(cascade_cumulative, cumulative)
            cascade_delta += delta
            cascade_observable = cascade_observable or observable
        cascade = max(cascade_cumulative, cascade_delta)
        if mode == "stream":
            self._record_stream_transitions(messages)
        task_id = next(
            (a2a_task_id(message) for message in messages if a2a_task_id(message)), None
        )
        state = next(
            (
                a2a_task_state(message)
                for message in reversed(messages)
                if a2a_task_state(message)
            ),
            None,
        )
        if mode != "stream" and state and state != "submitted":
            METRICS.transition("submitted", state, submit_elapsed)
        if mode == "async_poll" and task_id and state not in A2A_TERMINAL_STATES:
            state, observed, poll_observable = self._poll_a2a_task(
                task_id, case["name"], state, started
            )
            cascade = max(cascade, observed)
            cascade_observable = cascade_observable or poll_observable
        if cascade_observable:
            METRICS.increment("observed_mcp_calls", cascade)
            METRICS.increment("cascade_observable_requests")
        if state:
            METRICS.increment(f"state_{state}")
        if state in A2A_TERMINAL_STATES:
            METRICS.increment("terminal_tasks")
            if state == "completed":
                METRICS.increment("completed_tasks")
            else:
                METRICS.increment("failed_requests")
                if state == "failed":
                    METRICS.increment("failed_tasks")
            e2e_ms = (time.perf_counter() - started) * 1000
            METRICS.sample("a2a_e2e_ms", e2e_ms)
            events.request.fire(
                request_type="A2A_TASK",
                name=f"A2A end-to-end [{case['name']}]",
                response_time=e2e_ms,
                response_length=0,
                exception=(
                    None
                    if state == "completed"
                    else RuntimeError(f"terminal state: {state}")
                ),
            )
        elif state in A2A_INTERRUPTED_STATES:
            METRICS.increment("failed_requests")

    def _record_stream_transitions(self, messages: list[dict[str, Any]]) -> None:
        previous = "submitted"
        previous_at = 0.0
        arrivals = getattr(self, "_last_event_arrivals_ms", [])
        for index, message in enumerate(messages):
            state = a2a_task_state(message)
            if not state:
                continue
            observed_at = arrivals[index] if index < len(arrivals) else previous_at
            if state != previous:
                METRICS.transition(previous, state, max(0.0, observed_at - previous_at))
                previous = state
            previous_at = observed_at

    def _poll_a2a_task(
        self, task_id: str, case_name: str, initial_state: Optional[str], started: float
    ) -> tuple[Optional[str], int, bool]:
        deadline = time.perf_counter() + float(self.config.get("task_timeout", 300))
        interval = float(self.config.get("poll_interval", 1))
        previous = initial_state or "submitted"
        previous_at = time.perf_counter()
        observed = 0
        observable = False
        while time.perf_counter() < deadline:
            gevent.sleep(interval)
            params = {"id": task_id}
            if self.config.get("a2a_tenant") is not None:
                params["tenant"] = self.config["a2a_tenant"]
            METRICS.increment("a2a_request_attempts")
            poll_label = f"A2A GetTask [{case_name}]"
            if self.a2a_binding == "http_json":
                messages, _, _, status = self._post_rest(
                    f"/tasks/{task_id}",
                    {},
                    poll_label,
                )
            elif self.a2a_binding == "grpc":
                messages, _, _, status = self._post_grpc(
                    "GetTask",
                    params,
                    poll_label,
                )
            else:
                messages, _, _, status = self._post_rpc(
                    "GetTask",
                    params,
                    poll_label,
                )
            if status >= 400 or not messages:
                METRICS.increment("a2a_request_failures")
                continue
            state = a2a_task_state(messages[-1]) or previous
            if state != previous:
                now = time.perf_counter()
                METRICS.transition(previous, state, (now - previous_at) * 1000)
                previous, previous_at = state, now
            cumulative, _, current_observable = mcp_call_observation(
                messages[-1], self.config.get("cascade_count_paths") or []
            )
            observed = max(observed, cumulative)
            observable = observable or current_observable
            if state in A2A_TERMINAL_STATES or state in A2A_INTERRUPTED_STATES:
                return state, observed, observable
        METRICS.increment("failed_requests")
        METRICS.sample("a2a_e2e_ms", (time.perf_counter() - started) * 1000)
        return "timeout", observed, observable
