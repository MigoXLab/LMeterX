"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import shutil
import subprocess  # nosec B404
import tempfile
import threading
import time
from queue import Queue
from typing import List, Tuple

import psutil

from config.base import LOCUST_STOP_TIMEOUT, LOCUST_WAIT_TIMEOUT_BUFFER
from config.multiprocess import (
    get_cpu_count,
    get_process_count,
    should_enable_multiprocess,
)
from engine.process_manager import (
    allocate_master_port,
    cleanup_task_resources,
    register_locust_process_group,
    terminate_locust_process_group,
)
from model.task import Task
from utils.common import mask_sensitive_command
from utils.logger import logger


class LocustRunner:
    """
    Enhanced Locust runner with robust multiprocess management.
    """

    _process_dict: dict[str, subprocess.Popen] = {}

    def __init__(self, base_dir: str):
        """Create a runner rooted at the given repository directory."""
        self.base_dir = base_dir
        self._locustfile_path = os.path.join(self.base_dir, "engine", "locustfile.py")

    def run_locust_process(self, task: Task) -> dict:
        """
        Run Locust test as a separate process with full lifecycle management.
        """
        task_logger = logger.bind(task_id=task.id)
        task_logger.info(f"Starting Locust task {task.id}")

        try:
            # Step 1: Prepare environment
            self._prepare_task(task, task_logger)

            # Step 2: Build and start process
            cmd = self._build_locust_command(task, task_logger)
            process = self._start_process(cmd, task, task_logger)

            # Step 3: Monitor and capture output
            stdout, stderr = self._monitor_and_capture(process, task, task_logger)

            # Step 4: Finalize and load results
            result = self._finalize_task(process, task, stdout, stderr, task_logger)
            return result

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
            # Ensure cleanup is attempted even if an exception occurs
            # This is a safety net. `_finalize_task` should handle normal cleanup.
            if task.id in self._process_dict:
                task_logger.warning(
                    f"Task {task.id} exited abnormally. Triggering emergency cleanup."
                )
                # We create a dummy process object just to satisfy the _cleanup_task signature.
                # The actual PID might be invalid, but _cleanup_task will handle it gracefully.
                dummy_true = shutil.which("true") or "/bin/true"
                dummy_process = subprocess.Popen(
                    [dummy_true],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )  # nosec B607,B603 - absolute path; no untrusted input
                dummy_process.pid = -1  # Mark it as invalid
                self._cleanup_task(task, dummy_process, task_logger)

    def _prepare_task(self, task: Task, task_logger) -> None:
        """Prepare task environment: validate config and files."""
        # NOTE: Avoid global process cleanup here; it can terminate unrelated
        # Locust runs (e.g., model vs common API tasks) that are running
        # concurrently. Stale processes are reconciled in pollers/startup
        # routines instead of per-task execution.
        if not os.path.exists(self._locustfile_path):
            raise FileNotFoundError(f"Locustfile not found at {self._locustfile_path}")

    def _build_locust_command(self, task: Task, task_logger) -> List[str]:
        """Build Locust command based on task config."""
        locust_bin = shutil.which("locust") or "locust"
        cmd = [
            locust_bin,
            "-f",
            self._locustfile_path,
            "--host",
            task.target_host,
            "--users",
            str(task.concurrent_users),
            "--spawn-rate",
            str(task.spawn_rate),
            "--run-time",
            f"{task.duration}s",
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

        cpu_count = get_cpu_count()
        concurrent_users = int(task.concurrent_users)
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
        masked_cmd = mask_sensitive_command(cmd)
        task_logger.info(f"Executing: {' '.join(masked_cmd)}")

        env = os.environ.copy()
        env["TASK_ID"] = str(task.id)
        env["LOCUST_CONCURRENT_USERS"] = str(task.concurrent_users)
        # Ensure Locust subprocess can import project modules
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{self.base_dir}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else self.base_dir
        )
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
        if should_enable_multiprocess(int(task.concurrent_users)):
            try:
                master_port = allocate_master_port(task.id)
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
        stdout_queue: Queue[str] = Queue()
        stderr_queue: Queue[str] = Queue()

        def read_stream(pipe, q, name):
            try:
                for line in iter(pipe.readline, ""):
                    if line.strip():
                        q.put(line)
                        task_logger.opt(raw=True).info(line)
                pipe.close()
            except Exception as e:
                task_logger.error(f"Error reading {name}: {e}")

        stdout_thread = threading.Thread(
            target=read_stream, args=(process.stdout, stdout_queue, "stdout")
        )
        stderr_thread = threading.Thread(
            target=read_stream, args=(process.stderr, stderr_queue, "stderr")
        )

        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()

        total_timeout = task.duration + LOCUST_STOP_TIMEOUT + LOCUST_WAIT_TIMEOUT_BUFFER

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

        # Drain queues
        stdout = "".join(list(stdout_queue.queue))
        stderr = "".join(list(stderr_queue.queue))

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
        result_file = os.path.join(
            tempfile.gettempdir(), "locust_result", task.id, "result.json"
        )

        if not os.path.exists(result_file):
            error_msg = f"Result file not found: {result_file}"
            task_logger.error(error_msg)
            locust_result = {}
            status = "FAILED"
        else:
            locust_result = self._load_locust_result(result_file, task.id, task_logger)
            status = "COMPLETED" if process.returncode == 0 else "FAILED_REQUESTS"
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
        task_id = task.id
        task_logger.info(f"Starting cleanup for task {task_id}")

        # Remove from process dict (this is safe and should be done first)
        self._process_dict.pop(task_id, None)

        # Terminate multiprocess group if applicable
        if should_enable_multiprocess(int(task.concurrent_users)):
            terminate_locust_process_group(task_id, timeout=15.0)

        # Cleanup resources (sockets, temp files, etc.)
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

    def _cleanup_task_old(
        self, task: Task, process: subprocess.Popen, task_logger
    ) -> None:
        """Perform comprehensive cleanup after task completion."""
        task_id = task.id
        task_logger.info(f"Starting cleanup for task {task_id}")

        # Remove from process dict
        self._process_dict.pop(task_id, None)

        # Terminate multiprocess group
        if should_enable_multiprocess(int(task.concurrent_users)):
            terminate_locust_process_group(task_id, timeout=15.0)

        # Ensure main process is dead
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        # Cleanup resources
        cleanup_task_resources(task_id)

        # Kill any remaining locust processes tied to this task
        remaining_pids = self._find_remaining_locust_processes(task_id)
        for pid in remaining_pids:
            try:
                p = psutil.Process(pid)
                p.kill()
                task_logger.info(f"Force killed remaining process {pid}")
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
