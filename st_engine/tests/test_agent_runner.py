from unittest.mock import Mock, patch

from engine.agent_runner import AgentLocustRunner, protocol_execution_failure_reason


def test_protocol_execution_failure_reason_detects_setup_failure():
    assert (
        protocol_execution_failure_reason(
            "mcp",
            {"custom_metrics": {"failed_requests": 1, "top_level_requests": 0}},
        )
        == "Protocol reported 1 failed request(s)"
    )


def test_protocol_execution_failure_reason_detects_zero_workload_requests():
    assert (
        protocol_execution_failure_reason(
            "mcp", {"custom_metrics": {"top_level_requests": 0}}
        )
        == "Protocol run completed without executing a top-level request"
    )


def test_agent_runner_converts_clean_exit_with_protocol_failure_to_failed_requests(
    tmp_path,
):
    runner = AgentLocustRunner(str(tmp_path))
    task = Mock(protocol="mcp")
    logger = Mock()
    completed_result = {
        "status": "COMPLETED",
        "locust_result": {
            "custom_metrics": {"failed_requests": 1, "top_level_requests": 0}
        },
    }

    with patch(
        "engine.agent_runner.LlmLocustRunner._finalize_task",
        return_value=completed_result,
    ):
        result = runner._finalize_task(Mock(), task, "", "", logger)

    assert result["status"] == "FAILED_REQUESTS"
    assert result["error_message"] == "Protocol reported 1 failed request(s)"


def test_agent_runner_converts_clean_exit_without_workload_to_failed_requests(
    tmp_path,
):
    runner = AgentLocustRunner(str(tmp_path))
    task = Mock(protocol="mcp")
    logger = Mock()
    completed_result = {
        "status": "COMPLETED",
        "locust_result": {"custom_metrics": {"top_level_requests": 0}},
    }

    with patch(
        "engine.agent_runner.LlmLocustRunner._finalize_task",
        return_value=completed_result,
    ):
        result = runner._finalize_task(Mock(), task, "", "", logger)

    assert result["status"] == "FAILED_REQUESTS"
    assert "without executing a top-level request" in result["error_message"]


def test_agent_runner_fills_error_message_for_locust_exit_failures(tmp_path):
    runner = AgentLocustRunner(str(tmp_path))
    task = Mock(protocol="mcp")
    logger = Mock()
    failed_result = {
        "status": "FAILED_REQUESTS",
        "return_code": 1,
        "locust_result": {
            "custom_metrics": {"failed_requests": 3, "top_level_requests": 10}
        },
    }

    with patch(
        "engine.agent_runner.LlmLocustRunner._finalize_task",
        return_value=failed_result,
    ):
        result = runner._finalize_task(Mock(), task, "", "", logger)

    assert result["status"] == "FAILED_REQUESTS"
    assert result["error_message"] == "Protocol reported 3 failed request(s)"
