"""
Tests for LlmLocustRunner duraton consistency, extra environment variables
initialization, and command building.
"""

import io
import json
import math
import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from engine.http_runner import HttpLocustRunner
from engine.llm_runner import LlmLocustRunner
from utils.logger import SUBPROCESS_LOG_PROTOCOL, SUBPROCESS_LOG_PROTOCOL_ENV


# =====================================================================
# Fixtures
# =====================================================================
@pytest.fixture
def llm_runner(tmp_path):
    """Create a LlmLocustRunner rooted at a temporary directory."""
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "llm_locustfile.py").write_text("# dummy")
    return LlmLocustRunner(str(tmp_path))


@pytest.fixture
def http_runner(tmp_path):
    """Create an HttpLocustRunner rooted at a temporary directory."""
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "http_locustfile.py").write_text("# dummy")
    return HttpLocustRunner(str(tmp_path))


@pytest.fixture
def mock_llm_task():
    """Create a mock LLM Task with stepped-mode fields."""
    task = Mock()
    task.id = "task-fix-002"
    task.target_host = "http://llm.example.com"
    task.api_path = "/v1/chat/completions"
    task.headers = '{"Authorization": "Bearer token"}'
    task.cookies = "{}"
    task.model = "test-model"
    task.api_type = "openai-chat"
    task.stream_mode = "True"
    task.chat_type = 0
    task.concurrent_users = 50
    task.spawn_rate = 10
    task.duration = 120
    task.load_mode = "stepped"
    task.step_start_users = 1
    task.step_increment = 10
    task.step_duration = 30
    task.step_max_users = 100
    task.step_sustain_duration = 60
    task.request_payload = (
        '{"model": "test", "messages": [{"role": "user", "content": "hi"}]}'
    )
    task.field_mapping = None
    task.test_data = None
    task.cert_file = None
    task.key_file = None
    task.warmup_enabled = 0
    return task


# =====================================================================
# Fix 3: _calc_stepped_total_duration matches SteppedLoadShape
# =====================================================================
class TestSteppedDurationConsistency:
    """Verify runner's duration calculation matches the actual SteppedLoadShape."""

    @staticmethod
    def _shape_total_time(start, increment, step_dur, max_users, sustain):
        """Reproduce SteppedLoadShape's total_time calculation exactly."""
        num_steps = max(1, math.ceil((max_users - start) / max(increment, 1)))
        ramp_phase_time = num_steps * step_dur
        return ramp_phase_time + sustain

    def test_default_parameters(self, llm_runner):
        """Default: start=1, increment=10, dur=30, max=100, sustain=60."""
        task = Mock()
        task.step_start_users = 1
        task.step_increment = 10
        task.step_duration = 30
        task.step_max_users = 100
        task.step_sustain_duration = 60

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        shape_duration = self._shape_total_time(1, 10, 30, 100, 60)

        assert runner_duration == shape_duration

    def test_small_increment(self, llm_runner):
        """start=10, increment=1, dur=10, max=20, sustain=30."""
        task = Mock()
        task.step_start_users = 10
        task.step_increment = 1
        task.step_duration = 10
        task.step_max_users = 20
        task.step_sustain_duration = 30

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        shape_duration = self._shape_total_time(10, 1, 10, 20, 30)

        assert runner_duration == shape_duration

    def test_large_increment(self, llm_runner):
        """start=1, increment=100, dur=60, max=500, sustain=120."""
        task = Mock()
        task.step_start_users = 1
        task.step_increment = 100
        task.step_duration = 60
        task.step_max_users = 500
        task.step_sustain_duration = 120

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        shape_duration = self._shape_total_time(1, 100, 60, 500, 120)

        assert runner_duration == shape_duration

    def test_exact_division(self, llm_runner):
        """Increment evenly divides (max - start): start=0, inc=10, max=100."""
        task = Mock()
        task.step_start_users = 0
        task.step_increment = 10
        task.step_duration = 15
        task.step_max_users = 100
        task.step_sustain_duration = 45

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        shape_duration = self._shape_total_time(0, 10, 15, 100, 45)

        assert runner_duration == shape_duration

    def test_single_step(self, llm_runner):
        """Only one step needed: start=90, increment=20, max=100."""
        task = Mock()
        task.step_start_users = 90
        task.step_increment = 20
        task.step_duration = 30
        task.step_max_users = 100
        task.step_sustain_duration = 60

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        shape_duration = self._shape_total_time(90, 20, 30, 100, 60)

        assert runner_duration == shape_duration

    def test_max_equals_start(self, llm_runner):
        """Edge case: max == start → at least 1 step."""
        task = Mock()
        task.step_start_users = 50
        task.step_increment = 10
        task.step_duration = 30
        task.step_max_users = 50
        task.step_sustain_duration = 60

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        shape_duration = self._shape_total_time(50, 10, 30, 50, 60)

        assert runner_duration == shape_duration

    def test_none_parameters_use_defaults(self, llm_runner):
        """When task attributes are None, defaults are used."""
        task = Mock()
        task.step_start_users = None
        task.step_increment = None
        task.step_duration = None
        task.step_max_users = None
        task.step_sustain_duration = None

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        # Defaults: start=1, inc=10, dur=30, max=100, sustain=60
        shape_duration = self._shape_total_time(1, 10, 30, 100, 60)

        assert runner_duration == shape_duration

    @pytest.mark.parametrize(
        "start,increment,step_dur,max_users,sustain",
        [
            (1, 10, 30, 100, 60),
            (5, 5, 20, 50, 30),
            (1, 1, 10, 10, 10),
            (0, 50, 60, 1000, 120),
            (100, 25, 45, 500, 90),
            (1, 7, 30, 99, 60),  # Non-even division
            (3, 13, 25, 200, 80),  # Another non-even
        ],
    )
    def test_parametrized_consistency(
        self, llm_runner, start, increment, step_dur, max_users, sustain
    ):
        """Parametrized check: runner always matches shape for various configs."""
        task = Mock()
        task.step_start_users = start
        task.step_increment = increment
        task.step_duration = step_dur
        task.step_max_users = max_users
        task.step_sustain_duration = sustain

        runner_duration = llm_runner._calc_stepped_total_duration(task)
        shape_duration = self._shape_total_time(
            start, increment, step_dur, max_users, sustain
        )

        assert runner_duration == shape_duration, (
            f"Mismatch for start={start}, inc={increment}, dur={step_dur}, "
            f"max={max_users}, sustain={sustain}: "
            f"runner={runner_duration} vs shape={shape_duration}"
        )


# =====================================================================
# Fix 4: _extra_env is local and thread-safe in _start_process
# =====================================================================
class TestExtraEnvInitialization:
    """Verify extra environment variables are correctly constructed and passed without leakage."""

    def test_extra_env_not_leaked_between_runs(self, llm_runner, mock_llm_task):
        """_start_process should use a local dict and not leak or accumulate state between runs."""
        # Mock out subprocess and port allocation to avoid actual process launch
        with (
            patch("engine.llm_runner.subprocess.Popen") as mock_popen,
            patch("engine.llm_runner.allocate_master_port", return_value=5560),
            patch("engine.llm_runner.register_locust_process_group"),
            patch.object(llm_runner, "_capture_worker_pids", return_value=[]),
            patch.object(llm_runner, "_validate_subprocess_command"),
            patch("engine.llm_runner.mask_sensitive_command", return_value=["masked"]),
        ):
            mock_process = Mock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            mock_logger = Mock()
            llm_runner._start_process(
                ["locust", "-f", "dummy.py", "--processes", "2"],
                mock_llm_task,
                mock_logger,
            )

            # Retrieve the env dictionary passed to Popen in the first run
            assert mock_popen.called
            call_env_1 = mock_popen.call_args[1]["env"]
            assert "LOAD_MODE" in call_env_1
            assert call_env_1["LOAD_MODE"] == "stepped"
            assert call_env_1["SLS_ENABLED"] == "false"
            assert call_env_1[SUBPROCESS_LOG_PROTOCOL_ENV] == SUBPROCESS_LOG_PROTOCOL
            assert mock_popen.call_args.kwargs["stdout"] is subprocess.PIPE
            assert mock_popen.call_args.kwargs["stderr"] is subprocess.STDOUT

            # Run a second task (e.g. non-stepped/fixed) to ensure no accumulation
            mock_llm_task_fixed = Mock()
            mock_llm_task_fixed.id = "fixed-task"
            mock_llm_task_fixed.concurrent_users = 10
            mock_llm_task_fixed.duration = 60
            mock_llm_task_fixed.load_mode = "fixed"

            mock_popen.reset_mock()
            llm_runner._start_process(
                ["locust", "-f", "dummy.py"],
                mock_llm_task_fixed,
                mock_logger,
            )

            # Retrieve the env dictionary passed to Popen in the second run
            assert mock_popen.called
            call_env_2 = mock_popen.call_args[1]["env"]
            assert "LOAD_MODE" not in call_env_2
            assert call_env_2["TASK_DURATION"] == "60"
            assert call_env_2["SLS_ENABLED"] == "false"
            assert call_env_2[SUBPROCESS_LOG_PROTOCOL_ENV] == SUBPROCESS_LOG_PROTOCOL
            assert mock_popen.call_args.kwargs["stderr"] is subprocess.STDOUT


# =====================================================================
# Additional tests for llm_runner stepped mode variables
# =====================================================================
class TestLlmRunnerSteppedModeAndWarmup:
    """Test environment and warmup configuration changes in LlmLocustRunner."""

    def test_start_process_uses_step_max_users_in_stepped_mode(
        self, llm_runner, mock_llm_task
    ):
        """Verify that LOCUST_CONCURRENT_USERS env var uses step_max_users in stepped mode."""
        mock_llm_task.load_mode = "stepped"
        mock_llm_task.step_max_users = 150
        mock_llm_task.concurrent_users = 50

        with (
            patch("engine.llm_runner.subprocess.Popen") as mock_popen,
            patch("engine.llm_runner.allocate_master_port", return_value=5560),
            patch("engine.llm_runner.register_locust_process_group"),
            patch.object(llm_runner, "_capture_worker_pids", return_value=[]),
            patch.object(llm_runner, "_validate_subprocess_command"),
            patch("engine.llm_runner.mask_sensitive_command", return_value=["masked"]),
        ):
            mock_process = Mock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            llm_runner._start_process(
                ["locust", "-f", "dummy.py"],
                mock_llm_task,
                Mock(),
            )

            # Get the env kwargs passed to Popen
            called_kwargs = mock_popen.call_args.kwargs
            called_env = called_kwargs.get("env", {})
            assert called_env.get("LOCUST_CONCURRENT_USERS") == "150"

    def test_start_process_uses_concurrent_users_in_fixed_mode(
        self, llm_runner, mock_llm_task
    ):
        """Verify that LOCUST_CONCURRENT_USERS env var uses concurrent_users in fixed mode."""
        mock_llm_task.load_mode = "fixed"
        mock_llm_task.step_max_users = 150
        mock_llm_task.concurrent_users = 50

        with (
            patch("engine.llm_runner.subprocess.Popen") as mock_popen,
            patch("engine.llm_runner.allocate_master_port", return_value=5560),
            patch("engine.llm_runner.register_locust_process_group"),
            patch.object(llm_runner, "_capture_worker_pids", return_value=[]),
            patch.object(llm_runner, "_validate_subprocess_command"),
            patch("engine.llm_runner.mask_sensitive_command", return_value=["masked"]),
        ):
            mock_process = Mock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            llm_runner._start_process(
                ["locust", "-f", "dummy.py"],
                mock_llm_task,
                Mock(),
            )

            # Get the env kwargs passed to Popen
            called_kwargs = mock_popen.call_args.kwargs
            called_env = called_kwargs.get("env", {})
            assert called_env.get("LOCUST_CONCURRENT_USERS") == "50"

    def test_build_warmup_command_uses_warmup_users(self, llm_runner, mock_llm_task):
        """Verify that _build_warmup_command uses warmup_users for process count."""
        mock_llm_task.warmup_enabled = 1
        mock_llm_task.concurrent_users = 10

        with (
            patch("engine.llm_runner.get_cpu_count", return_value=8),
            patch(
                "engine.llm_runner.get_process_count", return_value=4
            ) as mock_get_process_count,
            patch(
                "engine.llm_runner.should_enable_multiprocess", return_value=True
            ) as mock_should_enable,
        ):
            cmd = llm_runner._build_warmup_command(
                mock_llm_task, Mock(), warmup_duration=10, warmup_users=200
            )

            # get_process_count and should_enable_multiprocess must be called with warmup_users (200)
            mock_get_process_count.assert_called_with(200, 8)
            mock_should_enable.assert_called_with(200, 8)

            # The cmd must contain the --processes 4 argument
            assert "--processes" in cmd
            idx = cmd.index("--processes")
            assert cmd[idx + 1] == "4"


class TestJsonLineLogCapture:
    SUMMARY_OUTPUT = """Type     Name                                                                          # reqs      # fails |    Avg     Min     Max    Med |   req/s  failures/s
--------|----------------------------------------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
GET      GET /v1/chat/completions                                                       20     0(0.00%) |     50      20      90     45 |    2.00        0.00
--------|----------------------------------------------------------------------------|-------|-------------|-------|-------|-------|-------|--------|-----------
         Aggregated                                                                    20     0(0.00%) |     50      20      90     45 |    2.00        0.00"""

    @staticmethod
    def _encoded_event(message):
        return (
            json.dumps(
                {
                    "protocol": SUBPROCESS_LOG_PROTOCOL,
                    "level": "INFO",
                    "message": message,
                    "logger": "locust.stats_logger",
                    "time": "2026-08-03T14:07:41.440",
                    "file": "stats.py",
                    "line": 789,
                    "function": "print_stats",
                    "process": 123,
                    "thread": 456,
                },
                separators=(",", ":"),
            )
            + "\n"
        )

    def test_monitor_forwards_table_once_and_retains_decoded_summary(self, llm_runner):
        process = Mock()
        process.pid = 12345
        process.returncode = 0
        process.stdout = io.StringIO(self._encoded_event(self.SUMMARY_OUTPUT))
        # Production Popen redirects stderr to stdout, so no separate stderr
        # stream exists and the captured summary must still be parseable.
        process.stderr = None

        task = Mock()
        task.id = "jsonl-task"
        task.duration = 10
        task.load_mode = "fixed"

        task_logger = Mock()
        bound_logger = Mock()
        task_logger.bind.return_value = bound_logger

        stdout, stderr = llm_runner._monitor_and_capture(process, task, task_logger)

        assert stdout == f"{self.SUMMARY_OUTPUT}\n"
        assert stderr == ""
        task_logger.bind.assert_called_once()
        assert task_logger.bind.call_args.kwargs["subprocess_stream"] == "stdout"
        bound_logger.log.assert_called_once_with("INFO", self.SUMMARY_OUTPUT)

        rows = llm_runner._parse_locust_summary(stdout, task.id)
        assert len(rows) == 1
        assert rows[0]["metric_type"] == "GET /v1/chat/completions"
        assert rows[0]["num_requests"] == 20
