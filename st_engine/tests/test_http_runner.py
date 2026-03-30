"""
Tests for HttpLocustRunner command building, multiprocess support,
and warmup phase skipping.
"""

from unittest.mock import Mock, patch

import pytest

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
