"""
Tests for http_locustfile helper functions, dataset preloading, stats aggregation,
and multiprocess guards.
"""

import json
import os
import queue
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from engine.http_locustfile import (
    _build_request_kwargs,
    _build_stat_row,
    _check_success_assert,
    _format_context,
    _parse_kv,
    _parse_request_body,
    _preload_dataset,
    _resolve_json_field,
    _write_result_file,
)


# =====================================================================
# _parse_kv
# =====================================================================
class TestParseKv:
    def test_empty_string(self):
        assert _parse_kv("") == {}

    def test_valid_json(self):
        result = _parse_kv('{"Content-Type": "application/json", "X-Token": "abc"}')
        assert result == {"Content-Type": "application/json", "X-Token": "abc"}

    def test_values_coerced_to_string(self):
        result = _parse_kv('{"num": 123, "flag": true}')
        assert result == {"num": "123", "flag": "True"}

    def test_invalid_json_returns_empty(self):
        assert _parse_kv("not-json") == {}

    def test_non_dict_json_returns_empty(self):
        assert _parse_kv("[1,2,3]") == {}


# =====================================================================
# _parse_request_body
# =====================================================================
class TestParseRequestBody:
    def test_valid_json_body(self):
        json_payload, text_payload = _parse_request_body('{"key": "value"}')
        assert json_payload == {"key": "value"}
        assert text_payload is None

    def test_plain_text_body(self):
        json_payload, text_payload = _parse_request_body("hello world")
        assert json_payload is None
        assert text_payload == "hello world"

    def test_empty_body(self):
        json_payload, text_payload = _parse_request_body("")
        assert json_payload is None
        assert text_payload == ""

    def test_none_body(self):
        json_payload, text_payload = _parse_request_body(None)
        assert json_payload is None
        assert text_payload is None


# =====================================================================
# _build_request_kwargs
# =====================================================================
class TestBuildRequestKwargs:
    def test_json_payload(self):
        result = _build_request_kwargs({}, {}, {"key": "val"}, None)
        assert "json" in result
        assert "data" not in result
        assert result["json"] == {"key": "val"}

    def test_text_payload(self):
        result = _build_request_kwargs({}, {}, None, "raw text")
        assert "data" in result
        assert "json" not in result
        assert result["data"] == "raw text"

    def test_json_takes_precedence(self):
        """When both are provided, json should be used, not data."""
        result = _build_request_kwargs({}, {}, {"k": 1}, "fallback")
        assert "json" in result
        assert "data" not in result

    def test_neither_payload(self):
        result = _build_request_kwargs({"h": "v"}, {"c": "v"}, None, None)
        assert "json" not in result
        assert "data" not in result
        assert result["headers"] == {"h": "v"}
        assert result["cookies"] == {"c": "v"}


# =====================================================================
# _resolve_json_field
# =====================================================================
class TestResolveJsonField:
    def test_top_level_field(self):
        found, val = _resolve_json_field({"code": 0}, "code")
        assert found is True
        assert val == 0

    def test_nested_field(self):
        found, val = _resolve_json_field({"data": {"status": "ok"}}, "data.status")
        assert found is True
        assert val == "ok"

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": 42}}}
        found, val = _resolve_json_field(data, "a.b.c")
        assert found is True
        assert val == 42

    def test_missing_field(self):
        found, val = _resolve_json_field({"code": 0}, "missing")
        assert found is False
        assert val is None

    def test_missing_nested(self):
        found, val = _resolve_json_field({"data": {}}, "data.code")
        assert found is False

    def test_non_dict_intermediate(self):
        found, val = _resolve_json_field({"data": "string"}, "data.code")
        assert found is False


# =====================================================================
# _check_success_assert
# =====================================================================
class TestCheckSuccessAssert:
    def test_eq_success(self):
        rule = {"field": "code", "operator": "eq", "value": 0}
        ok, reason = _check_success_assert(rule, '{"code": 0}')
        assert ok is True
        assert reason == ""

    def test_eq_failure(self):
        rule = {"field": "code", "operator": "eq", "value": 0}
        ok, reason = _check_success_assert(rule, '{"code": 1}')
        assert ok is False
        assert "Business assertion failed" in reason

    def test_neq(self):
        rule = {"field": "status", "operator": "neq", "value": "error"}
        ok, _ = _check_success_assert(rule, '{"status": "ok"}')
        assert ok is True

    def test_gt(self):
        rule = {"field": "count", "operator": "gt", "value": 5}
        ok, _ = _check_success_assert(rule, '{"count": 10}')
        assert ok is True

    def test_gte(self):
        rule = {"field": "count", "operator": "gte", "value": 10}
        ok, _ = _check_success_assert(rule, '{"count": 10}')
        assert ok is True

    def test_lt(self):
        rule = {"field": "count", "operator": "lt", "value": 10}
        ok, _ = _check_success_assert(rule, '{"count": 5}')
        assert ok is True

    def test_lte(self):
        rule = {"field": "count", "operator": "lte", "value": 5}
        ok, _ = _check_success_assert(rule, '{"count": 5}')
        assert ok is True

    def test_in_operator(self):
        rule = {"field": "code", "operator": "in", "value": [0, 200]}
        ok, _ = _check_success_assert(rule, '{"code": 0}')
        assert ok is True

    def test_in_operator_miss(self):
        rule = {"field": "code", "operator": "in", "value": [0, 200]}
        ok, _ = _check_success_assert(rule, '{"code": 500}')
        assert ok is False

    def test_not_in_operator(self):
        rule = {"field": "code", "operator": "not_in", "value": [400, 500]}
        ok, _ = _check_success_assert(rule, '{"code": 0}')
        assert ok is True

    def test_unknown_operator(self):
        rule = {"field": "code", "operator": "regex", "value": ".*"}
        ok, reason = _check_success_assert(rule, '{"code": 0}')
        assert ok is False
        assert "Unknown operator" in reason

    def test_invalid_json_response(self):
        rule = {"field": "code", "operator": "eq", "value": 0}
        ok, reason = _check_success_assert(rule, "not json")
        assert ok is False
        assert "not valid JSON" in reason

    def test_non_object_response(self):
        rule = {"field": "code", "operator": "eq", "value": 0}
        ok, reason = _check_success_assert(rule, "[1,2,3]")
        assert ok is False
        assert "not a JSON object" in reason

    def test_missing_field_in_response(self):
        rule = {"field": "code", "operator": "eq", "value": 0}
        ok, reason = _check_success_assert(rule, '{"status": "ok"}')
        assert ok is False
        assert "not found" in reason

    def test_null_field_value(self):
        rule = {"field": "code", "operator": "eq", "value": 0}
        ok, reason = _check_success_assert(rule, '{"code": null}')
        assert ok is False
        assert "null" in reason

    def test_null_expected_value(self):
        rule = {"field": "code", "operator": "eq", "value": None}
        ok, reason = _check_success_assert(rule, '{"code": 0}')
        assert ok is False
        assert "not configured" in reason

    def test_nested_field_assertion(self):
        rule = {"field": "data.code", "operator": "eq", "value": 0}
        ok, _ = _check_success_assert(rule, '{"data": {"code": 0}}')
        assert ok is True

    def test_string_int_comparison(self):
        """eq compares as strings, so int 0 should match string '0'."""
        rule = {"field": "code", "operator": "eq", "value": "0"}
        ok, _ = _check_success_assert(rule, '{"code": 0}')
        assert ok is True

    def test_numeric_comparison_error(self):
        """gt with non-numeric value should produce a comparison error."""
        rule = {"field": "code", "operator": "gt", "value": 5}
        ok, reason = _check_success_assert(rule, '{"code": "abc"}')
        assert ok is False
        assert "comparison error" in reason


# =====================================================================
# _format_context
# =====================================================================
class TestFormatContext:
    def test_with_status(self):
        result = _format_context(status=200)
        assert "status=200" in result

    def test_with_json_payload(self):
        result = _format_context(json_payload={"key": "val"})
        assert "request_json" in result

    def test_with_text_payload(self):
        result = _format_context(text_payload="raw body")
        assert "request_data" in result

    def test_json_takes_priority_over_text(self):
        result = _format_context(json_payload={"k": 1}, text_payload="txt")
        assert "request_json" in result
        assert "request_data" not in result

    def test_response_body_capped(self):
        long_body = "x" * 2000
        result = _format_context(response_body=long_body)
        assert "response_body" in result
        assert len(result) < 1200  # capped at 1000 chars

    def test_sensitive_headers(self):
        result = _format_context(headers={"Auth": "secret"}, include_sensitive=True)
        assert "headers" in result

    def test_sensitive_headers_hidden_by_default(self):
        result = _format_context(headers={"Auth": "secret"})
        assert "headers" not in result

    def test_empty_returns_empty_string(self):
        assert _format_context() == ""


# =====================================================================
# _build_stat_row
# =====================================================================
class TestBuildStatRow:
    def test_normal_stat(self):
        stat = Mock()
        stat.num_requests = 100
        stat.num_failures = 5
        stat.avg_response_time = 50.0
        stat.min_response_time = 10.0
        stat.max_response_time = 200.0
        stat.median_response_time = 45.0
        stat.get_response_time_percentile = Mock(return_value=180.0)
        stat.total_rps = 20.0
        stat.avg_content_length = 512.0

        row = _build_stat_row("task-001", "GET /api/users", stat)
        assert row["task_id"] == "task-001"
        assert row["metric_type"] == "GET /api/users"
        assert row["num_requests"] == 100
        assert row["num_failures"] == 5
        assert row["p95_latency"] == 180.0
        stat.get_response_time_percentile.assert_called_with(0.95)

    def test_exception_returns_empty(self):
        stat = Mock(
            spec=[]
        )  # empty spec → accessing any attribute raises AttributeError
        row = _build_stat_row("task-001", "test", stat)
        assert row == {}


# =====================================================================
# _write_result_file
# =====================================================================
class TestWriteResultFile:
    def test_writes_json(self, tmp_path):
        stats = [{"task_id": "t1", "metric_type": "total", "num_requests": 10}]
        with patch(
            "engine.http_locustfile.tempfile.gettempdir", return_value=str(tmp_path)
        ):
            result_file = _write_result_file("task-abc", stats)

        assert os.path.exists(result_file)
        with open(result_file) as f:
            data = json.load(f)
        assert data["locust_stats"] == stats
        assert data["custom_metrics"] == {}


# =====================================================================
# _preload_dataset
# =====================================================================
class TestPreloadDataset:
    def test_preload_json_dataset(self, tmp_path):
        dataset_file = tmp_path / "data.jsonl"
        dataset_file.write_text('{"name": "Alice"}\n{"name": "Bob"}\n')

        env = Mock()
        env.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="test-ds-001"
        )

        _preload_dataset(env)

        assert hasattr(env, "dataset_queue")
        dq = env.dataset_queue
        assert isinstance(dq, queue.Queue)
        assert dq.qsize() == 2

        item1 = dq.get()
        assert item1 == {"json": {"name": "Alice"}}
        item2 = dq.get()
        assert item2 == {"json": {"name": "Bob"}}

    def test_preload_mixed_lines(self, tmp_path):
        dataset_file = tmp_path / "mixed.jsonl"
        dataset_file.write_text('{"key": 1}\nplain text line\n\n')

        env = Mock()
        env.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="test-ds-002"
        )

        _preload_dataset(env)

        dq = env.dataset_queue
        assert dq.qsize() == 2

        item1 = dq.get()
        assert item1 == {"json": {"key": 1}}
        item2 = dq.get()
        assert item2 == {"text": "plain text line"}

    def test_preload_no_dataset_file(self):
        env = SimpleNamespace(
            parsed_options=SimpleNamespace(dataset_file="", task_id="test-ds-003")
        )

        _preload_dataset(env)

        # Should NOT set dataset_queue on the environment
        assert not hasattr(env, "dataset_queue")

    def test_preload_empty_file(self, tmp_path):
        dataset_file = tmp_path / "empty.jsonl"
        dataset_file.write_text("\n\n\n")

        env = Mock()
        env.parsed_options = SimpleNamespace(
            dataset_file=str(dataset_file), task_id="test-ds-004"
        )

        _preload_dataset(env)
        assert env.dataset_queue is None

    def test_preload_missing_file(self):
        env = Mock()
        env.parsed_options = SimpleNamespace(
            dataset_file="/tmp/nonexistent_file_abc123.jsonl", task_id="test-ds-005"
        )

        _preload_dataset(env)
        assert env.dataset_queue is None


# =====================================================================
# on_test_stop multiprocess guards
# =====================================================================
class TestOnTestStopMultiprocessGuard:
    """Verify that on_test_stop correctly skips result writing on Worker
    and only writes on Master/LocalRunner."""

    def _make_environment(self, runner_type):
        """Create a mock environment with a specific runner type."""
        env = Mock()
        env.parsed_options = SimpleNamespace(task_id="mp-test-001")
        env._realtime_greenlet = None

        if runner_type == "worker":
            from locust.runners import WorkerRunner

            env.runner = Mock(spec=WorkerRunner)
        elif runner_type == "master":
            from locust.runners import MasterRunner

            env.runner = Mock(spec=MasterRunner)
        elif runner_type == "local":
            from locust.runners import LocalRunner

            env.runner = Mock(spec=LocalRunner)
        else:
            env.runner = Mock()

        return env

    @patch("engine.http_locustfile._write_result_file")
    def test_worker_skips_result_writing(self, mock_write):
        """Worker processes must NOT write result files."""
        from engine.http_locustfile import on_test_stop

        env = self._make_environment("worker")
        on_test_stop(env)
        mock_write.assert_not_called()

    @patch("engine.http_locustfile._write_result_file")
    @patch("engine.http_locustfile.gevent")
    def test_local_runner_writes_results(self, mock_gevent, mock_write):
        """LocalRunner (single-process mode) should write results."""
        from engine.http_locustfile import on_test_stop

        env = self._make_environment("local")
        # Set up stats with one entry
        stat = Mock()
        stat.name = "GET /api/test"
        stat.num_requests = 10
        stat.num_failures = 0
        stat.avg_response_time = 50.0
        stat.min_response_time = 10.0
        stat.max_response_time = 100.0
        stat.median_response_time = 45.0
        stat.get_response_time_percentile = Mock(return_value=90.0)
        stat.total_rps = 5.0
        stat.avg_content_length = 200.0

        total_stat = Mock()
        total_stat.num_requests = 10
        total_stat.num_failures = 0
        total_stat.avg_response_time = 50.0
        total_stat.min_response_time = 10.0
        total_stat.max_response_time = 100.0
        total_stat.median_response_time = 45.0
        total_stat.get_response_time_percentile = Mock(return_value=90.0)
        total_stat.total_rps = 5.0
        total_stat.avg_content_length = 200.0

        env.stats = Mock()
        env.stats.entries = {("GET /api/test", "GET"): stat}
        env.stats.total = total_stat

        on_test_stop(env)
        mock_write.assert_called_once()

        # Verify the stats passed to _write_result_file contain clean metric_type
        written_stats = mock_write.call_args[0][1]
        metric_types = [s["metric_type"] for s in written_stats]
        assert "GET /api/test" in metric_types
        assert "total" in metric_types

    @patch("engine.http_locustfile._write_result_file")
    @patch("engine.http_locustfile.gevent")
    @patch("utils.common.wait_time_for_stats_sync", return_value=0.1)
    def test_master_waits_for_stats_sync(self, mock_wait, mock_gevent, mock_write):
        """MasterRunner should wait for worker stats sync before writing."""
        from engine.http_locustfile import on_test_stop

        env = self._make_environment("master")
        env.stats = Mock()
        env.stats.entries = {}
        env.stats.total = None

        with patch.dict(os.environ, {"LOCUST_CONCURRENT_USERS": "100"}):
            on_test_stop(env)

        # gevent.sleep should be called for stats sync wait
        mock_gevent.sleep.assert_called()

    @patch("engine.http_locustfile._write_result_file")
    @patch("engine.http_locustfile.gevent")
    def test_stats_entries_tuple_key_resolved_to_stat_name(
        self, mock_gevent, mock_write
    ):
        """stats.entries keys are (name, method) tuples; metric_type should use stat.name."""
        from engine.http_locustfile import on_test_stop

        env = self._make_environment("local")

        stat1 = Mock()
        stat1.name = "GET /users"
        stat1.num_requests = 5
        stat1.num_failures = 0
        stat1.avg_response_time = 20.0
        stat1.min_response_time = 10.0
        stat1.max_response_time = 30.0
        stat1.median_response_time = 20.0
        stat1.get_response_time_percentile = Mock(return_value=28.0)
        stat1.total_rps = 2.0
        stat1.avg_content_length = 100.0

        stat2 = Mock()
        stat2.name = "POST /users"
        stat2.num_requests = 3
        stat2.num_failures = 1
        stat2.avg_response_time = 40.0
        stat2.min_response_time = 20.0
        stat2.max_response_time = 60.0
        stat2.median_response_time = 35.0
        stat2.get_response_time_percentile = Mock(return_value=55.0)
        stat2.total_rps = 1.0
        stat2.avg_content_length = 50.0

        env.stats = Mock()
        env.stats.entries = {
            ("GET /users", "GET"): stat1,
            ("POST /users", "POST"): stat2,
        }
        env.stats.total = None

        on_test_stop(env)
        mock_write.assert_called_once()

        written_stats = mock_write.call_args[0][1]
        metric_types = {s["metric_type"] for s in written_stats}
        # metric_type should be the clean stat.name, not the tuple key
        assert "GET /users" in metric_types
        assert "POST /users" in metric_types
        # Should NOT contain tuple string representation
        for s in written_stats:
            assert not s["metric_type"].startswith("(")

    @patch("engine.http_locustfile._write_result_file")
    @patch("engine.http_locustfile.gevent")
    def test_aggregated_entry_filtered_out(self, mock_gevent, mock_write):
        """The auto-generated 'Aggregated' entry should be excluded."""
        from engine.http_locustfile import on_test_stop

        env = self._make_environment("local")

        agg_stat = Mock()
        agg_stat.name = "Aggregated"

        normal_stat = Mock()
        normal_stat.name = "GET /api"
        normal_stat.num_requests = 1
        normal_stat.num_failures = 0
        normal_stat.avg_response_time = 10.0
        normal_stat.min_response_time = 10.0
        normal_stat.max_response_time = 10.0
        normal_stat.median_response_time = 10.0
        normal_stat.get_response_time_percentile = Mock(return_value=10.0)
        normal_stat.total_rps = 1.0
        normal_stat.avg_content_length = 50.0

        env.stats = Mock()
        env.stats.entries = {
            ("Aggregated", None): agg_stat,
            ("GET /api", "GET"): normal_stat,
        }
        env.stats.total = None

        on_test_stop(env)
        mock_write.assert_called_once()

        written_stats = mock_write.call_args[0][1]
        metric_types = {s["metric_type"] for s in written_stats}
        assert "Aggregated" not in metric_types
        assert "GET /api" in metric_types
