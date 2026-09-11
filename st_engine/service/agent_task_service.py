"""Lifecycle service for protocol-aware A2A/MCP tasks."""

from config.base import ST_ENGINE_DIR
from engine.agent_runner import AgentLocustRunner
from engine.process_manager import (
    cleanup_task_resources,
    terminate_locust_process_group,
    terminate_locust_processes_by_task_id,
)

_shared_agent_runner = AgentLocustRunner(ST_ENGINE_DIR)


class AgentTaskService:
    def __init__(self):
        self.runner = _shared_agent_runner

    def start_task(self, task):
        return self.runner.run_locust_process(task)

    def stop_task(self, task_id: str) -> bool:
        self.runner._stopped_task_ids.add(task_id)
        process = self.runner._process_dict.get(task_id)
        terminate_locust_process_group(task_id, timeout=15.0)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except Exception:
                process.kill()
        if not process:
            terminate_locust_processes_by_task_id(task_id)
        self.runner._process_dict.pop(task_id, None)
        cleanup_task_resources(task_id)
        return True
