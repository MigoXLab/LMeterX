import pytest

from engine.agent_locustfile import AgentProtocolUser, ProtocolMetrics


def test_missing_response_body_is_a_protocol_error_not_an_attribute_error():
    user = object.__new__(AgentProtocolUser)
    response = type(
        "Response",
        (),
        {"headers": {"content-type": "application/json"}, "content": None},
    )()

    with pytest.raises(ValueError, match="response body was unavailable"):
        user._read_response(response, 0.0)


def test_protocol_summary_exposes_selected_dataset_rows():
    metrics = ProtocolMetrics()
    metrics.increment("scenario_selected:wiki", 3)
    metrics.increment("dataset_row_selected:wiki-python-sdk", 2)
    metrics.increment("dataset_row_selected:wiki-typescript-sdk")

    summary = metrics.summary("mcp")

    assert summary["scenario_selections"] == {"wiki": 3}
    assert summary["dataset_row_selections"] == {
        "wiki-python-sdk": 2,
        "wiki-typescript-sdk": 1,
    }


def test_mcp_summary_uses_distinct_received_completed_and_successful_rates():
    metrics = ProtocolMetrics()
    metrics.increment("mcp_tool_calls", 4)
    metrics.increment("mcp_completed_tool_calls", 3)
    metrics.increment("mcp_tool_successes", 2)
    metrics.increment("content_bytes", 1200)
    metrics.sample("mcp_ttfe_ms", 20)
    metrics.sample("mcp_ttft_ms", 20)
    metrics.sample("mcp_e2e_ms", 80)

    summary = metrics.summary("mcp")

    assert summary["tool_call_success_rate"] == 0.5
    assert summary["completed_tool_calls"] == 3
    assert summary["tool_call_request_rate"] == summary["tool_call_rps"]
    assert summary["tool_call_throughput"] == summary["completion_throughput"]
    assert (
        summary["successful_tool_call_throughput"] == summary["successful_throughput"]
    )
    assert summary["tool_call_rps"] > summary["completion_throughput"]
    assert summary["completion_throughput"] > summary["successful_throughput"]
    assert summary["completion_throughput"] == pytest.approx(
        summary["tool_call_rps"] * 3 / 4
    )
    assert summary["successful_throughput"] == pytest.approx(
        summary["tool_call_rps"] / 2
    )
    assert summary["time_to_first_event_ms"]["avg"] == 20
    assert summary["ttft_ms"]["avg"] == 20
    assert summary["ttft_ms"]["count"] == 1
    assert summary["end_to_end_latency_ms"]["avg"] == 80
    assert summary["response_time_ms"]["avg"] == 80
    assert summary["content_throughput_bytes_per_second"] > 0


def test_mcp_summary_ttft_falls_back_to_ttfe_when_ttft_missing():
    metrics = ProtocolMetrics()
    metrics.sample("mcp_ttfe_ms", 15)
    metrics.sample("mcp_e2e_ms", 40)

    summary = metrics.summary("mcp")

    assert summary["ttft_ms"]["avg"] == 15
    assert summary["ttft_ms"]["count"] == 1


def test_a2a_summary_reports_submission_terminal_and_combined_failure_metrics():
    metrics = ProtocolMetrics()
    metrics.increment("submissions", 10)
    metrics.increment("submission_successes", 8)
    metrics.increment("a2a_request_attempts", 15)
    metrics.increment("a2a_request_failures", 2)
    metrics.increment("terminal_tasks", 8)
    metrics.increment("completed_tasks", 5)
    metrics.increment("failed_tasks", 2)

    summary = metrics.summary("a2a")

    assert summary["task_submission_rate"] > 0
    assert summary["task_acceptance_rate"] == 0.8
    assert summary["task_submission_success_rate"] == 0.8
    assert summary["terminal_task_throughput"] > 0
    assert summary["completed_task_throughput"] > 0
    assert summary["terminal_completion_rate"] == 5 / 8
    assert summary["terminal_failure_rate"] == 2 / 8
    assert summary["terminal_task_completion_rate"] == 5 / 8
    assert summary["terminal_task_failure_rate"] == 2 / 8
    assert summary["composite_failure_rate"] == 4 / 23
    assert summary["total_failure_rate"] == 4 / 23
