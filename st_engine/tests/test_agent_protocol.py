import pytest

from engine.agent_protocol import (
    WeightedScenarioCursor,
    a2a_message_request,
    a2a_task_id,
    a2a_task_state,
    is_a2a_send_response,
    load_protocol_dataset,
    mcp_call_observation,
    mcp_header_value,
    mcp_parameter_headers,
    mcp_request_metadata,
    observed_mcp_call_count,
    parse_json_or_sse,
    sample_summary,
    token_count,
    token_count_observation,
)


def test_builds_a2a_v1_message_configuration_without_changing_parts():
    message = {"role": "ROLE_USER", "parts": [{"text": "hello"}]}
    params = a2a_message_request(message, return_immediately=True, tenant="tenant-a")
    assert params["message"]["parts"] == [{"text": "hello"}]
    assert params["message"]["messageId"]
    assert params["configuration"]["returnImmediately"] is True
    assert "acceptedOutputModes" not in params["configuration"]
    assert params["tenant"] == "tenant-a"


def test_extracts_task_from_send_message_response_and_get_task():
    sent = {
        "jsonrpc": "2.0",
        "id": "1",
        "result": {
            "task": {
                "id": "task-1",
                "status": {"state": "TASK_STATE_SUBMITTED"},
            }
        },
    }
    assert a2a_task_id(sent) == "task-1"
    assert a2a_task_state(sent) == "submitted"
    assert is_a2a_send_response([sent]) is True
    assert (
        is_a2a_send_response(
            [{"jsonrpc": "2.0", "id": "1", "result": {"unexpected": {}}}]
        )
        is False
    )


def test_parses_every_stream_event_and_terminal_state():
    body = (
        'data: {"jsonrpc":"2.0","id":"1","result":{"task":{"id":"t1",'
        '"status":{"state":"TASK_STATE_WORKING"}}}}\n\n'
        'data: {"jsonrpc":"2.0","id":"1","result":{"statusUpdate":{"taskId":"t1",'
        '"status":{"state":"TASK_STATE_COMPLETED"}}}}\n\n'
    )
    events = parse_json_or_sse("text/event-stream", body)
    assert len(events) == 2
    assert a2a_task_state(events[-1]) == "completed"


def test_cascade_count_only_uses_explicit_mcp_observability():
    payload = {
        "result": {
            "statusUpdate": {
                "metadata": {
                    "mcp_call_count": 4,
                    "generic_tools": [1, 2, 3, 4, 5],
                }
            }
        }
    }
    assert observed_mcp_call_count(payload, []) == 4
    assert observed_mcp_call_count({"metadata": {"generic_tools": [1, 2]}}, []) == 0


def test_cascade_count_supports_configured_metadata_path():
    payload = {"result": {"task": {"metadata": {"vendor": {"calls": [{}, {}, {}]}}}}}
    assert observed_mcp_call_count(payload, ["result.task.metadata.vendor.calls"]) == 3


def test_cascade_observation_distinguishes_zero_from_missing_and_events():
    assert mcp_call_observation({"metadata": {"mcp_call_count": 0}}, []) == (
        0,
        0,
        True,
    )
    assert mcp_call_observation({"metadata": {}}, []) == (0, 0, False)
    event = {"protocol": "mcp", "event": "tool_call_started"}
    assert mcp_call_observation(event, []) == (0, 1, True)


def test_tps_requires_explicit_count_path():
    payload = {"result": {"usage": {"outputTokens": 42}}}
    assert token_count(payload, None) == 0
    assert token_count(payload, "result.usage.outputTokens") == 42
    assert token_count_observation(payload, "result.usage.outputTokens") == (42, True)
    assert token_count_observation(payload, "result.usage.missing") == (0, False)


def test_mcp_2026_request_metadata_and_header_encoding():
    metadata = mcp_request_metadata("2026-07-28")
    assert metadata["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert mcp_header_value("search") == "search"
    assert mcp_header_value("上海").startswith("=?base64?")
    assert mcp_header_value("a\tb").startswith("=?base64?")


def test_mcp_2026_mirrors_x_mcp_header_values():
    schema = {
        "type": "object",
        "properties": {
            "region": {"type": "string", "x-mcp-header": "Region"},
            "nested": {
                "type": "object",
                "properties": {
                    "approved": {"type": "boolean", "x-mcp-header": "Approved"}
                },
            },
        },
    }
    assert mcp_parameter_headers(
        schema, {"region": "us-west1", "nested": {"approved": True}}
    ) == {"Mcp-Param-Region": "us-west1", "Mcp-Param-Approved": "true"}


def test_mcp_header_schema_is_validated_even_when_nested_argument_is_absent():
    schema = {
        "type": "object",
        "properties": {
            "nested": {
                "type": "object",
                "properties": {"value": {"type": "array", "x-mcp-header": "Invalid"}},
            }
        },
    }
    with pytest.raises(ValueError, match="primitive"):
        mcp_parameter_headers(schema, {})


def test_mcp_header_supports_finite_numbers_and_rejects_type_mismatch():
    schema = {
        "type": "object",
        "properties": {"score": {"type": "number", "x-mcp-header": "Score"}},
    }
    assert mcp_parameter_headers(schema, {"score": 1.5}) == {"Mcp-Param-Score": "1.5"}
    with pytest.raises(ValueError, match="number"):
        mcp_parameter_headers(schema, {"score": "high"})


def test_metric_summary_percentiles():
    summary = sample_summary([10, 20, 30, 40])
    assert summary["count"] == 4
    assert summary["avg"] == 25
    assert summary["p95"] == pytest.approx(38.5)


def test_loads_weighted_a2a_jsonl_dataset(tmp_path):
    dataset = tmp_path / "a2a.jsonl"
    dataset.write_text(
        '{"id":"order-1","scenario_id":"order",'
        '"message":{"role":"ROLE_USER","parts":[{"text":"hello"}]}}\n',
        encoding="utf-8",
    )
    records = load_protocol_dataset(str(dataset), "a2a", {"order"})
    assert records["order"][0]["id"] == "order-1"
    assert records["order"][0]["message"]["parts"][0]["text"] == "hello"


def test_loads_weighted_mcp_jsonl_dataset(tmp_path):
    dataset = tmp_path / "mcp.jsonl"
    dataset.write_text(
        '{"id":"weather-1","scenario_id":"weather",'
        '"arguments":{"city":"Shanghai"}}\n',
        encoding="utf-8",
    )
    records = load_protocol_dataset(str(dataset), "mcp", {"weather"})
    assert records["weather"][0]["arguments"]["city"] == "Shanghai"


def test_rejects_invalid_protocol_jsonl_record(tmp_path):
    dataset = tmp_path / "invalid.jsonl"
    dataset.write_text(
        '{"id":"weather-1","scenario_id":"weather","weight":2,' '"arguments":{}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="weight"):
        load_protocol_dataset(str(dataset), "mcp", {"weather"})


def test_smooth_weighted_scenarios_and_per_scenario_rows_are_deterministic():
    cursor = WeightedScenarioCursor(
        "mcp",
        [
            {
                "id": "weather",
                "name": "Weather",
                "weight": 3,
                "tool_name": "get_weather",
                "arguments": {},
            },
            {
                "id": "route",
                "name": "Route",
                "weight": 1,
                "tool_name": "plan_route",
                "arguments": {},
            },
        ],
        {
            "weather": [
                {"id": "w1", "scenario_id": "weather", "arguments": {"city": "A"}},
                {"id": "w2", "scenario_id": "weather", "arguments": {"city": "B"}},
            ],
            "route": [{"id": "r1", "scenario_id": "route", "arguments": {"to": "C"}}],
        },
    )
    selected = [cursor.next() for _ in range(8)]
    assert [item["id"] for item in selected].count("weather") == 6
    assert [item["id"] for item in selected].count("route") == 2
    weather_rows = [
        item["dataset_row_id"] for item in selected if item["id"] == "weather"
    ]
    assert weather_rows == ["w1", "w2", "w1", "w2", "w1", "w2"]
