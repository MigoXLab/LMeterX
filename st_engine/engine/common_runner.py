"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import shutil
from typing import List

from engine.runner import LocustRunner
from model.common_task import CommonTask


class CommonLocustRunner(LocustRunner):
    """Locust runner dedicated to common HTTP API load tests."""

    def __init__(self, base_dir: str):
        """Create a runner rooted at the given repository directory."""
        super().__init__(base_dir)
        self._locustfile_path = os.path.join(
            self.base_dir, "engine", "common_locustfile.py"
        )

    def _build_locust_command(self, task: CommonTask, task_logger) -> List[str]:
        """Build Locust command for common API tests."""
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

        # Optional args
        for key in ["request_body", "dataset_file"]:
            value = getattr(task, key, None)
            if value:
                cmd.extend([f"--{key}", value])

        return cmd

    def _run_warmup_phase(self, task: CommonTask, task_logger) -> None:
        """Common API tasks do not require LLM warmup; skip to avoid missing fields."""
        task_logger.debug("Skipping warmup phase for common API task.")
