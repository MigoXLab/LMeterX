"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import shutil
from typing import List

from engine.runner import LocustRunner
from model.common_task import CommonTask
from utils.logger import logger


class CommonLocustRunner(LocustRunner):
    """Locust runner dedicated to common HTTP API load tests."""

    def __init__(self, base_dir: str):
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
            "--request_body",
            task.request_body or "",
            "--task-id",
            task.id,
        ]
        if getattr(task, "dataset_file", None):
            cmd.extend(["--dataset_file", task.dataset_file])
        return cmd
