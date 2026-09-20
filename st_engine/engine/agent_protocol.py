"""Protocol helpers shared by the MCP/A2A Locust workload and tests."""

from __future__ import annotations

import base64
import json
import math
import re
import threading
import uuid
from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable, Optional

A2A_TERMINAL_STATES = {"completed", "failed", "canceled", "cancelled", "rejected"}
A2A_INTERRUPTED_STATES = {"input_required", "auth_required"}
MCP_STATELESS_VERSION = "2026-07-28"
_MCP_HEADER_NAME = re.compile(r"^[\x21-\x39\x3b-\x7e]+$")


def is_stateless_mcp(version: str) -> bool:
    return str(version or "") >= MCP_STATELESS_VERSION


def mcp_request_metadata(protocol_version: str) -> dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": protocol_version,
        "io.modelcontextprotocol/clientInfo": {"name": "LMeterX", "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def _dataset_metadata(record: dict[str, Any], line_number: int) -> None:
    for field in ("id", "scenario_id"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"dataset line {line_number} requires a non-empty {field}")
    if "weight" in record:
        raise ValueError(
            f"dataset line {line_number} must not define weight; "
            "configure weight on the business scenario"
        )


def _a2a_dataset_record(record: dict[str, Any], line_number: int) -> None:
    _dataset_metadata(record, line_number)
    allowed = {"id", "scenario_id", "message"}
    unknown = set(record) - allowed
    if unknown:
        raise ValueError(
            f"dataset line {line_number} contains unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    message = record.get("message")
    if not isinstance(message, dict):
        raise ValueError(f"dataset line {line_number} requires an A2A message object")
    if message.get("role", "ROLE_USER") != "ROLE_USER":
        raise ValueError(f"dataset line {line_number} message.role must be ROLE_USER")
    parts = message.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError(f"dataset line {line_number} message.parts must not be empty")
    for part_index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(
                f"dataset line {line_number} message.parts[{part_index}] must be an object"
            )
        content_fields = {"text", "data", "raw", "url"}.intersection(part)
        if len(content_fields) != 1:
            raise ValueError(
                f"dataset line {line_number} message.parts[{part_index}] must contain "
                "exactly one of text, data, raw, or url"
            )


def _mcp_dataset_record(record: dict[str, Any], line_number: int) -> None:
    _dataset_metadata(record, line_number)
    allowed = {"id", "scenario_id", "arguments"}
    unknown = set(record) - allowed
    if unknown:
        raise ValueError(
            f"dataset line {line_number} contains unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    arguments = record.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError(f"dataset line {line_number} arguments must be an object")


def load_protocol_dataset(
    path: str, protocol: str, scenario_ids: set[str]
) -> dict[str, list[dict[str, Any]]]:
    """Load JSONL rows grouped by their configured business scenario."""
    if not path:
        raise ValueError("dataset_file is required")
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"dataset line {line_number} is not valid JSON: {exc.msg}"
                    ) from exc
                if not isinstance(value, dict):
                    raise ValueError(
                        f"dataset line {line_number} must be a JSON object"
                    )
                if protocol == "a2a":
                    _a2a_dataset_record(value, line_number)
                elif protocol == "mcp":
                    _mcp_dataset_record(value, line_number)
                else:
                    raise ValueError(f"unsupported agent protocol: {protocol}")
                scenario_id = str(value["scenario_id"])
                if scenario_id not in scenario_ids:
                    raise ValueError(
                        f"dataset line {line_number} references unknown scenario_id "
                        f"{scenario_id!r}"
                    )
                records[scenario_id].append(value)
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"unable to read protocol dataset: {exc}") from exc
    if not records:
        raise ValueError("dataset must contain at least one JSONL record")
    missing = sorted(scenario_ids - set(records))
    if missing:
        raise ValueError(
            "dataset has no rows for configured scenarios: " + ", ".join(missing)
        )
    return dict(records)


class WeightedScenarioCursor:
    """Select scenarios by smooth weight, then rows within each scenario in order."""

    def __init__(
        self,
        protocol: str,
        scenarios: list[dict[str, Any]],
        dataset_rows: Optional[dict[str, list[dict[str, Any]]]] = None,
    ) -> None:
        if not scenarios:
            raise ValueError("at least one business scenario is required")
        self.protocol = protocol
        self.scenarios = [deepcopy(item) for item in scenarios]
        self.dataset_rows = dataset_rows or {}
        self._lock = threading.Lock()
        self._current: dict[str, int] = {}
        self._row_indices: dict[str, int] = defaultdict(int)
        self._total_weight = 0
        seen: set[str] = set()
        for scenario in self.scenarios:
            scenario_id = str(scenario.get("id") or "")
            weight = scenario.get("weight", 1)
            if not scenario_id or scenario_id in seen:
                raise ValueError("business scenario ids must be non-empty and unique")
            if (
                isinstance(weight, bool)
                or not isinstance(weight, int)
                or not 1 <= weight <= 100
            ):
                raise ValueError(
                    f"business scenario {scenario_id!r} has an invalid weight"
                )
            seen.add(scenario_id)
            self._current[scenario_id] = 0
            self._total_weight += weight

    def next(self) -> dict[str, Any]:
        with self._lock:
            selected: Optional[dict[str, Any]] = None
            selected_score: Optional[int] = None
            for scenario in self.scenarios:
                scenario_id = str(scenario["id"])
                self._current[scenario_id] += int(scenario.get("weight", 1))
                score = self._current[scenario_id]
                if selected is None or score > int(selected_score or 0):
                    selected = scenario
                    selected_score = score
            assert selected is not None
            scenario_id = str(selected["id"])
            self._current[scenario_id] -= self._total_weight
            rows = self.dataset_rows.get(scenario_id) or []
            row = None
            if rows:
                row_index = self._row_indices[scenario_id] % len(rows)
                self._row_indices[scenario_id] += 1
                row = rows[row_index]

        result = deepcopy(selected)
        if row:
            result["dataset_row_id"] = row["id"]
            if self.protocol == "a2a":
                result["message"] = deepcopy(row["message"])
            else:
                result["arguments"] = deepcopy(row.get("arguments") or {})
        return result


def mcp_header_value(value: Any) -> str:
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    else:
        rendered = str(value)
    plain = all(0x20 <= ord(char) <= 0x7E for char in rendered)
    sentinel = rendered.startswith("=?base64?") and rendered.endswith("?=")
    if plain and rendered == rendered.strip() and not sentinel:
        return rendered
    encoded = base64.b64encode(rendered.encode("utf-8")).decode("ascii")
    return f"=?base64?{encoded}?="


def mcp_parameter_headers(
    input_schema: dict[str, Any], arguments: dict[str, Any]
) -> dict[str, str]:
    """Mirror 2026-07-28 x-mcp-header arguments into safe HTTP headers."""
    output: dict[str, str] = {}
    seen: set[str] = set()

    def visit(schema: Any, value: Any) -> None:
        if not isinstance(schema, dict):
            return
        annotation = schema.get("x-mcp-header")
        if annotation is not None:
            name = str(annotation)
            lowered = name.lower()
            if not name or not _MCP_HEADER_NAME.fullmatch(name) or lowered in seen:
                raise ValueError(f"invalid or duplicate x-mcp-header: {name!r}")
            value_type = schema.get("type")
            if value_type not in {"string", "number", "integer", "boolean"}:
                raise ValueError(
                    f"x-mcp-header {name!r} must annotate a primitive value"
                )
            seen.add(lowered)
            if value is not None:
                if value_type == "string" and not isinstance(value, str):
                    raise ValueError(f"x-mcp-header {name!r} requires a string")
                if value_type == "boolean" and not isinstance(value, bool):
                    raise ValueError(f"x-mcp-header {name!r} requires a boolean")
                if value_type == "number" and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError(f"x-mcp-header {name!r} requires a number")
                if value_type == "integer" and (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or abs(value) > 9_007_199_254_740_991
                ):
                    raise ValueError(f"x-mcp-header {name!r} has an unsafe integer")
                output[f"Mcp-Param-{name}"] = mcp_header_value(value)

        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                child_value = value.get(key) if isinstance(value, dict) else None
                visit(child_schema, child_value)

    visit(input_schema, arguments)
    return output


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def sample_summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "avg": 0.0,
            "min": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    return {
        "count": len(values),
        "avg": sum(values) / len(values),
        "min": min(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "max": max(values),
    }


def jsonrpc_request(
    method: str, params: dict[str, Any], request_id: Any = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
    if request_id is not None:
        body["id"] = request_id
    return body


A2A_REST_METHODS: dict[str, str] = {
    "SendMessage": "/message:send",
    "SendStreamingMessage": "/message:stream",
    "GetTask": "/tasks",
}


def a2a_message_request(
    message: dict[str, Any],
    *,
    return_immediately: bool,
    accepted_output_modes: Optional[list[str]] = None,
    tenant: Optional[str] = None,
) -> dict[str, Any]:
    normalized = dict(message)
    normalized.setdefault("messageId", str(uuid.uuid4()))
    normalized.setdefault("role", "ROLE_USER")
    configuration: dict[str, Any] = {"returnImmediately": return_immediately}
    if accepted_output_modes:
        configuration["acceptedOutputModes"] = accepted_output_modes
    request: dict[str, Any] = {
        "message": normalized,
        "configuration": configuration,
    }
    if tenant is not None:
        request["tenant"] = tenant
    return request


def parse_json_or_sse(content_type: str, body: str) -> list[dict[str, Any]]:
    """Parse JSON or all JSON payloads from a completed SSE response."""
    if "text/event-stream" not in (content_type or "").lower():
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError("response is not a JSON object")
        return [value]
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []
    for raw_line in body.splitlines() + [""]:
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                value = json.loads("\n".join(data_lines))
                if isinstance(value, dict):
                    messages.append(value)
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not messages:
        raise ValueError("SSE stream did not contain a JSON message")
    return messages


def rpc_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("jsonrpc") == "2.0":
        error = payload.get("error")
        if error:
            if isinstance(error, dict):
                raise ValueError(
                    str(error.get("message") or error.get("code") or "JSON-RPC error")
                )
            raise ValueError(str(error))
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("JSON-RPC response has no object result")
        return result
    return payload


def normalize_a2a_state(value: Any) -> Optional[str]:
    if value is None:
        return None
    state = str(value).strip().lower().replace("-", "_")
    return re.sub(r"^task_state_", "", state) or None


def _records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _records(child)


def a2a_task_id(payload: dict[str, Any]) -> Optional[str]:
    try:
        payload = rpc_payload(payload)
    except ValueError:
        return None
    for record in _records(payload):
        kind = str(record.get("kind") or "").lower()
        if kind == "task" or "status" in record or "taskId" in record:
            value = record.get("id") or record.get("taskId")
            if value:
                return str(value)
    return None


def a2a_task_state(payload: dict[str, Any]) -> Optional[str]:
    try:
        payload = rpc_payload(payload)
    except ValueError:
        return None
    for record in _records(payload):
        status = record.get("status")
        if isinstance(status, dict) and status.get("state") is not None:
            return normalize_a2a_state(status.get("state"))
        if record.get("state") is not None and (
            "taskId" in record
            or str(record.get("kind", "")).lower().endswith("status-update")
        ):
            return normalize_a2a_state(record.get("state"))
    return None


def is_a2a_send_response(messages: list[dict[str, Any]]) -> bool:
    """Validate the wrapper union used by A2A 1.0 send responses."""
    if not messages:
        return False
    recognized = {"task", "message", "statusUpdate", "artifactUpdate"}
    has_initial_result = False
    for message in messages:
        try:
            result = rpc_payload(message)
        except ValueError:
            return False
        wrappers = recognized.intersection(result)
        if not wrappers:
            return False
        if wrappers.intersection({"task", "message"}):
            has_initial_result = True
    return has_initial_result


def resolve_path(value: Any, path: str) -> Any:
    current = value
    for part in [item for item in path.split(".") if item]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def _count_value(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return 1
    return 0


def mcp_call_observation(
    payload: Any, configured_paths: list[str]
) -> tuple[int, int, bool]:
    """Return (cumulative_count, event_delta, observable).

    Metadata counters/lists are treated as cumulative snapshots. Explicit MCP
    start events are deltas. Keeping them separate prevents SSE snapshots such
    as 1, 2, 3 from being incorrectly summed to 6.
    """
    cumulative: list[int] = []
    observable = False
    for path in configured_paths:
        value = resolve_path(payload, path)
        if value is not None:
            observable = True
            cumulative.append(_count_value(value))

    event_delta = 0
    recognized = {"mcp_call_count", "mcpCallCount", "mcp_tool_calls", "mcpToolCalls"}
    for record in _records(payload):
        for key in recognized.intersection(record):
            observable = True
            cumulative.append(_count_value(record[key]))
        protocol = str(
            record.get("protocol") or record.get("tool_protocol") or ""
        ).lower()
        event = str(record.get("agno_event_type") or record.get("event") or "").lower()
        if protocol == "mcp" and event in {
            "tool_call_started",
            "mcp_tool_call_started",
        }:
            observable = True
            event_delta += 1
    return max(cumulative, default=0), event_delta, observable


def observed_mcp_call_count(payload: Any, configured_paths: list[str]) -> int:
    """Return MCP calls explicitly exposed by A2A metadata.

    A2A keeps agent internals opaque, so this intentionally does not count every
    generic tool event. Targets can expose a cumulative count/list through a
    configured metadata path or one of the recognized MCP-specific keys.
    """
    cumulative, delta, _ = mcp_call_observation(payload, configured_paths)
    return max(cumulative, delta)


def token_count(payload: Any, configured_path: Optional[str]) -> int:
    if not configured_path:
        return 0
    return _count_value(resolve_path(payload, configured_path))


def token_count_observation(
    payload: Any, configured_path: Optional[str]
) -> tuple[int, bool]:
    if not configured_path:
        return 0, False
    value = resolve_path(payload, configured_path)
    return _count_value(value), value is not None


def mcp_content_bytes(payload: dict[str, Any]) -> int:
    try:
        result = rpc_payload(payload)
    except ValueError:
        return 0
    return len(
        json.dumps(result.get("content", []), ensure_ascii=False).encode("utf-8")
    )
