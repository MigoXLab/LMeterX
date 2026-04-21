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
from engine.http_runner import HttpLocustRunner
from engine.process_manager import (
    cleanup_task_resources,
    get_task_process_status,
    terminate_locust_process_group,
)
from model.http_task import HttpTask
from service.http_result_service import HttpResultService
from utils.logger import (  # type: ignore[attr-defined]
    add_task_log_sink,
    logger,
    remove_task_log_sink,
)
from utils.vm_push import ENGINE_ID


class HttpTaskService:
    """Lifecycle management for HTTP API load test tasks."""

    def __init__(self):
        """Initialize runner and result service for HTTP API tasks."""
        self.runner = HttpLocustRunner(ST_ENGINE_DIR)
        self.result_service = HttpResultService()

    def update_task_status(
        self,
        session: Session,
        task: HttpTask,
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
            task = session.get(HttpTask, task_id)
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

    def get_and_lock_task(self, session: Session) -> HttpTask | None:
        """Fetch a pending task and mark it as locked in the same transaction."""
        try:
            query = (
                select(HttpTask)
                .where(HttpTask.status == "created")
                .where(HttpTask.is_deleted == 0)
                .with_for_update()
                .limit(1)
            )
            task = session.execute(query).scalar_one_or_none()
            if task:
                task_logger = logger.bind(task_id=task.id)
                task_logger.info(f" Claimed and locked new task {task.id}.")
                task.status = "locked"  # type: ignore
                task.engine_id = ENGINE_ID  # type: ignore # Bind engine instance
                session.commit()
                task_logger.info(f"Task {task.id} bound to engine_id={ENGINE_ID}")
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
            query = select(HttpTask.id).where(HttpTask.status == TASK_STATUS_STOPPING)
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
        """Best-effort reconciliation for stale HTTP tasks owned by current engine."""
        try:
            stale_tasks = (
                session.execute(
                    select(HttpTask)
                    .where(
                        HttpTask.status.in_([TASK_STATUS_RUNNING, TASK_STATUS_LOCKED])
                    )
                    .where(HttpTask.is_deleted == 0)
                    .where(HttpTask.engine_id == ENGINE_ID)
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
                    task_engine_id = getattr(task, "engine_id", None)

                    # Defensive guard for future query changes.
                    if not task_engine_id:
                        task_logger.warning(
                            " Task has empty engine_id. Skipping startup reconciliation "
                            "to avoid cross-instance misjudgment."
                        )
                        continue
                    if task_engine_id != ENGINE_ID:
                        task_logger.info(
                            f" Task bound to engine_id={task_engine_id}, current={ENGINE_ID}. "
                            "Skipping reconciliation."
                        )
                        continue

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
                    except FileNotFoundError as e:
                        # Minimal images may not include procps (pgrep/pkill).
                        # Keep current status to avoid false negatives during scaling.
                        task_logger.warning(
                            f" Process inspection command is missing: {e}. "
                            "Skipping startup reconciliation for this task and keeping current status."
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

    def reconcile_dead_engine_tasks(self, session: Session):
        """Mark running/locked HTTP tasks from dead engines as failed.

        An engine is considered dead when its heartbeat timestamp is older
        than the configured stale threshold.  This handles the scenario
        where ``docker compose --scale`` removes replicas while tasks are
        still running inside them.
        """
        from service.heartbeat import get_stale_engine_ids

        try:
            stale_ids = get_stale_engine_ids(session)
            if not stale_ids:
                return

            orphan_tasks = (
                session.execute(
                    select(HttpTask)
                    .where(
                        HttpTask.status.in_([TASK_STATUS_RUNNING, TASK_STATUS_LOCKED])
                    )
                    .where(HttpTask.is_deleted == 0)
                    .where(HttpTask.engine_id.in_(stale_ids))
                )
                .scalars()
                .all()
            )

            if not orphan_tasks:
                return

            logger.info(
                f"Found {len(orphan_tasks)} orphaned HTTP task(s) "
                f"from dead engine(s): {stale_ids}"
            )
            for task in orphan_tasks:
                handler_id = None
                try:
                    handler_id = add_task_log_sink(task.id)
                    task_logger = logger.bind(task_id=task.id)
                    task_logger.warning(
                        f"Engine '{task.engine_id}' has been discontinued. Marking as FAILED."
                    )
                    self.update_task_status(
                        session,
                        task,
                        TASK_STATUS_FAILED,
                        f"Engine instance '{task.engine_id}' is no longer "
                        "alive. Task has been marked as failed due to "
                        "engine shutdown.",
                    )
                finally:
                    if handler_id is not None:
                        remove_task_log_sink(handler_id)
        except Exception as e:
            if isinstance(e, (OperationalError, pymysql.err.OperationalError)):
                logger.warning(f" DB error during dead-engine reconciliation: {e}")
            else:
                logger.debug(f" Dead-engine reconciliation error (non-fatal): {e}")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback after dead-engine reconciliation.",
                    exc_info=True,
                )

    def start_task(self, task: HttpTask) -> dict:
        """Run the HTTP task and return the runner result payload."""
        task_logger = logger.bind(task_id=task.id)
        try:
            task_logger.info(f"Starting execution for task {task.id}.")
            return self.runner.run_locust_process(task)
        except Exception as e:
            task_logger.exception(f" Unexpected error during execution: {e}")
            return {
                "status": "FAILED",
                "locust_result": {},
                "stderr": str(e),
                "return_code": -1,
            }

    def _safe_refresh_task(self, session: Session, task: HttpTask, task_logger):
        """Refresh task state from DB, rolling back on connection errors."""
        try:
            session.refresh(task)
        except (OperationalError, pymysql.err.OperationalError) as e:
            error_msg = str(getattr(e, "orig", e))
            task_logger.warning(
                f" Database connection error while refreshing task state: {error_msg}. "
                "Continuing with task processing."
            )
            try:
                session.rollback()
            except Exception:
                task_logger.debug(
                    "Failed to rollback session after refresh error.",
                    exc_info=True,
                )

    def _resolve_task_status(
        self, session: Session, task: HttpTask, run_result: dict, task_logger
    ):
        """Decide and persist the final task status based on run results."""
        run_status = run_result.get("status")
        locust_result = run_result.get("locust_result", {})

        if task.status in (TASK_STATUS_STOPPING, TASK_STATUS_STOPPED):
            task_logger.info(
                f" Task {task.id} was stopped during execution. Marking stopped."
            )
            self.update_task_status(session, task, TASK_STATUS_STOPPED)
        elif run_status == "STOPPED":
            task_logger.info(
                f" Task {task.id} was stopped (exit signal detected). Marking stopped."
            )
            self.update_task_status(session, task, TASK_STATUS_STOPPED)
        elif run_status == "COMPLETED":
            self._handle_completed(session, task, locust_result)
        elif run_status == "FAILED_REQUESTS":
            if locust_result:
                self.result_service.insert_locust_results(
                    session, locust_result, task.id
                )
            self.update_task_status(session, task, TASK_STATUS_FAILED_REQUESTS)
        else:
            error_message = run_result.get("stderr") or "Runner failed to start."
            self.update_task_status(session, task, TASK_STATUS_FAILED, error_message)

    def _handle_completed(self, session: Session, task: HttpTask, locust_result: dict):
        """Handle a successfully completed run, persisting results or marking failed."""
        self.update_task_status(session, task, TASK_STATUS_COMPLETED)
        if locust_result:
            self.result_service.insert_locust_results(session, locust_result, task.id)
        else:
            self.update_task_status(
                session,
                task,
                TASK_STATUS_FAILED,
                "Runner completed but no result file was generated.",
            )

    def _handle_pipeline_db_error(
        self, session: Session, task: HttpTask, task_logger, error: Exception
    ):
        """Handle database connection errors during pipeline execution."""
        task_logger.warning(
            f" Database connection error in pipeline: {error}. "
            "Task processing may be incomplete."
        )
        try:
            session.rollback()
        except Exception:
            task_logger.debug(
                "Failed to rollback session after pipeline DB error.",
                exc_info=True,
            )
        try:
            self.update_task_status(
                session,
                task,
                TASK_STATUS_FAILED,
                f"Pipeline error: Database connection issue - {str(error)}",
            )
        except Exception as status_update_error:
            logger.warning(
                f" Could not update task {task.id} status due to database error: {status_update_error}"
            )

    def _handle_pipeline_error(
        self, session: Session, task: HttpTask, task_logger, error: Exception
    ):
        """Handle unexpected errors during pipeline execution."""
        task_logger.error(f" Pipeline error: {error}")
        task_logger.error(f" Full traceback: {traceback.format_exc()}")
        try:
            self.update_task_status(
                session, task, TASK_STATUS_FAILED, str(error) or "Pipeline error"
            )
        except (OperationalError, pymysql.err.OperationalError) as db_error:
            logger.warning(
                f" Database connection error while updating failed task status: {db_error}"
            )
        except Exception as status_update_error:
            logger.error(
                f" Critical: Failed to update status for task {task.id}: {status_update_error}"
            )

    def process_task_pipeline(self, task: HttpTask, session: Session):
        """Process a single task end-to-end and persist its status/results."""
        handler_id = None
        task_logger = logger.bind(task_id=task.id)
        try:
            handler_id = add_task_log_sink(task.id)

            # Re-check soft-delete flag to handle the race where a user deletes
            # a "created" task right after the poller locked it but before
            # execution starts.
            self._safe_refresh_task(session, task, task_logger)
            if getattr(task, "is_deleted", 0) == 1:
                task_logger.info(
                    f" Task {task.id} was soft-deleted before execution. Skipping."
                )
                return

            self.update_task_status(session, task, TASK_STATUS_RUNNING)

            run_result = self.start_task(task)

            self._safe_refresh_task(session, task, task_logger)
            self._resolve_task_status(session, task, run_result, task_logger)
        except (OperationalError, pymysql.err.OperationalError) as e:
            self._handle_pipeline_db_error(session, task, task_logger, e)
        except Exception as e:
            self._handle_pipeline_error(session, task, task_logger, e)
        finally:
            if handler_id is not None:
                remove_task_log_sink(handler_id)

    def stop_task(self, task_id: str) -> bool:
        """Stop a running task and clean up process resources."""
        task_logger = logger.bind(task_id=task_id)
        try:
            task_logger.info(f" Received stop request for task {task_id}.")

            # Mark this task as stopped so _finalize_task can detect it
            self.runner._stopped_task_ids.add(task_id)

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
