"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import subprocess  # nosec B404
import traceback
from typing import List

import pymysql.err  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
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
        """Initialize runner and result service for common API tasks."""
        self.runner = CommonLocustRunner(ST_ENGINE_DIR)
        self.result_service = CommonResultService()

    def update_task_status(
        self,
        session: Session,
        task: CommonTask,
        status: str,
        error_message: str | None = None,
    ):
        """Update task status and optional error message, committing changes."""
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
                task.error_message = truncated_error  # type: ignore[assignment]
            session.commit()
        except (OperationalError, pymysql.err.OperationalError) as e:
            task_logger = logger.bind(task_id=getattr(task, "id", "unknown"))
            task_logger.warning(
                f" Database connection error while updating task status: {e}. "
                "This may be a transient database issue."
            )
            try:
                session.rollback()
            except Exception:
                task_logger.debug(
                    "Failed to rollback session after updating task status.",
                    exc_info=True,
                )
            raise
        except Exception as e:
            task_logger = logger.bind(task_id=getattr(task, "id", "unknown"))
            task_logger.exception(f" Failed to update status: {e}")
            try:
                session.rollback()
            except Exception:
                task_logger.debug(
                    "Failed to rollback session after update task status failure.",
                    exc_info=True,
                )

    def update_task_status_by_id(self, session: Session, task_id: str, status: str):
        """Update task status by task id when a task instance is not provided."""
        task_logger = logger.bind(task_id=task_id)
        try:
            task = session.get(CommonTask, task_id)
            if task:
                self.update_task_status(session, task, status)
            else:
                task_logger.warning(" Could not find task to update status.")
        except (OperationalError, pymysql.err.OperationalError) as e:
            task_logger.warning(
                f" Database connection error while updating task status by ID: {e}. "
                "This may be a transient database issue."
            )
            try:
                session.rollback()
            except Exception:
                task_logger.debug(
                    "Failed to rollback session after updating task status by ID.",
                    exc_info=True,
                )
            raise
        except Exception as e:
            task_logger.exception(f" Failed to update status for task: {e}")
            try:
                session.rollback()
            except Exception:
                task_logger.debug(
                    "Failed to rollback session after update task status by ID failure.",
                    exc_info=True,
                )

    def get_and_lock_task(self, session: Session) -> CommonTask | None:
        """Fetch a pending task and mark it as locked in the same transaction."""
        try:
            query = (
                select(CommonTask)
                .where(CommonTask.status == "created")
                .where(CommonTask.is_deleted == 0)
                .with_for_update()
                .limit(1)
            )
            task = session.execute(query).scalar_one_or_none()
            if task:
                task_logger = logger.bind(task_id=task.id)
                task_logger.info(f" Claimed and locked new task {task.id}.")
                task.status = "locked"  # type: ignore
                session.commit()
                return task
            return None
        except (OperationalError, pymysql.err.OperationalError) as e:
            logger.warning(
                f" Database connection error while trying to get and lock a task: {e}. "
                "This may be a transient database issue. Returning None to allow retry."
            )
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after get-and-lock failure.",
                    exc_info=True,
                )
            return None
        except Exception as e:
            logger.exception(f" Error while trying to get and lock a task: {e}")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after get-and-lock error.",
                    exc_info=True,
                )
            return None

    def get_stopping_task_ids(self, session: Session) -> List[str]:
        """Return all task ids that are currently stopping."""
        try:
            query = select(CommonTask.id).where(
                CommonTask.status == TASK_STATUS_STOPPING
            )
            result = session.execute(query).scalars().all()
            return [str(task_id) for task_id in result]
        except (OperationalError, pymysql.err.OperationalError) as e:
            logger.warning(
                f" Database connection error while fetching stopping tasks: {e}. "
                "This may be a transient database issue. Returning empty list."
            )
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after fetching stopping tasks.",
                    exc_info=True,
                )
            return []
        except Exception as e:
            logger.exception(f" Error fetching stopping tasks: {e}")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after stopping tasks error.",
                    exc_info=True,
                )
            return []

    def reconcile_tasks_on_startup(self, session: Session):
        """Best-effort reconciliation to mark stale common tasks as failed on engine restart."""
        try:
            stale_tasks = (
                session.execute(
                    select(CommonTask)
                    .where(
                        CommonTask.status.in_([TASK_STATUS_RUNNING, TASK_STATUS_LOCKED])
                    )
                    .where(CommonTask.is_deleted == 0)
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
                            f" Task {task.id} was locked during restart. Marking as FAILED (never started)."
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
                        f" Task {task.id} was {task.status} during restart. Checking for orphaned process and failing it."
                    )
                    try:
                        cmd = ["pgrep", "-f", f"locust .*--task-id {task.id}"]
                        subprocess.check_output(
                            cmd, stderr=subprocess.DEVNULL
                        )  # nosec B603

                        task_logger.warning(
                            " Orphaned Locust process detected after engine restart. Terminating and marking task as FAILED."
                        )
                        try:
                            kill_cmd = ["pkill", "-f", f"locust .*--task-id {task.id}"]
                            subprocess.run(kill_cmd, check=True)  # nosec B603
                            task_logger.info(
                                " Successfully terminated orphaned process."
                            )
                        except subprocess.CalledProcessError as e:
                            if e.returncode > 1:
                                task_logger.error(
                                    f" Failed to kill orphaned process: {e}"
                                )
                            else:
                                task_logger.warning(
                                    f" Orphaned process cleanup interrupted or already gone (exit code {e.returncode})."
                                )
                        except Exception as kill_e:
                            task_logger.error(
                                f" Unexpected error while killing orphaned process: {kill_e}"
                            )

                        error_message = "Task process was orphaned by an engine restart and has been terminated."
                        self.update_task_status(
                            session, task, TASK_STATUS_FAILED, error_message
                        )
                    except subprocess.CalledProcessError:
                        # pgrep did not find a process; mark failed with explanation
                        task_logger.warning(
                            " Task was running during restart, but no active process found. Marking as FAILED."
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
        except (OperationalError, pymysql.err.OperationalError) as e:
            logger.warning(
                f" Database connection error during reconciliation: {e}. "
                "This may be a transient database issue. Reconciliation will be retried on next startup."
            )
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session during reconciliation.",
                    exc_info=True,
                )
            raise
        except Exception as e:
            logger.exception(f" reconcile error: {e}")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after reconciliation error.",
                    exc_info=True,
                )

    def start_task(self, task: CommonTask) -> dict:
        """Run the common task and return the runner result payload."""
        task_logger = logger.bind(task_id=task.id)
        try:
            task_logger.info(f" Starting execution for task {task.id}.")
            return self.runner.run_locust_process(task)
        except Exception as e:
            task_logger.exception(f" Unexpected error during execution: {e}")
            return {
                "status": "FAILED",
                "locust_result": {},
                "stderr": str(e),
                "return_code": -1,
            }

    def process_task_pipeline(self, task: CommonTask, session: Session):
        """Process a single task end-to-end and persist its status/results."""
        handler_id = None
        task_logger = logger.bind(task_id=task.id)
        try:
            handler_id = add_task_log_sink(task.id)
            self.update_task_status(session, task, TASK_STATUS_RUNNING)

            run_result = self.start_task(task)
            run_status = run_result.get("status")
            locust_result = run_result.get("locust_result", {})

            try:
                session.refresh(task)
            except (OperationalError, pymysql.err.OperationalError) as e:
                task_logger.warning(
                    f" Database connection error while refreshing task state: {e}. "
                    "Continuing with task processing."
                )
                try:
                    session.rollback()
                except Exception:
                    task_logger.debug(
                        "Failed to rollback session after refresh error.",
                        exc_info=True,
                    )

            if task.status in (TASK_STATUS_STOPPING, TASK_STATUS_STOPPED):
                task_logger.info(
                    f" Task {task.id} was stopped during execution. Marking stopped."
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
        except (OperationalError, pymysql.err.OperationalError) as e:
            task_logger.warning(
                f" Database connection error in pipeline: {e}. "
                "Task processing may be incomplete."
            )
            try:
                session.rollback()
            except Exception:
                task_logger.debug(
                    "Failed to rollback session after pipeline DB error.",
                    exc_info=True,
                )
            # Try to update status, but don't fail if database is still unavailable
            try:
                self.update_task_status(
                    session,
                    task,
                    TASK_STATUS_FAILED,
                    f"Pipeline error: Database connection issue - {str(e)}",
                )
            except Exception as status_update_error:
                logger.warning(
                    f" Could not update task {task.id} status due to database error: {status_update_error}"
                )
        except Exception as e:
            task_logger.error(f" Pipeline error: {e}")
            task_logger.error(f" Full traceback: {traceback.format_exc()}")
            try:
                self.update_task_status(
                    session, task, TASK_STATUS_FAILED, str(e) or "Pipeline error"
                )
            except (OperationalError, pymysql.err.OperationalError) as db_error:
                logger.warning(
                    f" Database connection error while updating failed task status: {db_error}"
                )
            except Exception as status_update_error:
                logger.error(
                    f" Critical: Failed to update status for task {task.id}: {status_update_error}"
                )
        finally:
            if handler_id is not None:
                remove_task_log_sink(handler_id)

    def stop_task(self, task_id: str) -> bool:
        """Stop a running task and clean up process resources."""
        task_logger = logger.bind(task_id=task_id)
        try:
            task_logger.info(f" Received stop request for task {task_id}.")
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
                f" Unexpected error while stopping task {task_id}: {e}"
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

            task_logger.info(f" Sending SIGTERM to process PID {process.pid}.")
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
            task_logger.exception(f" Error terminating process: {e}")
            return False
