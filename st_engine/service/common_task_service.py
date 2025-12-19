"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import subprocess  # nosec B404
import traceback
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.base import ST_ENGINE_DIR
from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_FAILED_REQUESTS,
    TASK_STATUS_LOCKED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
    TASK_STATUS_STOPPING,
)
from engine.common_runner import CommonLocustRunner
from engine.process_manager import (
    cleanup_task_resources,
    get_task_process_status,
    terminate_locust_process_group,
)
from model.common_task import CommonTask
from service.common_result_service import CommonResultService
from utils.logger import (  # type: ignore[attr-defined]
    add_task_log_sink,
    logger,
    remove_task_log_sink,
)


class CommonTaskService:
    """Lifecycle management for common API load test tasks."""

    def __init__(self):
        self.runner = CommonLocustRunner(ST_ENGINE_DIR)
        self.result_service = CommonResultService()

    def update_task_status(
        self,
        session: Session,
        task: CommonTask,
        status: str,
        error_message: str | None = None,
    ):
        try:
            task.status = status  # type: ignore
            if error_message:
                max_length = 65000
                truncated_error = (
                    error_message[: max_length - 100]
                    + f"\n... (truncated, original length: {len(error_message)})"
                    if len(error_message) > max_length
                    else error_message
                )
                setattr(task, "error_message", truncated_error)
            session.commit()
        except Exception as e:
            task_logger = logger.bind(task_id=getattr(task, "id", "unknown"))
            task_logger.exception(f"[COMMON] Failed to update status: {e}")
            session.rollback()

    def update_task_status_by_id(self, session: Session, task_id: str, status: str):
        task_logger = logger.bind(task_id=task_id)
        try:
            task = session.get(CommonTask, task_id)
            if task:
                self.update_task_status(session, task, status)
            else:
                task_logger.warning("[COMMON] Could not find task to update status.")
        except Exception as e:
            task_logger.exception(f"[COMMON] Failed to update status for task: {e}")
            session.rollback()

    def get_and_lock_task(self, session: Session) -> CommonTask | None:
        try:
            query = (
                select(CommonTask)
                .where(CommonTask.status == "created")
                .with_for_update()
                .limit(1)
            )
            task = session.execute(query).scalar_one_or_none()
            if task:
                task_logger = logger.bind(task_id=task.id)
                task_logger.info(f"[COMMON] Claimed and locked new task {task.id}.")
                task.status = "locked"  # type: ignore
                session.commit()
                return task
            return None
        except Exception as e:
            logger.exception(f"[COMMON] Error while trying to get and lock a task: {e}")
            session.rollback()
            return None

    def get_stopping_task_ids(self, session: Session) -> List[str]:
        try:
            query = select(CommonTask.id).where(
                CommonTask.status == TASK_STATUS_STOPPING
            )
            result = session.execute(query).scalars().all()
            return [str(task_id) for task_id in result]
        except Exception as e:
            logger.exception(f"[COMMON] Error fetching stopping tasks: {e}")
            session.rollback()
            return []

    def reconcile_tasks_on_startup(self, session: Session):
        """Best-effort reconciliation to mark stale common tasks as failed on engine restart."""
        try:
            stale_tasks = (
                session.execute(
                    select(CommonTask).where(
                        CommonTask.status.in_([TASK_STATUS_RUNNING, TASK_STATUS_LOCKED])
                    )
                )
                .scalars()
                .all()
            )
            for task in stale_tasks:
                handler_id = None
                task_logger = logger.bind(task_id=task.id)
                try:
                    # Ensure task log sink exists so reconciliation warnings are captured per task
                    handler_id = add_task_log_sink(task.id)

                    if task.status == TASK_STATUS_LOCKED:
                        task_logger.warning(
                            f"[COMMON] Task {task.id} was locked during restart. Marking as FAILED (never started)."
                        )
                        self.update_task_status(
                            session,
                            task,
                            TASK_STATUS_FAILED,
                            "Task was aborted before execution due to an engine restart.",
                        )
                        continue

                    # For running tasks, try to detect and clean orphaned locust processes.
                    task_logger.warning(
                        f"[COMMON] Task {task.id} was {task.status} during restart. Checking for orphaned process and failing it."
                    )
                    try:
                        cmd = ["pgrep", "-f", f"locust .*--task-id {task.id}"]
                        subprocess.check_output(
                            cmd, stderr=subprocess.DEVNULL
                        )  # nosec B603

                        task_logger.warning(
                            "[COMMON] Orphaned Locust process detected after engine restart. Terminating and marking task as FAILED."
                        )
                        try:
                            kill_cmd = ["pkill", "-f", f"locust .*--task-id {task.id}"]
                            subprocess.run(kill_cmd, check=True)  # nosec B603
                            task_logger.info(
                                "[COMMON] Successfully terminated orphaned process."
                            )
                        except subprocess.CalledProcessError as e:
                            if e.returncode > 1:
                                task_logger.error(
                                    f"[COMMON] Failed to kill orphaned process: {e}"
                                )
                            else:
                                task_logger.warning(
                                    f"[COMMON] Orphaned process cleanup interrupted or already gone (exit code {e.returncode})."
                                )
                        except Exception as kill_e:
                            task_logger.error(
                                f"[COMMON] Unexpected error while killing orphaned process: {kill_e}"
                            )

                        error_message = "Task process was orphaned by an engine restart and has been terminated."
                        self.update_task_status(
                            session, task, TASK_STATUS_FAILED, error_message
                        )
                    except subprocess.CalledProcessError:
                        # pgrep did not find a process; mark failed with explanation
                        task_logger.warning(
                            "[COMMON] Task was running during restart, but no active process found. Marking as FAILED."
                        )
                        error_message = (
                            "Task process was not found after an engine restart."
                        )
                        self.update_task_status(
                            session, task, TASK_STATUS_FAILED, error_message
                        )
                finally:
                    if handler_id is not None:
                        remove_task_log_sink(handler_id)
        except Exception as e:
            logger.exception(f"[COMMON] reconcile error: {e}")
            session.rollback()

    def start_task(self, task: CommonTask) -> dict:
        task_logger = logger.bind(task_id=task.id)
        try:
            task_logger.info(f"[COMMON] Starting execution for task {task.id}.")
            return self.runner.run_locust_process(task)
        except Exception as e:
            task_logger.exception(f"[COMMON] Unexpected error during execution: {e}")
            return {
                "status": "FAILED",
                "locust_result": {},
                "stderr": str(e),
                "return_code": -1,
            }

    def process_task_pipeline(self, task: CommonTask, session: Session):
        handler_id = None
        task_logger = logger.bind(task_id=task.id)
        try:
            handler_id = add_task_log_sink(task.id)
            self.update_task_status(session, task, TASK_STATUS_RUNNING)

            run_result = self.start_task(task)
            run_status = run_result.get("status")
            locust_result = run_result.get("locust_result", {})

            session.refresh(task)

            if task.status in (TASK_STATUS_STOPPING, TASK_STATUS_STOPPED):
                task_logger.info(
                    f"[COMMON] Task {task.id} was stopped during execution. Marking stopped."
                )
                self.update_task_status(session, task, TASK_STATUS_STOPPED)
            elif run_status == "COMPLETED":
                self.update_task_status(session, task, TASK_STATUS_COMPLETED)
                if locust_result:
                    self.result_service.insert_locust_results(
                        session, locust_result, task.id
                    )
                else:
                    self.update_task_status(
                        session,
                        task,
                        TASK_STATUS_FAILED,
                        "Runner completed but no result file was generated.",
                    )
            elif run_status == "FAILED_REQUESTS":
                if locust_result:
                    self.result_service.insert_locust_results(
                        session, locust_result, task.id
                    )
                self.update_task_status(session, task, TASK_STATUS_FAILED_REQUESTS)
            else:
                error_message = run_result.get("stderr") or "Runner failed to start."
                self.update_task_status(
                    session, task, TASK_STATUS_FAILED, error_message
                )
        except Exception as e:
            task_logger.error(f"[COMMON] Pipeline error: {e}")
            task_logger.error(f"[COMMON] Full traceback: {traceback.format_exc()}")
            try:
                self.update_task_status(
                    session, task, TASK_STATUS_FAILED, str(e) or "Pipeline error"
                )
            except Exception as status_update_error:
                logger.error(
                    f"[COMMON] Critical: Failed to update status for task {task.id}: {status_update_error}"
                )
        finally:
            if handler_id is not None:
                remove_task_log_sink(handler_id)

    def stop_task(self, task_id: str) -> bool:
        task_logger = logger.bind(task_id=task_id)
        try:
            task_logger.info(f"[COMMON] Received stop request for task {task_id}.")
            process = self.runner._process_dict.get(task_id)
            if not process:
                task_logger.warning(
                    "Process not found in runner's dictionary. It may have finished or not started."
                )
                return True

            if process.poll() is not None:
                self.runner._process_dict.pop(task_id, None)
                cleanup_task_resources(task_id)
                return True

            group_info = get_task_process_status(task_id)
            group_terminated = False
            if group_info:
                group_terminated = terminate_locust_process_group(task_id, timeout=15.0)
                if not group_terminated:
                    task_logger.warning(
                        "Multiprocess group termination reported failure."
                    )

            if process.poll() is None:
                if not self._terminate_local_process(process, task_id, task_logger):
                    return False

            self.runner._process_dict.pop(task_id, None)
            cleanup_task_resources(task_id)
            return True
        except Exception as e:
            task_logger.exception(
                f"[COMMON] Unexpected error while stopping task {task_id}: {e}"
            )
            return False

    def _terminate_local_process(
        self,
        process: subprocess.Popen,
        task_id: str,
        task_logger,
        term_timeout: float = 10.0,
    ) -> bool:
        try:
            if process.poll() is not None:
                return True

            task_logger.info(f"[COMMON] Sending SIGTERM to process PID {process.pid}.")
            process.terminate()
            try:
                process.wait(timeout=term_timeout)
            except subprocess.TimeoutExpired:
                task_logger.warning("Process did not terminate gracefully. Killing...")
                process.kill()
                process.wait()

            if process.poll() is None:
                task_logger.error("Process is still running after SIGKILL.")
                return False

            task_logger.info("Process terminated successfully.")
            return True
        except Exception as e:
            task_logger.exception(f"[COMMON] Error terminating process: {e}")
            return False
