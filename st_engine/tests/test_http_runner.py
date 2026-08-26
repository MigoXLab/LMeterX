"""
Tests for HttpLocustRunner command building, multiprocess support,
and warmup phase skipping.
"""

import json
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from config.base import LOCUST_STOP_TIMEOUT
from engine.http_runner import HttpLocustRunner


@pytest.fixture
def runner(tmp_path):
    """Create an HttpLocustRunner rooted at a temporary directory."""
    # Create a dummy locustfile to satisfy path validation
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "http_locustfile.py").write_text("# dummy")
    return HttpLocustRunner(str(tmp_path))


@pytest.fixture
def mock_task():
    """Create a mock HttpTask with typical fixed-mode fields."""
    task = Mock()
    task.id = "task-http-001"
    task.target_host = "http://example.com"
    task.api_path = "/api/v1/users"
    task.method = "POST"
    task.headers = '{"Authorization": "Bearer xxx"}'
    task.cookies = '{"session": "abc"}'
    task.concurrent_users = 10
    task.spawn_rate = 5
    task.duration = 60
    task.load_mode = "fixed"
    task.request_body = '{"name": "test"}'
    task.dataset_file = None
    task.success_assert = None
    # Stepped fields (not used in fixed mode)
    task.step_start_users = None
    task.step_increment = None
    task.step_duration = None
    task.step_max_users = None
    task.step_sustain_duration = None
    return task


@pytest.fixture
def mock_logger():
    return Mock()


@pytest.fixture
def mock_http_task():
    """Create a mock HttpTask with typical fixed-mode fields."""
    task = Mock()
    task.id = "task-fix-001"
    task.target_host = "http://example.com"
    task.api_path = "/api/test"
    task.method = "POST"
    task.headers = '{"Content-Type": "application/json"}'
    task.cookies = "{}"
    task.concurrent_users = 50
    task.spawn_rate = 10
    task.duration = 120
    task.load_mode = "fixed"
    task.request_body = '{"key": "value"}'
    task.dataset_file = None
    task.success_assert = None
    task.step_start_users = None
    task.step_increment = None
    task.step_duration = None
    task.step_max_users = None
    task.step_sustain_duration = None
    return task


# =====================================================================
# Fixed mode command building
# =====================================================================
class TestFixedModeCommand:
    def test_basic_command_structure(self, runner, mock_task, mock_logger):
        cmd = runner._build_locust_command(mock_task, mock_logger)

        assert "-f" in cmd
        assert "--host" in cmd
        assert "http://example.com" in cmd
        assert "--headless" in cmd
        assert "--only-summary" in cmd
        assert "--task-id" in cmd
        assert "task-http-001" in cmd

    def test_method_passed(self, runner, mock_task, mock_logger):
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx = cmd.index("--method")
        assert cmd[idx + 1] == "POST"

    def test_api_path_passed(self, runner, mock_task, mock_logger):
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx = cmd.index("--api_path")
        assert cmd[idx + 1] == "/api/v1/users"

    def test_fixed_mode_args(self, runner, mock_task, mock_logger):
        cmd = runner._build_locust_command(mock_task, mock_logger)

        idx_users = cmd.index("--users")
        assert cmd[idx_users + 1] == "10"

        idx_spawn = cmd.index("--spawn-rate")
        assert cmd[idx_spawn + 1] == "5"

        idx_time = cmd.index("--run-time")
        assert cmd[idx_time + 1] == "60s"

    def test_request_body_included(self, runner, mock_task, mock_logger):
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx = cmd.index("--request_body")
        assert cmd[idx + 1] == '{"name": "test"}'

    def test_optional_args_excluded_when_none(self, runner, mock_task, mock_logger):
        mock_task.request_body = None
        mock_task.dataset_file = None
        mock_task.success_assert = None

        cmd = runner._build_locust_command(mock_task, mock_logger)

        assert "--request_body" not in cmd
        assert "--dataset_file" not in cmd
        assert "--success_assert" not in cmd

    def test_dataset_file_included(self, runner, mock_task, mock_logger):
        mock_task.dataset_file = "/data/test.jsonl"
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx = cmd.index("--dataset_file")
        assert cmd[idx + 1] == "/data/test.jsonl"

    def test_success_assert_included(self, runner, mock_task, mock_logger):
        mock_task.success_assert = '{"field":"code","operator":"eq","value":0}'
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx = cmd.index("--success_assert")
        assert cmd[idx + 1] == '{"field":"code","operator":"eq","value":0}'

    def test_headers_and_cookies_passed(self, runner, mock_task, mock_logger):
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx_h = cmd.index("--headers")
        assert cmd[idx_h + 1] == '{"Authorization": "Bearer xxx"}'
        idx_c = cmd.index("--cookies")
        assert cmd[idx_c + 1] == '{"session": "abc"}'

    def test_empty_headers_defaults_to_empty_json(self, runner, mock_task, mock_logger):
        mock_task.headers = None
        mock_task.cookies = None
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx_h = cmd.index("--headers")
        assert cmd[idx_h + 1] == "{}"
        idx_c = cmd.index("--cookies")
        assert cmd[idx_c + 1] == "{}"


# =====================================================================
# Stepped mode command building
# =====================================================================
class TestSteppedModeCommand:
    def test_stepped_mode_omits_users_args(self, runner, mock_task, mock_logger):
        mock_task.load_mode = "stepped"
        mock_task.step_start_users = 1
        mock_task.step_increment = 10
        mock_task.step_duration = 30
        mock_task.step_max_users = 100
        mock_task.step_sustain_duration = 60

        cmd = runner._build_locust_command(mock_task, mock_logger)

        assert "--users" not in cmd
        assert "--spawn-rate" not in cmd
        assert "--run-time" not in cmd


# =====================================================================
# Multiprocess support
# =====================================================================
class TestMultiprocessSupport:
    @patch("engine.http_runner.should_enable_multiprocess", return_value=True)
    @patch("engine.http_runner.get_process_count", return_value=4)
    @patch("engine.http_runner.get_cpu_count", return_value=8)
    def test_multiprocess_enabled_when_high_concurrency(
        self, mock_cpu, mock_proc_count, mock_should, runner, mock_task, mock_logger
    ):
        mock_task.concurrent_users = 2000
        cmd = runner._build_locust_command(mock_task, mock_logger)

        assert "--processes" in cmd
        idx = cmd.index("--processes")
        assert cmd[idx + 1] == "4"

    @patch("engine.http_runner.should_enable_multiprocess", return_value=False)
    @patch("engine.http_runner.get_process_count", return_value=1)
    @patch("engine.http_runner.get_cpu_count", return_value=2)
    def test_multiprocess_disabled_for_low_concurrency(
        self, mock_cpu, mock_proc_count, mock_should, runner, mock_task, mock_logger
    ):
        mock_task.concurrent_users = 10
        cmd = runner._build_locust_command(mock_task, mock_logger)

        assert "--processes" not in cmd

    @patch("engine.http_runner.should_enable_multiprocess", return_value=True)
    @patch("engine.http_runner.get_process_count", return_value=1)
    @patch("engine.http_runner.get_cpu_count", return_value=1)
    def test_multiprocess_not_added_when_count_is_1(
        self, mock_cpu, mock_proc_count, mock_should, runner, mock_task, mock_logger
    ):
        """Even if multiprocess is "enabled", a count of 1 should not add --processes."""
        mock_task.concurrent_users = 2000
        cmd = runner._build_locust_command(mock_task, mock_logger)

        assert "--processes" not in cmd


# =====================================================================
# Warmup phase
# =====================================================================
class TestWarmupPhase:
    def test_warmup_is_noop(self, runner, mock_task, mock_logger):
        """HTTP runner should skip warmup without errors."""
        runner._run_warmup_phase(mock_task, mock_logger)
        mock_logger.debug.assert_called()


# =====================================================================
# Locust summary fallback
# =====================================================================
class TestSummaryFallback:
    SUMMARY_OUTPUT = """
Type     Name                                                                          # reqs      # fails |    Avg     Min     Max    Med |   req/s  failures/s
--------|----------------------------------------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
GET      GET /puyu/ip/location                                                           2186     0(0.00%) |     27      23      82     27 |   36.59        0.00
--------|----------------------------------------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
         Aggregated                                                                      2186     0(0.00%) |     27      23      82     27 |   36.59        0.00
Response time percentiles (approximated)
Type     Name                                                                                  50%    66%    75%    80%    90%    95%    98%    99%  99.9% 99.99%   100% # reqs
--------|--------------------------------------------------------------------------------|--------|------|------|------|------|------|------|------|------|------|------|------
GET      GET /puyu/ip/location                                                                  27     27     27     28     29     31     37     45     80     82     82   2186
--------|--------------------------------------------------------------------------------|--------|------|------|------|------|------|------|------|------|------|------|------
         Aggregated                                                                             27     27     27     28     29     31     37     45     80     82     82   2186
"""

    def test_parse_locust_summary_recovers_http_stats(self, runner):
        rows = runner._parse_locust_summary(self.SUMMARY_OUTPUT, "task-http-001")

        assert len(rows) == 1
        assert rows[0]["task_id"] == "task-http-001"
        assert rows[0]["metric_type"] == "GET /puyu/ip/location"
        assert rows[0]["num_requests"] == 2186
        assert rows[0]["num_failures"] == 0
        assert rows[0]["avg_latency"] == 27.0
        assert rows[0]["p95_latency"] == 31.0
        assert rows[0]["rps"] == 36.59

    def test_finalize_recovers_when_result_file_missing(
        self, runner, mock_task, mock_logger
    ):
        process = Mock()
        process.returncode = 0

        with (
            patch.object(runner, "_cleanup_task"),
            patch("engine.llm_runner.os.path.exists", return_value=False),
        ):
            result = runner._finalize_task(
                process, mock_task, self.SUMMARY_OUTPUT, "", mock_logger
            )

        assert result["status"] == "COMPLETED"
        stats = result["locust_result"]["locust_stats"]
        assert stats[0]["num_requests"] == 2186


# =====================================================================
# HTTP methods coverage
# =====================================================================
class TestHttpMethods:
    @pytest.mark.parametrize(
        "method", ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    )
    def test_all_methods_passed_to_command(
        self, runner, mock_task, mock_logger, method
    ):
        mock_task.method = method
        cmd = runner._build_locust_command(mock_task, mock_logger)
        idx = cmd.index("--method")
        assert cmd[idx + 1] == method


# =====================================================================
# Fix 1: HTTP Runner --stop-timeout
# =====================================================================
class TestHttpRunnerStopTimeout:
    """Verify that HttpLocustRunner includes --stop-timeout in the command."""

    def test_stop_timeout_present_in_fixed_mode(
        self, runner, mock_http_task, mock_logger
    ):
        cmd = runner._build_locust_command(mock_http_task, mock_logger)
        assert "--stop-timeout" in cmd
        idx = cmd.index("--stop-timeout")
        assert cmd[idx + 1] == f"{LOCUST_STOP_TIMEOUT}s"

    def test_stop_timeout_present_in_stepped_mode(
        self, runner, mock_http_task, mock_logger
    ):
        mock_http_task.load_mode = "stepped"
        mock_http_task.step_start_users = 5
        mock_http_task.step_increment = 10
        mock_http_task.step_duration = 30
        mock_http_task.step_max_users = 50
        mock_http_task.step_sustain_duration = 60

        cmd = runner._build_locust_command(mock_http_task, mock_logger)
        assert "--stop-timeout" in cmd
        idx = cmd.index("--stop-timeout")
        assert cmd[idx + 1] == f"{LOCUST_STOP_TIMEOUT}s"

    def test_stop_timeout_value_matches_config(
        self, runner, mock_http_task, mock_logger
    ):
        """Ensure the value is derived from the LOCUST_STOP_TIMEOUT config constant."""
        cmd = runner._build_locust_command(mock_http_task, mock_logger)
        idx = cmd.index("--stop-timeout")
        expected_value = f"{LOCUST_STOP_TIMEOUT}s"
        assert cmd[idx + 1] == expected_value
        # Verify the constant is a positive integer
        assert LOCUST_STOP_TIMEOUT > 0


# =====================================================================
# Fix 2: HTTP locustfile always writes result.json
# =====================================================================
class TestHttpLocustfileResultWrite:
    """Verify that on_test_stop always writes result.json, even with empty stats."""

    def test_write_result_file_with_empty_stats(self):
        """_write_result_file should succeed with an empty stats list."""
        from engine.http_locustfile import _write_result_file

        task_id = "test-empty-stats"
        result_file = _write_result_file(task_id, [])

        assert os.path.exists(result_file)
        with open(result_file, "r") as f:
            data = json.load(f)
        assert data == {"custom_metrics": {}, "locust_stats": []}

        # Cleanup
        import shutil

        shutil.rmtree(os.path.dirname(result_file))

    def test_write_result_file_with_populated_stats(self):
        """_write_result_file should correctly serialize populated stats."""
        from engine.http_locustfile import _write_result_file

        task_id = "test-populated-stats"
        stats = [
            {
                "task_id": task_id,
                "metric_type": "POST /api",
                "num_requests": 100,
                "num_failures": 5,
                "avg_latency": 50.0,
                "min_latency": 10.0,
                "max_latency": 200.0,
                "median_latency": 45.0,
                "p95_latency": 150.0,
                "rps": 10.0,
                "avg_content_length": 512.0,
            }
        ]
        result_file = _write_result_file(task_id, stats)

        assert os.path.exists(result_file)
        with open(result_file, "r") as f:
            data = json.load(f)
        assert data["locust_stats"] == stats
        assert data["custom_metrics"] == {}

        # Cleanup
        import shutil

        shutil.rmtree(os.path.dirname(result_file))

    def test_on_test_stop_writes_file_when_stats_empty(self):
        """Integration: on_test_stop should write result.json even when
        environment.stats has no entries (e.g., all requests failed during
        aggregation).

        We test this by directly calling on_test_stop with a mock environment
        that simulates the LocalRunner path with empty stats.entries.
        """
        import shutil

        from locust.runners import LocalRunner

        from engine.http_locustfile import on_test_stop

        # Create minimal mock environment
        mock_env = MagicMock()
        mock_env.parsed_options = SimpleNamespace(task_id="test-empty-on-stop")
        mock_env.runner = MagicMock(spec=LocalRunner)
        mock_env.runner.__class__ = LocalRunner
        mock_env._realtime_greenlet = None

        # Empty stats entries — simulates aggregation failure scenario
        mock_env.stats.entries = {}
        mock_env.stats.total = None

        on_test_stop(mock_env)

        # Verify result.json was written
        result_file = os.path.join(
            tempfile.gettempdir(),
            "locust_result",
            "test-empty-on-stop",
            "result.json",
        )
        assert os.path.exists(
            result_file
        ), "result.json must be written even when locust_stats is empty"

        with open(result_file, "r") as f:
            data = json.load(f)
        assert "locust_stats" in data
        assert "custom_metrics" in data
        # The stats list should be empty (no entries to aggregate)
        assert data["locust_stats"] == []

        # Cleanup
        shutil.rmtree(os.path.dirname(result_file))
