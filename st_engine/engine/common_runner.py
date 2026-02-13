"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import math
import os
import shutil
import tempfile
from typing import Dict, List

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

    def _get_stepped_env(self, task: CommonTask) -> Dict[str, str]:
        """Build environment variables for stepped load mode."""
        return {
            "LOAD_MODE": "stepped",
            "STEP_START_USERS": str(task.step_start_users or 1),
            "STEP_INCREMENT": str(task.step_increment or 10),
            "STEP_DURATION": str(task.step_duration or 30),
            "STEP_MAX_USERS": str(task.step_max_users or 100),
            "STEP_SUSTAIN_DURATION": str(task.step_sustain_duration or 60),
        }

    def _calc_stepped_total_duration(self, task: CommonTask) -> int:
        """Calculate total duration for stepped load mode."""
        start = task.step_start_users or 1
        increment = task.step_increment or 10
        step_dur = task.step_duration or 30
        max_users = task.step_max_users or 100
        sustain = task.step_sustain_duration or 60

        num_steps = max(1, math.ceil((max_users - start) / max(increment, 1)) + 1)
        return num_steps * step_dur + sustain

    def _build_locust_command(self, task: CommonTask, task_logger) -> List[str]:
        """Build Locust command for common API tests."""
        locust_bin = shutil.which("locust") or "locust"
        load_mode = getattr(task, "load_mode", "fixed") or "fixed"

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

        # Optional args
        for key in ["request_body", "dataset_file"]:
            value = getattr(task, key, None)
            if value:
                cmd.extend([f"--{key}", value])

        return cmd

    def _start_process(self, cmd, task, task_logger):
        """Override to inject stepped load env vars when needed."""
        load_mode = getattr(task, "load_mode", "fixed") or "fixed"
        if load_mode == "stepped":
            # Store env overrides so the parent _start_process picks them up
            if not hasattr(self, "_extra_env"):
                self._extra_env = {}
            self._extra_env = self._get_stepped_env(task)
        else:
            self._extra_env = {}
        return super()._start_process(cmd, task, task_logger)

    def _monitor_and_capture(self, process, task, task_logger):
        """Override to use correct timeout for stepped mode."""
        load_mode = getattr(task, "load_mode", "fixed") or "fixed"
        if load_mode == "stepped":
            # Override duration for timeout calculation so the parent method
            # waits long enough for the full stepped schedule.
            original_duration = task.duration
            task.duration = self._calc_stepped_total_duration(task)
            task_logger.info(
                f"Stepped mode: overriding timeout duration to {task.duration}s "
                f"(original fixed duration: {original_duration}s)"
            )
            try:
                return super()._monitor_and_capture(process, task, task_logger)
            finally:
                task.duration = original_duration
        return super()._monitor_and_capture(process, task, task_logger)

    def _finalize_task(self, process, task, stdout, stderr, task_logger):
        """
        Override to read realtime metrics JSONL before the parent class
        deletes the result directory (via shutil.rmtree in _load_locust_result).
        The data is attached to the result dict so process_task_pipeline
        can persist it to the database.
        """
        metrics_path = os.path.join(
            tempfile.gettempdir(), "locust_result", task.id, "realtime_metrics.jsonl"
        )
        realtime_metrics_data: List[dict] = []
        if os.path.exists(metrics_path):
            try:
                with open(metrics_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            realtime_metrics_data.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                task_logger.info(
                    f"Read {len(realtime_metrics_data)} realtime metric points "
                    f"from JSONL before directory cleanup."
                )
            except Exception as e:
                task_logger.warning(f"Failed to pre-read realtime metrics JSONL: {e}")

        # Call parent which reads result.json and then deletes the directory
        result = super()._finalize_task(process, task, stdout, stderr, task_logger)
        result["realtime_metrics_data"] = realtime_metrics_data
        return result

    def _run_warmup_phase(self, task: CommonTask, task_logger) -> None:
        """Common API tasks do not require LLM warmup; skip to avoid missing fields."""
        task_logger.debug("Skipping warmup phase for common API task.")
