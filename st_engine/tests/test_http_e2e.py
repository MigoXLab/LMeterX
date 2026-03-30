"""
End-to-end style tests that simulate the complete HTTP API load testing flow
by wiring together locustfile helpers, runner command building, result
writing/reading, and the service layer.

These tests do NOT start real Locust subprocesses; they validate the full
data path by exercising the glue code with realistic inputs.
"""

import json
import os
import queue
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from engine.http_locustfile import (
    _build_request_kwargs,
    _build_stat_row,
    _check_success_assert,
    _parse_kv,
    _parse_request_body,
    _preload_dataset,
    _write_result_file,
)
from engine.http_runner import HttpLocustRunner
from service.http_result_service import HttpResultService


# =====================================================================
# E2E: request preparation → assertion → result writing → DB insertion
# =====================================================================
class TestRequestToResultFlow:
    """Simulate a full request lifecycle: parse headers, body, assert, write
    result, and insert into DB."""

    def test_successful_json_request_flow(self, tmp_path):
        """Simulate: POST /api/data with JSON body → 200 + business assert pass
        → result written → result service reads and inserts."""

        # Step 1: Parse headers & cookies
        headers = _parse_kv(
            '{"Content-Type": "application/json", "X-Api-Key": "key123"}'
        )
        cookies = _parse_kv('{"session": "sess-abc"}')
        assert headers["Content-Type"] == "application/json"
        assert cookies["session"] == "sess-abc"

        # Step 2: Parse request body
        json_payload, text_payload = _parse_request_body('{"name": "Alice", "age": 30}')
        assert json_payload == {"name": "Alice", "age": 30}
        assert text_payload is None

        # Step 3: Build request kwargs
        kwargs = _build_request_kwargs(headers, cookies, json_payload, text_payload)
        assert kwargs["json"] == {"name": "Alice", "age": 30}
        assert kwargs["headers"] == headers
        assert kwargs["cookies"] == cookies
        assert "data" not in kwargs

        # Step 4: Check business assertion (simulated response)
        assert_rule = {"field": "code", "operator": "eq", "value": 0}
        response_body = '{"code": 0, "data": {"id": 42}}'
        ok, reason = _check_success_assert(assert_rule, response_body)
        assert ok is True
        assert reason == ""

        # Step 5: Build stat row (simulated Locust stats)
        stat = Mock()
        stat.num_requests = 1000
        stat.num_failures = 5
        stat.avg_response_time = 45.2
        stat.min_response_time = 12.0
        stat.max_response_time = 350.0
        stat.median_response_time = 40.0
        stat.get_response_time_percentile = Mock(return_value=210.0)
        stat.total_rps = 50.0
        stat.avg_content_length = 256.0

        row = _build_stat_row("task-e2e-001", "POST /api/data", stat)
        assert row["task_id"] == "task-e2e-001"
        assert row["metric_type"] == "POST /api/data"
        assert row["num_requests"] == 1000
        assert row["p95_latency"] == 210.0

        # Step 6: Write result file
        with patch(
            "engine.http_locustfile.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            result_file = _write_result_file("task-e2e-001", [row])

        with open(result_file) as f:
            result_data = json.load(f)

        assert len(result_data["locust_stats"]) == 1
        assert result_data["locust_stats"][0]["metric_type"] == "POST /api/data"

        # Step 7: Result service inserts into DB
        session = Mock()
        result_service = HttpResultService()
        result_service.insert_locust_results(session, result_data, "task-e2e-001")
        session.add.assert_called_once()
        session.commit.assert_called_once()

        added = session.add.call_args[0][0]
        assert added.metric_type == "POST /api/data"
        assert added.num_requests == 1000

    def test_business_assertion_failure_flow(self):
        """Simulate a request that passes HTTP-level (200) but fails business
        assertion (code != 0)."""

        # Business assertion expects code == 0
        assert_rule = {"field": "code", "operator": "eq", "value": 0}
        response_body = '{"code": 1001, "message": "Unauthorized"}'

        ok, reason = _check_success_assert(assert_rule, response_body)
        assert ok is False
        assert "Business assertion failed" in reason
        assert "1001" in reason

    def test_204_no_content_skips_assertion(self):
        """HTTP 204 No Content should be treated as success even when
        a business assertion rule is configured."""
        # The Locust code skips assertion for 204 or empty body.
        # Here we verify the rule itself: assertion on empty body returns
        # a failure reason, so the Locust code correctly short-circuits
        # before calling _check_success_assert.
        assert_rule = {"field": "code", "operator": "eq", "value": 0}

        # Empty body → assertion fails
        ok, reason = _check_success_assert(assert_rule, "")
        assert ok is False  # This is why the Locust code must skip assertion for 204

    def test_non_2xx_flow(self):
        """Status code >= 300 should be marked as failure at HTTP level,
        bypassing business assertion entirely."""
        # The Locust code checks `resp.status_code >= 300` first.
        # Business assertion is only reached for 2xx codes.
        # This test verifies the assertion function itself isn't affected.
        assert_rule = {"field": "code", "operator": "eq", "value": 0}

        # 500 error body
        ok, reason = _check_success_assert(
            assert_rule, '{"code": 0, "detail": "Internal Server Error"}'
        )
        # The body could still pass, but the Locust code won't call this
        # because the HTTP status check (>= 300) fires first.
        assert ok is True  # assertion itself passes — it's the HTTP check that blocks


# =====================================================================
# E2E: dataset preload → round-robin → request kwargs
# =====================================================================
class TestDatasetToRequestFlow:
    """Test the path from dataset file → preloaded queue → request kwargs."""

    def test_dataset_round_robin_flow(self, tmp_path):
        """Load a JSONL dataset, simulate round-robin pick, build kwargs."""

        # Step 1: Create dataset file
        dataset_file = tmp_path / "payloads.jsonl"
        dataset_file.write_text(
            '{"name": "Alice", "action": "create"}\n'
            '{"name": "Bob", "action": "update"}\n'
            '{"name": "Charlie", "action": "delete"}\n'
        )

        # Step 2: Preload
        env = Mock()
        env.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="task-ds-e2e"
        )
        _preload_dataset(env)

        dq = env.dataset_queue
        assert dq.qsize() == 3

        # Step 3: Simulate round-robin (get + put back)
        record = dq.get_nowait()
        dq.put_nowait(record)
        assert "json" in record
        json_payload = record["json"]
        assert json_payload["name"] in ("Alice", "Bob", "Charlie")

        # Step 4: Build request kwargs
        kwargs = _build_request_kwargs(
            {"Content-Type": "application/json"}, {}, json_payload, None
        )
        assert "json" in kwargs
        assert kwargs["json"]["name"] in ("Alice", "Bob", "Charlie")

    def test_dataset_with_plain_text_lines(self, tmp_path):
        """Non-JSON lines in dataset should be treated as text payloads."""
        dataset_file = tmp_path / "text_data.jsonl"
        dataset_file.write_text("plain text line 1\nplain text line 2\n")

        env = Mock()
        env.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="task-ds-txt"
        )
        _preload_dataset(env)

        dq = env.dataset_queue
        record = dq.get_nowait()
        assert "text" in record

        kwargs = _build_request_kwargs({}, {}, None, record["text"])
        assert "data" in kwargs
        assert kwargs["data"] == "plain text line 1"

    def test_empty_dataset_falls_back_to_request_body(self, tmp_path):
        """When dataset is empty, the code falls back to static request_body."""
        dataset_file = tmp_path / "empty.jsonl"
        dataset_file.write_text("\n\n\n")

        env = Mock()
        env.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="task-ds-empty"
        )
        _preload_dataset(env)
        assert env.dataset_queue is None

        # Fallback: parse static request_body
        json_payload, text_payload = _parse_request_body('{"fallback": true}')
        assert json_payload == {"fallback": True}


# =====================================================================
# E2E: runner command build → result file → service insertion
# =====================================================================
class TestRunnerToServiceFlow:
    """Verify the complete chain from runner command build through result
    file creation to service result insertion."""

    def test_fixed_mode_full_chain(self, tmp_path):
        """Build command → simulate result file → insert into DB."""

        # Step 1: Build runner and command
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "http_locustfile.py").write_text("# dummy")

        runner = HttpLocustRunner(str(tmp_path))
        task = Mock()
        task.id = "task-chain-001"
        task.target_host = "http://api.example.com"
        task.api_path = "/v1/items"
        task.method = "PUT"
        task.headers = '{"Authorization": "Bearer token"}'
        task.cookies = "{}"
        task.concurrent_users = 50
        task.spawn_rate = 10
        task.duration = 120
        task.load_mode = "fixed"
        task.request_body = '{"item": "test"}'
        task.dataset_file = None
        task.success_assert = '{"field":"status","operator":"eq","value":"ok"}'
        task.step_start_users = None
        task.step_increment = None
        task.step_duration = None
        task.step_max_users = None
        task.step_sustain_duration = None

        cmd = runner._build_locust_command(task, Mock())

        # Verify critical args
        assert "--method" in cmd
        assert "PUT" in cmd
        assert "--success_assert" in cmd
        assert "--request_body" in cmd

        # Step 2: Simulate result file creation (as locust on_test_stop would)
        stats = [
            {
                "task_id": "task-chain-001",
                "metric_type": "PUT /v1/items",
                "num_requests": 500,
                "num_failures": 10,
                "avg_latency": 80.5,
                "min_latency": 15.0,
                "max_latency": 500.0,
                "median_latency": 70.0,
                "p95_latency": 350.0,
                "rps": 25.0,
                "avg_content_length": 128.0,
            },
            {
                "task_id": "task-chain-001",
                "metric_type": "total",
                "num_requests": 500,
                "num_failures": 10,
                "avg_latency": 80.5,
                "min_latency": 15.0,
                "max_latency": 500.0,
                "median_latency": 70.0,
                "p95_latency": 350.0,
                "rps": 25.0,
                "avg_content_length": 128.0,
            },
        ]

        with patch(
            "engine.http_locustfile.tempfile.gettempdir",
            return_value=str(tmp_path),
        ):
            result_file = _write_result_file("task-chain-001", stats)

        # Step 3: Load result (as _finalize_task would)
        with open(result_file) as f:
            locust_result = json.load(f)

        assert len(locust_result["locust_stats"]) == 2

        # Step 4: Insert into DB
        session = Mock()
        result_service = HttpResultService()
        result_service.insert_locust_results(session, locust_result, "task-chain-001")

        assert session.add.call_count == 2
        session.commit.assert_called_once()

        # Verify the metrics are correct
        calls = session.add.call_args_list
        metric_types = [c[0][0].metric_type for c in calls]
        assert "PUT /v1/items" in metric_types
        assert "total" in metric_types

    def test_all_http_methods_command_generation(self, tmp_path):
        """Verify all HTTP methods produce valid commands with correct method arg."""
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "http_locustfile.py").write_text("# dummy")
        runner = HttpLocustRunner(str(tmp_path))

        for method in ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
            task = Mock()
            task.id = f"task-{method.lower()}"
            task.target_host = "http://example.com"
            task.api_path = f"/api/{method.lower()}"
            task.method = method
            task.headers = "{}"
            task.cookies = "{}"
            task.concurrent_users = 10
            task.spawn_rate = 5
            task.duration = 30
            task.load_mode = "fixed"
            task.request_body = None
            task.dataset_file = None
            task.success_assert = None

            cmd = runner._build_locust_command(task, Mock())
            idx = cmd.index("--method")
            assert cmd[idx + 1] == method, f"Expected {method} in command"


# =====================================================================
# E2E: multiprocess dataset isolation
# =====================================================================
class TestMultiprocessDatasetIsolation:
    """Verify that dataset preloading works correctly when simulating
    multiple independent process environments (as --processes N would create)."""

    def test_independent_queues_per_environment(self, tmp_path):
        """Each Locust process (env) should have its own dataset_queue.
        Consuming from one should NOT affect the other."""
        dataset_file = tmp_path / "shared.jsonl"
        dataset_file.write_text('{"id": 1}\n{"id": 2}\n{"id": 3}\n')

        # Simulate two independent environments (two processes)
        env1 = Mock()
        env1.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="mp-env1"
        )
        env2 = Mock()
        env2.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="mp-env2"
        )

        _preload_dataset(env1)
        _preload_dataset(env2)

        # Both should have 3 items
        assert env1.dataset_queue.qsize() == 3
        assert env2.dataset_queue.qsize() == 3

        # Consume from env1
        env1.dataset_queue.get_nowait()
        env1.dataset_queue.get_nowait()

        # env2 should be unaffected
        assert env1.dataset_queue.qsize() == 1
        assert env2.dataset_queue.qsize() == 3


# =====================================================================
# E2E: success assertion with various operator combinations
# =====================================================================
class TestSuccessAssertE2E:
    """End-to-end scenarios for business assertion across different
    response types and operator combinations."""

    def test_nested_field_eq_success(self):
        rule = {"field": "data.result.code", "operator": "eq", "value": "SUCCESS"}
        body = '{"data": {"result": {"code": "SUCCESS", "items": []}}}'
        ok, _ = _check_success_assert(rule, body)
        assert ok is True

    def test_numeric_gt_with_float(self):
        rule = {"field": "score", "operator": "gt", "value": 0.5}
        body = '{"score": 0.95}'
        ok, _ = _check_success_assert(rule, body)
        assert ok is True

    def test_in_operator_with_multiple_values(self):
        rule = {"field": "status", "operator": "in", "value": ["active", "pending"]}
        body = '{"status": "pending"}'
        ok, _ = _check_success_assert(rule, body)
        assert ok is True

    def test_not_in_operator(self):
        rule = {"field": "status", "operator": "not_in", "value": ["deleted", "banned"]}
        body = '{"status": "active"}'
        ok, _ = _check_success_assert(rule, body)
        assert ok is True

    def test_complex_response_structure(self):
        """Real-world-like response with nested pagination."""
        rule = {"field": "meta.code", "operator": "eq", "value": 200}
        body = json.dumps(
            {
                "meta": {"code": 200, "message": "OK"},
                "data": {"items": [1, 2, 3], "total": 100},
                "pagination": {"page": 1, "per_page": 20},
            }
        )
        ok, _ = _check_success_assert(rule, body)
        assert ok is True
