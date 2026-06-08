"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import math
import os
import shutil
import subprocess  # nosec B404
import tempfile
import threading
import time
from collections import deque
from typing import Dict, List, Tuple

import psutil

from config.base import (
    LOCUST_STOP_TIMEOUT,
    LOCUST_WAIT_TIMEOUT_BUFFER,
    MAX_CAPTURED_OUTPUT_BYTES,
)
from config.multiprocess import (
    get_cpu_count,
    get_process_count,
    should_enable_multiprocess,
)
from engine.process_manager import (
    allocate_master_port,
    cleanup_task_resources,
    register_locust_process_group,
    release_task_port,
    terminate_locust_process_group,
)
from model.llm_task import Task
from utils.common import mask_sensitive_command
from utils.logger import logger


class _OutputTailBuffer:
    """Bound retained subprocess output while preserving recent diagnostics."""

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max(0, int(max_bytes or 0))
        self._lines: deque[str] = deque()
        self._bytes = 0
        self.truncated = False

    @staticmethod
    def _line_size(line: str) -> int:
        return len(line.encode("utf-8", errors="replace"))

    def append(self, line: str) -> None:
        if self.max_bytes <= 0:
            self.truncated = True
            return

        size = self._line_size(line)
        if size > self.max_bytes:
            encoded = line.encode("utf-8", errors="replace")[-self.max_bytes :]
            line = encoded.decode("utf-8", errors="ignore")
            size = self._line_size(line)
            self._lines.clear()
            self._bytes = 0
            self.truncated = True

        self._lines.append(line)
        self._bytes += size

        while self._bytes > self.max_bytes and self._lines:
            dropped = self._lines.popleft()
            self._bytes -= self._line_size(dropped)
            self.truncated = True

    def text(self) -> str:
        return "".join(self._lines)


class LlmLocustRunner:
    """
    Enhanced Locust runner with robust multiprocess management.
    """

    _STOPPED_IDS_HARD_CAP = 500
    _WARMUP_DURATION_SECONDS = 120
    _WARMUP_COOLDOWN_SECONDS = 3
    _WARMUP_STOP_TIMEOUT_SECONDS = 10

    def __init__(self, base_dir: str):
        """Create a runner rooted at the given repository directory."""
        self.base_dir = base_dir
        self._locustfile_path = os.path.join(
            self.base_dir, "engine", "llm_locustfile.py"
        )
        self._process_dict: dict[str, subprocess.Popen] = {}
        self._stopped_task_ids: set[str] = set()

    def _cleanup_stale_stopped_ids(self) -> int:
        """Remove stopped task IDs that have no corresponding active process.

        Returns the number of entries removed.
        """
        if len(self._stopped_task_ids) > self._STOPPED_IDS_HARD_CAP:
            logger.warning(
                f"_stopped_task_ids exceeded hard cap ({len(self._stopped_task_ids)}). "
                f"Force clearing to prevent memory leak."
            )
            self._stopped_task_ids.clear()
            return 0
        stale_ids = self._stopped_task_ids - set(self._process_dict.keys())
        for task_id in stale_ids:
            self._stopped_task_ids.discard(task_id)
        return len(stale_ids)

    # --- Shared stepped load helpers ---

    @staticmethod
    def _safe_int(value, default: int) -> int:
        """Return *value* as int if it is not None, otherwise *default*.

        Unlike ``value or default``, this correctly preserves 0 as a valid
        value instead of silently falling back to *default*.
        """
        if value is None:
            return default
        return int(value)

    def _get_stepped_env(self, task) -> Dict[str, str]:
        """Build environment variables for stepped load mode.

        Works with any task object that has step_* attributes (Task or HttpTask).
        """
        return {
            "LOAD_MODE": "stepped",
            "STEP_START_USERS": str(
                self._safe_int(getattr(task, "step_start_users", None), 1)
            ),
            "STEP_INCREMENT": str(
                self._safe_int(getattr(task, "step_increment", None), 10)
            ),
            "STEP_DURATION": str(
                self._safe_int(getattr(task, "step_duration", None), 30)
            ),
            "STEP_MAX_USERS": str(
                self._safe_int(getattr(task, "step_max_users", None), 100)
            ),
            "STEP_SUSTAIN_DURATION": str(
                self._safe_int(getattr(task, "step_sustain_duration", None), 60)
            ),
        }

    def _calc_stepped_total_duration(self, task) -> int:
        """Calculate total duration for stepped load mode.

        Works with any task object that has step_* attributes.
        Must match SteppedLoadShape's total_time calculation exactly.
        """
        start = self._safe_int(getattr(task, "step_start_users", None), 1)
        increment = self._safe_int(getattr(task, "step_increment", None), 10)
        step_dur = self._safe_int(getattr(task, "step_duration", None), 30)
        max_users = self._safe_int(getattr(task, "step_max_users", None), 100)
        sustain = self._safe_int(getattr(task, "step_sustain_duration", None), 60)

        num_steps = max(1, math.ceil((max_users - start) / max(increment, 1)))
        return num_steps * step_dur + sustain

    def _get_load_mode(self, task) -> str:
        """Return the load mode for the task ('fixed' or 'stepped')."""
        return getattr(task, "load_mode", "fixed") or "fixed"

    def run_locust_process(self, task: Task) -> dict:
        """
        Run Locust test as a separate process with full lifecycle management.
        For LLM API tasks, runs a warmup phase first to avoid cold start interference.
        """
        task_logger = logger.bind(task_id=task.id)

        # Opportunistic cleanup of stale stopped IDs to prevent memory leak
        cleaned = self._cleanup_stale_stopped_ids()
        if cleaned:
            task_logger.debug(f"Cleaned {cleaned} stale stopped task IDs")

        try:
            # Step 1: Prepare environment
            self._prepare_task(task, task_logger)

            # Step 1.5: Run warmup phase for LLM API tasks
            self._run_warmup_phase(task, task_logger)

            # Step 2: Build and start process
            cmd = self._build_locust_command(task, task_logger)
            process = self._start_process(cmd, task, task_logger)

            # Step 3: Monitor and capture output
            stdout, stderr = self._monitor_and_capture(process, task, task_logger)

            # Step 4: Finalize and load results
            result = self._finalize_task(process, task, stdout, stderr, task_logger)
            return result

        except InterruptedError as e:
            # Task was stopped during warmup phase
            task_logger.info(f"Task {task.id} was stopped during warmup: {e}")
            return {
                "status": "STOPPED",
                "stdout": "",
                "stderr": str(e),
                "return_code": -15,  # SIGTERM
                "locust_result": {},
            }
        except Exception as e:
            task_logger.exception(f"Unhandled exception during Locust execution: {e}")
            return {
                "status": "FAILED",
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "locust_result": {},
            }
        finally:
            # Always discard from stopped set to prevent memory leak
            self._stopped_task_ids.discard(task.id)

            # Emergency cleanup if process still tracked (abnormal exit)
            if task.id in self._process_dict:
                task_logger.warning(
                    f"Task {task.id} exited abnormally. Triggering emergency cleanup."
                )
                self._cleanup_task_resources(task, task_logger)
            else:
                # Even on normal exit, ensure port is released in case cleanup
                # missed it (e.g., no process group was ever registered).
                release_task_port(task.id)

    def _prepare_task(self, task: Task, task_logger) -> None:
        """Prepare task environment: validate config and files."""
        # NOTE: Avoid global process cleanup here; it can terminate unrelated
        # Locust runs (e.g., model vs HTTP API tasks) that are running
        # concurrently. Stale processes are reconciled in pollers/startup
        # routines instead of per-task execution.
        if not os.path.exists(self._locustfile_path):
            raise FileNotFoundError(f"Locustfile not found at {self._locustfile_path}")

    def _validate_subprocess_command(self, cmd: List[str], context: str) -> None:
        """Basic safety validation for subprocess command args."""
        if not isinstance(cmd, list) or not cmd:
            raise ValueError(f"{context} command must be a non-empty list")
        if not all(isinstance(arg, str) and arg for arg in cmd):
            raise ValueError(f"{context} command args must be non-empty strings")
        if any("\x00" in arg for arg in cmd):
            raise ValueError(f"{context} command contains null byte")

    def _run_warmup_phase(self, task: Task, task_logger) -> None:
        """
        Run warmup phase before the actual test to avoid cold start interference.
        Uses original payload (no dataset), same concurrency.
        After warmup, waits 10 seconds to let KV Cache stabilize.

        Warmup can be enabled/disabled and duration can be configured via task settings.
        """
        # Check if warmup is enabled (handle both boolean and integer from database)
        warmup_enabled = getattr(task, "warmup_enabled", 1)
        # Convert to boolean: 0 or False means disabled
        if warmup_enabled == 0 or warmup_enabled is False:
            task_logger.info("Warmup phase is disabled, skipping")
            return

        # Get warmup duration from task settings (default to 120s if not set)
        warmup_duration = getattr(
            task, "warmup_duration", self._WARMUP_DURATION_SECONDS
        )
        if not isinstance(warmup_duration, int) or warmup_duration <= 0:
            warmup_duration = self._WARMUP_DURATION_SECONDS

        # In stepped mode, warmup uses the max concurrency (step_max_users)
        load_mode = self._get_load_mode(task)
        warmup_users = (
            getattr(task, "step_max_users", None) or task.concurrent_users
            if load_mode == "stepped"
            else task.concurrent_users
        )
        task_logger.info(
            f"Starting warmup phase: {warmup_duration}s with {warmup_users} users"
            f" (load_mode={load_mode})"
        )

        warmup_task_id = f"{task.id}_warmup"

        # Build warmup command (no test_data, with warmup_mode flag)
        warmup_cmd = self._build_warmup_command(
            task, task_logger, warmup_duration, warmup_users
        )
        self._validate_subprocess_command(warmup_cmd, "Warmup")
        masked_cmd = mask_sensitive_command(warmup_cmd)
        task_logger.info(f"Warmup command: {' '.join(masked_cmd)}")

        env = os.environ.copy()
        env["TASK_ID"] = warmup_task_id
        env["LOCUST_CONCURRENT_USERS"] = str(warmup_users)
        # Warmup uses INFO level to avoid OOM from large payloads (e.g. base64
        # images) being repr'd into DEBUG log lines in each worker process.
        if "LOG_LEVEL" not in env:
            env["LOG_LEVEL"] = "INFO"

        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{self.base_dir}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else self.base_dir
        )

        # Allocate port BEFORE starting warmup process to avoid conflicts.
        # Only allocate if --processes is in the command.
        warmup_port = None
        if "--processes" in warmup_cmd:
            try:
                warmup_port = allocate_master_port(warmup_task_id)
                warmup_cmd.extend(["--master-bind-port", str(warmup_port)])
                task_logger.info(f"Allocated master port {warmup_port} for warmup")
            except Exception as e:
                task_logger.warning(f"Failed to allocate warmup master port: {e}")

        # Expose process count for locustfile (avoid LOCUST_PROCESSES which
        # Locust interprets as --processes)
        try:
            proc_idx = warmup_cmd.index("--processes")
            env["LMETERX_PROCESS_COUNT"] = warmup_cmd[proc_idx + 1]
        except (ValueError, IndexError):
            env["LMETERX_PROCESS_COUNT"] = "1"

        warmup_process = None
        try:
            warmup_process = subprocess.Popen(
                warmup_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                shell=False,  # nosec B603 - validated args, no shell
            )
            task_logger.info(f"Warmup process started with PID={warmup_process.pid}")

            # Register warmup process in _process_dict for stop handling
            # Use warmup_task_id as key so stop_task can find it
            self._process_dict[warmup_task_id] = warmup_process

            # Handle multiprocess registration for warmup
            if warmup_port is not None:
                try:
                    warmup_worker_pids = self._capture_worker_pids(
                        warmup_process.pid, warmup_task_id, task_logger
                    )
                    if warmup_worker_pids:
                        register_locust_process_group(
                            warmup_task_id,
                            warmup_process.pid,
                            warmup_worker_pids,
                            warmup_port,
                        )
                        task_logger.info(
                            f"Registered warmup process group: master={warmup_process.pid}, workers={warmup_worker_pids}"
                        )
                except Exception as e:
                    task_logger.warning(
                        f"Failed to register warmup multiprocess group: {e}"
                    )

            # Read and log warmup output in real-time using threads
            def read_warmup_stream(pipe, prefix):
                try:
                    for line in iter(pipe.readline, ""):
                        if line.strip():
                            if " | DEBUG    | " in line or " | DEBUG | " in line:
                                task_logger.opt(raw=True).debug(f"{line}")
                            elif " | WARNING  | " in line or " | WARNING | " in line:
                                task_logger.opt(raw=True).warning(f"{line}")
                            elif " | ERROR    | " in line or " | ERROR | " in line:
                                task_logger.opt(raw=True).error(f"{line}")
                            else:
                                task_logger.opt(raw=True).info(f"{line}")
                    pipe.close()
                except Exception as e:
                    task_logger.debug(f"Error reading warmup {prefix}: {e}")

            stdout_thread = threading.Thread(
                target=read_warmup_stream, args=(warmup_process.stdout, "stdout")
            )
            stderr_thread = threading.Thread(
                target=read_warmup_stream, args=(warmup_process.stderr, "stderr")
            )
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            # Wait for warmup to complete with timeout buffer
            # _WARMUP_STOP_TIMEOUT_SECONDS (10s) is how long Locust waits for
            # in-flight requests after --run-time expires; add extra buffer
            # for process exit
            warmup_timeout = (
                warmup_duration
                + self._WARMUP_STOP_TIMEOUT_SECONDS
                + LOCUST_WAIT_TIMEOUT_BUFFER
            )
            try:
                warmup_process.wait(timeout=warmup_timeout)
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                task_logger.info(
                    f"Warmup phase completed with exit code {warmup_process.returncode}"
                )
            except subprocess.TimeoutExpired:
                task_logger.warning("Warmup process timed out, terminating...")
                warmup_process.terminate()
                try:
                    warmup_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    warmup_process.kill()
                    warmup_process.wait()

            # Check if warmup was stopped externally (user clicked stop)
            # Check 1: Process was killed by signal (negative return code)
            # Check 2: Task was marked as stopped via _stopped_task_ids
            was_stopped = False
            if warmup_process.returncode is not None and warmup_process.returncode < 0:
                task_logger.info(
                    f"Warmup was terminated by signal {-warmup_process.returncode}."
                )
                was_stopped = True
            elif task.id in self._stopped_task_ids:
                task_logger.info(
                    f"Task {task.id} was marked as stopped during warmup phase."
                )
                was_stopped = True

            if was_stopped:
                # Raise an exception to abort the main test
                raise InterruptedError("Task was stopped during warmup phase")

        except InterruptedError:
            # Re-raise to propagate stop signal
            raise
        except Exception as e:
            task_logger.warning(f"Warmup phase failed: {e}, continuing with main test")
        finally:
            # Cleanup warmup process tracking
            self._process_dict.pop(warmup_task_id, None)

            # Terminate multiprocess group if applicable
            terminate_locust_process_group(warmup_task_id, timeout=10.0)

            # Cleanup warmup task resources (including port release)
            cleanup_task_resources(warmup_task_id)

            # Cleanup any remaining warmup processes
            warmup_pids = self._find_remaining_locust_processes(warmup_task_id)
            for pid in warmup_pids:
                try:
                    p = psutil.Process(pid)
                    p.kill()
                    task_logger.debug(f"Killed remaining warmup process {pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        # Wait for KV Cache to stabilize
        task_logger.info(
            f"Warmup completed. Waiting {self._WARMUP_COOLDOWN_SECONDS}s for KV Cache to stabilize..."
        )
        time.sleep(self._WARMUP_COOLDOWN_SECONDS)
        task_logger.info("Starting main test phase")

    def _build_warmup_command(
        self, task: Task, task_logger, warmup_duration: int, warmup_users: int = 0
    ) -> List[str]:
        """Build Locust command for warmup phase (no dataset, warmup_mode enabled).

        Args:
            task: The task configuration.
            task_logger: Logger instance bound to the task.
            warmup_duration: Pre-validated warmup duration in seconds.
                Resolved and validated by ``_run_warmup_phase`` before calling.
            warmup_users: Number of concurrent users for warmup.
                In stepped mode, this is ``step_max_users``.
        """
        if not warmup_users:
            warmup_users = int(task.concurrent_users)
        locust_bin = shutil.which("locust") or "locust"
        # Use a short stop-timeout for warmup: after --run-time expires,
        # Locust will forcibly kill remaining users within this timeout.
        # Without this, Locust waits indefinitely for in-flight LLM streaming
        # requests to complete, causing the warmup phase to never end on time.
        cmd = [
            locust_bin,
            "-f",
            self._locustfile_path,
            "--host",
            task.target_host,
            "--users",
            str(warmup_users),
            "--spawn-rate",
            str(task.spawn_rate),
            "--run-time",
            f"{warmup_duration}s",
            "--stop-timeout",
            f"{self._WARMUP_STOP_TIMEOUT_SECONDS}s",
            "--duration",
            str(warmup_duration),
            "--headless",
            "--only-summary",
            "--api_path",
            task.api_path or "/chat/completions",
            "--headers",
            task.headers,
            "--cookies",
            task.cookies or "{}",
            "--model_name",
            task.model or "",
            "--api_type",
            getattr(task, "api_type", "openai-chat") or "openai-chat",
            "--stream_mode",
            task.stream_mode,
            "--chat_type",
            str(task.chat_type or 0),
            "--task-id",
            f"{task.id}_warmup",
            "--warmup_mode",
            "true",
        ]

        # Handle multiprocess for high concurrency warmup
        cpu_count = get_cpu_count()
        process_count = get_process_count(warmup_users, cpu_count)

        if should_enable_multiprocess(warmup_users, cpu_count) and process_count > 1:
            cmd.extend(["--processes", str(process_count)])
            task_logger.info(f"Warmup multi-process enabled: {process_count} workers")

        # Include request_payload and field_mapping for warmup
        # but NOT test_data (to use original payload)
        for key, value in [
            ("request_payload", task.request_payload),
            ("field_mapping", task.field_mapping),
            ("cert_file", task.cert_file),
            ("key_file", task.key_file),
        ]:
            if value:
                cmd.extend([f"--{key}", value])

        return cmd

    def _build_locust_command(self, task: Task, task_logger) -> List[str]:
        """Build Locust command based on task config."""
        locust_bin = shutil.which("locust") or "locust"
        load_mode = self._get_load_mode(task)

        cmd = [
            locust_bin,
            "-f",
            self._locustfile_path,
            "--host",
            task.target_host,
            "--stop-timeout",
            f"{LOCUST_STOP_TIMEOUT}s",
            "--headless",
            "--only-summary",
            "--api_path",
            task.api_path or "/chat/completions",
            "--headers",
            task.headers,
            "--cookies",
            task.cookies or "{}",
            "--model_name",
            task.model or "",
            "--api_type",
            getattr(task, "api_type", "openai-chat") or "openai-chat",
            "--stream_mode",
            task.stream_mode,
            "--chat_type",
            str(task.chat_type or 0),
            "--task-id",
            task.id,
        ]

        if load_mode == "stepped":
            # In stepped mode, LoadTestShape controls users/run-time/spawn-rate.
            # Do NOT pass --users / --run-time / --spawn-rate.
            task_logger.info(
                f"Stepped load mode: start={getattr(task, 'step_start_users', 1)}, "
                f"increment={getattr(task, 'step_increment', 10)}, "
                f"step_duration={getattr(task, 'step_duration', 30)}s, "
                f"max={getattr(task, 'step_max_users', 100)}, "
                f"sustain={getattr(task, 'step_sustain_duration', 60)}s"
            )
        else:
            # Fixed concurrency mode - pass standard Locust args
            cmd.extend(
                [
                    "--users",
                    str(task.concurrent_users),
                    "--spawn-rate",
                    str(task.spawn_rate),
                    "--run-time",
                    f"{task.duration}s",
                    "--duration",
                    str(task.duration),
                ]
            )

        cpu_count = get_cpu_count()
        concurrent_users = (
            int(getattr(task, "step_max_users", None) or task.concurrent_users)
            if load_mode == "stepped"
            else int(task.concurrent_users)
        )
        process_count = get_process_count(concurrent_users, cpu_count)

        if (
            should_enable_multiprocess(concurrent_users, cpu_count)
            and process_count > 1
        ):
            cmd.extend(["--processes", str(process_count)])
            task_logger.info(
                f"Multi-process enabled: {process_count} workers (CPU={cpu_count}, users={concurrent_users})"
            )

        # Optional args
        for key, value in [
            ("request_payload", task.request_payload),
            ("field_mapping", task.field_mapping),
            ("test_data", task.test_data),
            ("cert_file", task.cert_file),
            ("key_file", task.key_file),
        ]:
            if value:
                cmd.extend([f"--{key}", value])

        return cmd

    def _start_process(
        self, cmd: List[str], task: Task, task_logger
    ) -> subprocess.Popen:
        """Start Locust subprocess and register multiprocess group if needed."""
        # Inject stepped load env vars and task duration
        load_mode = self._get_load_mode(task)
        extra_env: dict[str, str] = {}
        if load_mode == "stepped":
            extra_env.update(self._get_stepped_env(task))
            extra_env["TASK_DURATION"] = str(self._calc_stepped_total_duration(task))
        else:
            extra_env["TASK_DURATION"] = str(task.duration)

        # Allocate a unique master port BEFORE starting the process to avoid
        # port conflicts when multiple tasks run concurrently.
        # Only allocate if --processes is actually in the command (i.e., the
        # build step decided multiprocess is needed AND process_count > 1).
        master_port = None
        if "--processes" in cmd:
            try:
                master_port = allocate_master_port(task.id)
                cmd.extend(["--master-bind-port", str(master_port)])
                task_logger.info(f"Allocated master port {master_port} for task")
            except Exception as e:
                task_logger.warning(f"Failed to allocate master port: {e}")

        self._validate_subprocess_command(cmd, "Locust")
        masked_cmd = mask_sensitive_command(cmd)
        task_logger.info(f"Executing: {' '.join(masked_cmd)}")

        env = os.environ.copy()
        env["TASK_ID"] = str(task.id)

        # Use step_max_users in stepped mode, otherwise concurrent_users
        effective_users = (
            (getattr(task, "step_max_users", None) or task.concurrent_users)
            if load_mode == "stepped"
            else task.concurrent_users
        )
        env["LOCUST_CONCURRENT_USERS"] = str(effective_users)

        # Expose process count so locustfiles can detect multiprocess mode
        # and use shared memory for datasets instead of per-process copies.
        # Use LMETERX_PROCESS_COUNT (not LOCUST_PROCESSES) to avoid triggering
        # Locust's built-in --processes env var parsing.
        try:
            proc_idx = cmd.index("--processes")
            env["LMETERX_PROCESS_COUNT"] = cmd[proc_idx + 1]
        except (ValueError, IndexError):
            env["LMETERX_PROCESS_COUNT"] = "1"

        # Ensure Locust subprocess can import project modules
        # Subprocess log level follows DETAIL_LOG_LEVEL (defaults to LOG_LEVEL).
        # Users can set DETAIL_LOG_LEVEL=DEBUG to capture request payloads in
        # the detailed task log without impacting normal operation.
        env["LOG_LEVEL"] = os.environ.get(
            "DETAIL_LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO")
        )

        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{self.base_dir}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else self.base_dir
        )
        # Apply extra env vars (stepped load config, task duration, etc.)
        if extra_env:
            env.update(extra_env)
            task_logger.debug(f"Applied extra env vars: {list(extra_env.keys())}")
        task_logger.debug(
            f"Setting LOCUST_CONCURRENT_USERS={env['LOCUST_CONCURRENT_USERS']} from task.concurrent_users={task.concurrent_users}"
        )
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            shell=False,  # nosec B603 - command is constructed with validated args and no shell
        )
        self._process_dict[task.id] = process
        task_logger.info(f"Started Locust process PID={process.pid}")

        # Handle multiprocess registration
        if master_port is not None:
            try:
                worker_pids = self._capture_worker_pids(
                    process.pid, task.id, task_logger
                )
                if worker_pids:
                    register_locust_process_group(
                        task.id, process.pid, worker_pids, master_port
                    )
                    task_logger.info(
                        f"Registered group: master={process.pid}, workers={worker_pids}"
                    )
                else:
                    task_logger.warning("No worker processes detected")
            except Exception as e:
                task_logger.warning(f"Failed to register multiprocess group: {e}")

        return process

    def _monitor_and_capture(
        self, process: subprocess.Popen, task: Task, task_logger
    ) -> Tuple[str, str]:
        """Monitor process execution and capture real-time output."""
        stdout_buffer = _OutputTailBuffer(MAX_CAPTURED_OUTPUT_BYTES)
        stderr_buffer = _OutputTailBuffer(MAX_CAPTURED_OUTPUT_BYTES)

        def read_stream(pipe, output_buffer, name):
            if pipe is None:
                return
            try:
                for line in iter(pipe.readline, ""):
                    if line.strip():
                        output_buffer.append(line)
                        if " | DEBUG    | " in line or " | DEBUG | " in line:
                            task_logger.opt(raw=True).debug(line)
                        elif " | WARNING  | " in line or " | WARNING | " in line:
                            task_logger.opt(raw=True).warning(line)
                        elif " | ERROR    | " in line or " | ERROR | " in line:
                            task_logger.opt(raw=True).error(line)
                        else:
                            task_logger.opt(raw=True).info(line)
                pipe.close()
            except Exception as e:
                task_logger.error(f"Error reading {name}: {e}")

        stdout_thread = threading.Thread(
            target=read_stream, args=(process.stdout, stdout_buffer, "stdout")
        )
        stderr_thread = threading.Thread(
            target=read_stream, args=(process.stderr, stderr_buffer, "stderr")
        )

        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        # Use stepped total duration for timeout calculation if applicable
        load_mode = self._get_load_mode(task)
        effective_duration = task.duration
        if load_mode == "stepped":
            effective_duration = self._calc_stepped_total_duration(task)
            task_logger.info(
                f"Stepped mode: overriding timeout duration to {effective_duration}s "
                f"(original fixed duration: {task.duration}s)"
            )

        total_timeout = (
            effective_duration + LOCUST_STOP_TIMEOUT + LOCUST_WAIT_TIMEOUT_BUFFER
        )

        try:
            process.wait(timeout=total_timeout)
            task_logger.info(
                f"Process {process.pid} exited with code {process.returncode}"
            )
        except subprocess.TimeoutExpired:
            task_logger.error(
                f"Process {process.pid} timed out after {total_timeout}s. Terminating..."
            )
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                task_logger.error("Process did not terminate gracefully. Killing...")
                process.kill()
                process.wait()

        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=10)

        stdout = stdout_buffer.text()
        stderr = stderr_buffer.text()
        if stdout_buffer.truncated or stderr_buffer.truncated:
            task_logger.warning(
                "Subprocess output exceeded in-memory capture limit; "
                f"retained last {MAX_CAPTURED_OUTPUT_BYTES} bytes per stream."
            )

        return stdout, stderr

    def _finalize_task(
        self,
        process: subprocess.Popen,
        task: Task,
        stdout: str,
        stderr: str,
        task_logger,
    ) -> dict:
        """Load result and perform cleanup."""
        # Check if task was manually stopped (killed by signal or marked as stopped).
        # In multi-worker/multi-replica deployments, the stop request may land on
        # a different process than the one running the task, so _stopped_task_ids
        # won't reflect the stop.  Fall back to detecting SIGTERM in stderr output.
        # Locust logs in native format ("locust.main: Got SIGTERM signal") while
        # LMeterX's custom handler uses loguru format ("Got SIGTERM signal").
        # Guard against None and check both streams for robustness against log
        # redirection in container environments.
        _stdout = stdout or ""
        _stderr = stderr or ""
        _combined_output = _stdout + _stderr
        _sigterm_detected = (
            "locust.main: Got SIGTERM signal" in _combined_output
            or "Got SIGTERM signal" in _combined_output
        )
        # Determine if the task was intentionally stopped vs. killed by external
        # forces (OOM killer, cgroup limit, etc.).
        # Only these indicate an intentional stop:
        #   1. Explicit stop request recorded in _stopped_task_ids
        #   2. SIGTERM (-15) — our stop logic always sends SIGTERM first
        #   3. SIGTERM detected in Locust logs (multi-replica: stop landed elsewhere)
        # SIGKILL (-9) without an explicit stop request means the process was
        # forcefully killed by the kernel (OOM) or external system — treat as FAILED.
        _explicitly_stopped = task.id in self._stopped_task_ids
        _killed_by_sigterm = (
            process is not None
            and process.returncode is not None
            and process.returncode == -15
        )
        was_stopped = (
            _explicitly_stopped
            or _killed_by_sigterm
            or (
                _sigterm_detected and "--run-time limit reached" not in _combined_output
            )
        )
        # External kill (OOM, cgroup pressure, etc.) — not an intentional stop
        was_killed_externally = (
            not was_stopped
            and process is not None
            and process.returncode is not None
            and process.returncode < 0
        )

        result_file = os.path.join(
            tempfile.gettempdir(), "locust_result", task.id, "result.json"
        )

        if not os.path.exists(result_file):
            if was_stopped:
                # Task was manually stopped – the process was killed before it
                # could write result.json.  This is expected behaviour, not an error.
                task_logger.info(
                    f"Task was stopped (exit code {process.returncode}). "
                    f"No result file expected."
                )
                locust_result = {}
                status = "STOPPED"
            elif was_killed_externally:
                signal_num = -process.returncode
                if signal_num == 9:
                    error_msg = (
                        f"Process was killed by SIGKILL (signal 9). "
                        f"This is typically caused by the container OOM killer "
                        f"(cgroup memory limit exceeded). "
                        f"Please increase the engine Pod memory limit or reduce "
                        f"test concurrency."
                    )
                    task_logger.error(
                        f"[OOM] Task {task.id} was OOM-killed. "
                        f"Exit code: -9 (SIGKILL). "
                        f"The container memory limit may be insufficient for "
                        f"the current workload."
                    )
                else:
                    error_msg = (
                        f"Process was killed by signal {signal_num}. "
                        f"This indicates an abnormal engine termination."
                    )
                    task_logger.error(
                        f"Task {task.id} process killed by signal {signal_num}."
                    )
                locust_result = {}
                status = "FAILED"
            else:
                # Distinguish engine crash vs. requests-all-failed:
                # If Locust completed its run-time normally but result.json is
                # missing (e.g. on_test_stop interrupted by SIGTERM during
                # shutdown), this is a request-level failure, not an engine failure.
                run_time_completed = "--run-time limit reached" in _combined_output
                locust_request_failure_exit = (
                    process is not None
                    and process.returncode is not None
                    and process.returncode == 1
                )
                if run_time_completed and locust_request_failure_exit:
                    task_logger.warning(
                        "Locust completed run-time but result.json missing "
                        "(likely shutdown interrupted). Treating as FAILED_REQUESTS."
                    )
                    locust_result = {}
                    status = "FAILED_REQUESTS"
                else:
                    error_msg = f"Result file not found: {result_file}"
                    task_logger.error(error_msg)
                    locust_result = {}
                    status = "FAILED"
        else:
            locust_result = self._load_locust_result(result_file, task.id, task_logger)
            if was_stopped:
                # Stopped but managed to write partial results
                status = "STOPPED"
            elif was_killed_externally:
                status = "FAILED"
            elif process is not None and process.returncode == 0:
                status = "COMPLETED"
            else:
                status = "FAILED_REQUESTS"
            if status == "FAILED_REQUESTS":
                task_logger.warning(
                    f"Locust test completed with failures (exit code {process.returncode})"
                )

        # Cleanup
        self._cleanup_task(task, process, task_logger)

        return {
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "return_code": process.returncode,
            "locust_result": locust_result,
        }

    def _cleanup_task(self, task: Task, process: subprocess.Popen, task_logger) -> None:
        """Perform comprehensive cleanup after task completion."""
        self._cleanup_task_resources(task, task_logger)

    def _cleanup_task_resources(self, task, task_logger) -> None:
        """Core cleanup logic that does not require a process object."""
        task_id = task.id
        task_logger.info(f"Starting cleanup for task {task_id}")

        # Remove from process dict (this is safe and should be done first)
        self._process_dict.pop(task_id, None)

        # Remove from stopped task set to avoid memory leak
        self._stopped_task_ids.discard(task_id)

        # Unconditionally attempt to terminate multiprocess group and release port.
        # terminate_locust_process_group safely handles the case where no group
        # exists. This avoids relying on should_enable_multiprocess() which can
        # give a different answer at cleanup time than at startup time.
        terminate_locust_process_group(task_id, timeout=15.0)

        # Cleanup resources (process group record, port allocation, etc.)
        cleanup_task_resources(task_id)

        # Find and kill any remaining locust processes associated with this task
        # This is a safety net for truly orphaned processes
        remaining_pids = self._find_remaining_locust_processes(task_id)
        for pid in remaining_pids:
            try:
                p = psutil.Process(pid)
                p.kill()
                task_logger.info(f"Force killed remaining orphaned process {pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        task_logger.info(f"Cleanup completed for task {task_id}")

    def _capture_worker_pids(
        self, master_pid: int, task_id: str, task_logger
    ) -> List[int]:
        """Capture worker PIDs for multiprocess Locust."""
        worker_pids: List[int] = []
        start_time = time.time()
        last_count = 0
        stable_count = 0

        while time.time() - start_time < 15:
            try:
                master = psutil.Process(master_pid)
                children = master.children(recursive=True)
                current_pids = []

                for child in children:
                    try:
                        cmdline = child.cmdline()
                        if cmdline and any(
                            "locust" in str(arg).lower() for arg in cmdline
                        ):
                            current_pids.append(child.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                if len(current_pids) == last_count > 0:
                    stable_count += 1
                    if stable_count >= 3:
                        worker_pids = current_pids
                        break
                else:
                    stable_count = 0
                    last_count = len(current_pids)
                    if current_pids:
                        worker_pids = current_pids

                time.sleep(1)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                task_logger.warning(f"Master process {master_pid} inaccessible")
                break
            except Exception as e:
                task_logger.warning(f"Error capturing workers: {e}")
                break

        task_logger.debug(f"Captured {len(worker_pids)} workers: {worker_pids}")
        return worker_pids

    def _find_remaining_locust_processes(self, task_id: str) -> List[int]:
        """Find any remaining locust processes associated with this task."""
        pids = []
        try:
            for proc in psutil.process_iter(["pid", "cmdline"]):
                try:
                    cmdline = proc.info.get("cmdline") or []
                    if isinstance(cmdline, list) and any(
                        "locust" in str(arg).lower() for arg in cmdline
                    ):
                        if task_id in str(cmdline):
                            pids.append(proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.bind(task_id=task_id).warning(f"Error scanning processes: {e}")
        return pids

    def _load_locust_result(self, result_file: str, task_id: str, task_logger) -> dict:
        """Load and return Locust result JSON."""
        try:
            with open(result_file, "r") as f:
                data = json.load(f)
            result_dir = os.path.dirname(result_file)
            if os.path.exists(result_dir):
                shutil.rmtree(result_dir)
            return data
        except json.JSONDecodeError:
            task_logger.error("Failed to decode JSON result file")
            return {}
        except Exception as e:
            task_logger.exception(f"Error loading result: {e}")
            return {}
