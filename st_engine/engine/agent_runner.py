"""Locust subprocess runner for A2A and MCP load-test jobs."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any, List

from config.base import LOCUST_STOP_TIMEOUT
from engine.llm_runner import LlmLocustRunner


def protocol_execution_failure_reason(
    protocol: str, locust_result: dict[str, Any] | None
) -> str | None:
    """Return why a nominally successful protocol run must be failed.

    Agent protocol setup happens in ``HttpUser.on_start``.  Locust considers a
    user stopped from there a clean process exit, even when MCP/A2A setup has
    already recorded a protocol failure.  A completed run also has to execute
    at least one configured top-level request to be meaningful.
    """
    if protocol not in {"a2a", "mcp"}:
        return None

    metrics = (locust_result or {}).get("custom_metrics")
    if not isinstance(metrics, dict):
        return None

    try:
        failed_requests = int(metrics.get("failed_requests", 0) or 0)
    except (TypeError, ValueError):
        failed_requests = 0
    if failed_requests > 0:
        return f"Protocol reported {failed_requests} failed request(s)"

    try:
        top_level_requests = int(metrics.get("top_level_requests", 0) or 0)
    except (TypeError, ValueError):
        top_level_requests = 0
    if top_level_requests == 0:
        return "Protocol run completed without executing a top-level request"
    return None


class AgentLocustRunner(LlmLocustRunner):
    def __init__(self, base_dir: str):
        super().__init__(base_dir)
        self._locustfile_path = os.path.join(base_dir, "engine", "agent_locustfile.py")

    def _config_path(self, task_id: str) -> str:
        return os.path.join(
            tempfile.gettempdir(), "lmeterx_agent_configs", f"{task_id}.json"
        )

    def _delete_config(self, task_id: str) -> None:
        try:
            os.unlink(self._config_path(task_id))
        except FileNotFoundError:
            pass

    def _build_locust_command(self, task, task_logger) -> List[str]:
        config_path = self._config_path(task.id)
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, mode=0o700, exist_ok=True)
        os.chmod(config_dir, 0o700)
        try:
            protocol_config = json.loads(task.protocol_config or "{}")
            headers = json.loads(task.headers or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid agent task JSON configuration: {exc}") from exc
        runtime_config = {
            **protocol_config,
            "protocol": task.protocol,
            "protocol_version": task.protocol_version,
            "api_path": task.api_path,
            "headers": headers,
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(config_path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(runtime_config, handle, ensure_ascii=False)

        locust_bin = shutil.which("locust") or "locust"
        return [
            locust_bin,
            "-f",
            self._locustfile_path,
            "--host",
            task.target_host,
            "--headless",
            "--only-summary",
            "--stop-timeout",
            f"{LOCUST_STOP_TIMEOUT}s",
            "--users",
            str(task.concurrent_users),
            "--spawn-rate",
            str(task.spawn_rate),
            "--run-time",
            f"{task.duration}s",
            "--task-id",
            task.id,
            "--config-file",
            config_path,
        ]

    def _run_warmup_phase(self, task, task_logger) -> None:
        task_logger.debug("Protocol tasks do not run an LLM warmup phase.")

    def _finalize_task(self, process, task, stdout, stderr, task_logger) -> dict:
        result = super()._finalize_task(process, task, stdout, stderr, task_logger)
        protocol = str(getattr(task, "protocol", ""))
        reason = protocol_execution_failure_reason(
            protocol, result.get("locust_result")
        )

        if result.get("status") == "COMPLETED":
            if reason:
                task_logger.error(
                    "Protocol task produced a clean Locust exit without a valid "
                    f"workload result: {reason}. Marking it FAILED_REQUESTS."
                )
                result["status"] = "FAILED_REQUESTS"
                result["error_message"] = reason
            return result

        # Locust exit code 1 already maps to FAILED_REQUESTS without a message;
        # surface the protocol failure count (or exit code) for operators/tests.
        if result.get("status") == "FAILED_REQUESTS" and not result.get(
            "error_message"
        ):
            result["error_message"] = reason or (
                "Locust completed with failures "
                f"(exit code {result.get('return_code')})"
            )
        return result

    def run_locust_process(self, task) -> dict:
        try:
            return super().run_locust_process(task)
        finally:
            self._delete_config(task.id)

    def _cleanup_task(self, task, process, task_logger) -> None:
        try:
            super()._cleanup_task(task, process, task_logger)
        finally:
            self._delete_config(task.id)
