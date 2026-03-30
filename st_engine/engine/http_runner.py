"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import shutil
from typing import List

from config.multiprocess import (
    get_cpu_count,
    get_process_count,
    should_enable_multiprocess,
)
from engine.llm_runner import LlmLocustRunner
from model.http_task import HttpTask


class HttpLocustRunner(LlmLocustRunner):
    """Locust runner dedicated to common HTTP API load tests."""

    def __init__(self, base_dir: str):
        """Create a runner rooted at the given repository directory."""
        super().__init__(base_dir)
        self._locustfile_path = os.path.join(
            self.base_dir, "engine", "http_locustfile.py"
        )

    def _build_locust_command(self, task: HttpTask, task_logger) -> List[str]:
        """Build Locust command for common API tests."""
        locust_bin = shutil.which("locust") or "locust"
        load_mode = self._get_load_mode(task)

        cmd = [
            locust_bin,
            "-f",
            self._locustfile_path,
            "--host",
            task.target_host,
            "--headless",
            "--only-summary",
            "--api_path",
            task.api_path,
            "--method",
            task.method,
            "--headers",
            task.headers or "{}",
            "--cookies",
            task.cookies or "{}",
            "--task-id",
            task.id,
        ]

        if load_mode == "stepped":
            # In stepped mode, LoadTestShape controls users/run-time/spawn-rate.
            # Do NOT pass --users / --run-time / --spawn-rate; Locust ignores them
            # when a shape class is present, but omitting avoids confusion.
            task_logger.info(
                f"Stepped load mode: start={task.step_start_users}, "
                f"increment={task.step_increment}, step_duration={task.step_duration}s, "
                f"max={task.step_max_users}, sustain={task.step_sustain_duration}s"
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
                ]
            )

        # Multi-process support: automatically enable when concurrency is high
        cpu_count = get_cpu_count()
        concurrent_users = int(task.concurrent_users)
        process_count = get_process_count(concurrent_users, cpu_count)

        if (
            should_enable_multiprocess(concurrent_users, cpu_count)
            and process_count > 1
        ):
            cmd.extend(["--processes", str(process_count)])
            task_logger.info(
                f"Multi-process enabled: {process_count} workers "
                f"(CPU={cpu_count}, users={concurrent_users})"
            )

        # Optional args
        for key in ["request_body", "dataset_file", "success_assert"]:
            value = getattr(task, key, None)
            if value:
                cmd.extend([f"--{key}", value])

        return cmd

    def _run_warmup_phase(self, task: HttpTask, task_logger) -> None:
        """HTTP API tasks do not require LLM warmup; skip to avoid missing fields."""
        task_logger.debug("Skipping warmup phase for HTTP API task.")
