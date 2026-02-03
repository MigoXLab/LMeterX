"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import subprocess  # nosec B404

import pymysql.err  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from config.base import ST_ENGINE_DIR, UPLOAD_FOLDER
from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_FAILED_REQUESTS,
    TASK_STATUS_LOCKED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
    TASK_STATUS_STOPPING,
)
from engine.process_manager import (
    cleanup_task_resources,
    get_task_process_status,
    terminate_locust_process_group,
)
from engine.runner import LocustRunner
from model.task import Task
from service.result_service import ResultService
from utils.logger import add_task_log_sink, logger, remove_task_log_sink


class TaskService:
    """
    Provides services for managing the entire lifecycle of a performance test task.
    This includes creating, locking, executing, and stopping tasks.
    """

    def __init__(self):
        """Initializes the TaskService with a LocustRunner instance."""
        self.runner = LocustRunner(ST_ENGINE_DIR)
        self.result_service = ResultService()

    def _cleanup_task_files(self, task: Task):
        """
        Clean up uploaded files associated with a completed or failed task.

        Args:
            task (Task): The task object containing file paths to clean up.
        """
        task_logger = logger.bind(task_id=task.id)
        files_to_remove = []

        # Collect all file paths associated with this task
        if hasattr(task, "test_data") and task.test_data:
            if task.test_data not in ["default", ""]:
                # Only add actual file paths, not default dataset or empty strings
                if not task.test_data.strip().startswith("{"):  # Not JSONL content
                    files_to_remove.append(task.test_data)

        if hasattr(task, "cert_file") and task.cert_file:
            files_to_remove.append(task.cert_file)

        if hasattr(task, "key_file") and task.key_file:
            files_to_remove.append(task.key_file)

        # Remove each file if it exists
        for file_path in files_to_remove:
            if file_path and file_path.strip():
                try:
                    # Ensure we're working with absolute paths
                    if not os.path.isabs(file_path):
                        file_path = os.path.join(UPLOAD_FOLDER, file_path)  # type: ignore

                    if os.path.exists(file_path):
                        os.remove(file_path)
                        task_logger.info(f"Successfully removed file: {file_path}")
                    else:
                        task_logger.debug(f"File not found for cleanup: {file_path}")

                except Exception as e:
                    task_logger.warning(f"Failed to remove file {file_path}: {e}")

    def update_task_status(
        self,
        session: Session,
        task: Task,
        status: str,
        error_message: str | None = None,
    ):
        """
        Updates the status of a given task.

        Args:
            session (Session): The SQLAlchemy database session.
            task (Task): The task object to update.
            status (str): The new status to set.
            error_message (str, optional): An error message to record if the task failed.
        """
        try:
            task.status = status  # type: ignore
            if error_message:
                # Limit error message length to avoid database field overflow
                # MySQL TEXT field can store up to 65,535 characters
                max_length = 65000  # Leave some buffer
                if len(error_message) > max_length:
                    truncated_message = (
                        error_message[: max_length - 100]
                        + f"\n... (truncated, original length: {len(error_message)})"
                    )
                    task.error_message = truncated_message  # type: ignore
                else:
                    task.error_message = error_message  # type: ignore
            session.commit()

            # Clean up uploaded files for terminal states
            if status in [
                TASK_STATUS_COMPLETED,
                TASK_STATUS_STOPPED,
                TASK_STATUS_FAILED,
                TASK_STATUS_FAILED_REQUESTS,
            ]:
                try:
                    self._cleanup_task_files(task)
                except Exception as cleanup_error:
                    if hasattr(task, "id") and task.id:
                        task_logger = logger.bind(task_id=task.id)
                        task_logger.warning(f"File cleanup failed: {cleanup_error}")
                    else:
                        logger.warning(
                            f"File cleanup failed for a task: {cleanup_error}"
                        )

        except (OperationalError, pymysql.err.OperationalError) as e:
            if hasattr(task, "id") and task.id:
                task_logger = logger.bind(task_id=task.id)
                task_logger.warning(
                    f"Database connection error while updating task status: {e}. "
                    "This may be a transient database issue."
                )
            else:
                logger.warning(
                    f"Database connection error while updating task status: {e}. "
                    "This may be a transient database issue."
                )
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after status update DB error.",
                    exc_info=True,
                )
            raise
        except Exception as e:
            if hasattr(task, "id") and task.id:
                task_logger = logger.bind(task_id=task.id)
                task_logger.exception(f"Failed to update status: {e}")
            else:
                logger.exception(f"Failed to update status for a task: {e}")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after status update error.",
                    exc_info=True,
                )

    def update_task_status_by_id(self, session: Session, task_id: str, status: str):
        """
        Updates the status of a task identified by its ID.

        Args:
            session (Session): The SQLAlchemy database session.
            task_id (str): The ID of the task to update.
            status (str): The new status to set.
        """
        task_logger = logger.bind(task_id=task_id)
        try:
            task = session.get(Task, task_id)
            if task:
                self.update_task_status(session, task, status)
            else:
                task_logger.warning(f"Could not find task to update status.")
        except (OperationalError, pymysql.err.OperationalError) as e:
            task_logger.warning(
                f"Database connection error while updating task status by ID: {e}. "
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
            task_logger.exception(f"Failed to update status for task: {e}")
            try:
                session.rollback()
            except Exception:
                task_logger.debug(
                    "Failed to rollback session after update task status failure.",
                    exc_info=True,
                )

    def get_and_lock_task(self, session: Session) -> Task | None:
        """
        Atomically retrieves and locks the next available task with 'created' status.

        This method uses a 'SELECT ... FOR UPDATE' query to ensure that only one
        engine instance can claim a task.

        Args:
            session (Session): The SQLAlchemy database session.

        Returns:
            Task | None: The locked task object, or None if no tasks are available.
        """
        try:
            # The transaction is handled by the get_db_session context manager
            query = (
                select(Task).where(Task.status == "created").with_for_update().limit(1)
            )
            task = session.execute(query).scalar_one_or_none()
            if task:
                task_logger = logger.bind(task_id=task.id)
                task_logger.info(f"Claimed and locked new task {task.id}.")
                task.status = "locked"  # type: ignore # Update status immediately
                session.commit()
                return task
            return None
        except (OperationalError, pymysql.err.OperationalError) as e:
            logger.warning(
                f"Database connection error while trying to get and lock a task: {e}. "
                "This may be a transient database issue. Returning None to allow retry."
            )
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after get-and-lock DB error.",
                    exc_info=True,
                )
            return None
        except Exception as e:
            logger.exception(f"Error while trying to get and lock a task: {e}")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after get-and-lock error.",
                    exc_info=True,
                )
            return None

    def reconcile_tasks_on_startup(self, session: Session):
        """
        Reconciles tasks on engine startup by checking for tasks in 'running' or
        'locked' states and cleaning up any that no longer have an active process.

        This is crucial for handling state inconsistencies that arise when the
        engine is restarted while tasks are being processed.
        Args:
            session (Session): The SQLAlchemy database session.
        """
        logger.info("Reconciling tasks on startup...")
        try:
            # Find all tasks that were in a transient state (locked or running)
            # during the last shutdown.
            stale_tasks = (
                session.execute(
                    select(Task).where(
                        Task.status.in_([TASK_STATUS_RUNNING, TASK_STATUS_LOCKED])
                    )
                )
                .scalars()
                .all()
            )

            if not stale_tasks:
                logger.info("No running or locked tasks found to reconcile.")
                return

            logger.info(f"Found {len(stale_tasks)} potentially stale tasks to check")
            for task in stale_tasks:
                handler_id = None
                try:
                    # Temporarily add a log sink for this specific task to capture reconciliation logs.
                    handler_id = add_task_log_sink(task.id)
                    task_logger = logger.bind(task_id=task.id)

                    if task.status == TASK_STATUS_LOCKED:
                        # The task was locked, but the engine restarted before the process
                        # was created. Mark it as failed directly.
                        task_logger.warning(
                            f"Task {task.id} was in '{task.status}' state during restart. "
                            f"Task {task.id}, Marking as FAILED as it never started."
                        )
                        error_message = "Task was aborted before execution due to an engine restart."
                        self.update_task_status(
                            session, task, TASK_STATUS_FAILED, error_message
                        )
                        continue

                    # For tasks in 'running' state, check for an orphaned process.
                    try:
                        # Use pgrep to check if a locust process with a specific task-id exists.
                        cmd = ["pgrep", "-f", f"locust .*--task-id {task.id}"]
                        subprocess.check_output(
                            cmd, stderr=subprocess.DEVNULL
                        )  # nosec B603

                        # If pgrep succeeds, the process exists and is now an orphan.
                        task_logger.warning(
                            f"Something went wrong with engine service."
                            f"Terminating it and marking task as FAILED."
                        )
                        try:
                            kill_cmd = ["pkill", "-f", f"locust .*--task-id {task.id}"]
                            subprocess.run(kill_cmd, check=True)  # nosec B603
                            task_logger.info(
                                f"Successfully terminated orphaned process."
                            )
                        except subprocess.CalledProcessError as e:
                            if e.returncode > 1:
                                task_logger.error(
                                    f"Failed to kill orphaned process: {e}"
                                )
                            else:
                                task_logger.warning(
                                    f"Orphaned process cleanup for task {task.id} was interrupted or the process was already gone (exit code {e.returncode}). This is likely safe to ignore."
                                )
                        except Exception as kill_e:
                            task_logger.error(
                                f"An unexpected error occurred while trying to kill orphaned process: {kill_e}"
                            )

                        error_message = "Task process was orphaned by an engine restart and has been terminated."
                        self.update_task_status(
                            session, task, TASK_STATUS_FAILED, error_message
                        )

                    except subprocess.CalledProcessError:
                        # pgrep returns a non-zero exit code, meaning no process was found.
                        task_logger.warning(
                            f"Task {task.id} was in '{task.status}' state, but no active process found. "
                            f"Marking as FAILED. This likely occurred during an engine restart."
                        )
                        error_message = (
                            "Task process was not found after an engine restart."
                        )
                        self.update_task_status(
                            session, task, TASK_STATUS_FAILED, error_message
                        )
                finally:
                    # Clean up the temporary log sink.
                    if handler_id is not None:
                        remove_task_log_sink(handler_id)

        except (OperationalError, pymysql.err.OperationalError) as e:
            logger.warning(
                f"Database connection error during reconciliation: {e}. "
                "This may be a transient database issue. Reconciliation will be retried on next startup."
            )
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session during reconciliation DB error.",
                    exc_info=True,
                )
            raise
        except Exception as e:
            logger.exception(f"An error occurred during task reconciliation: {e}")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after reconciliation error.",
                    exc_info=True,
                )

    def start_task(self, task: Task) -> dict:
        """
        Executes the performance test for a given task.

        Args:
            task (Task): The task to execute.

        Returns:
            dict: The result dictionary from the Locust runner, including run status.
        """
        task_logger = logger.bind(task_id=task.id)
        try:
            task_logger.info(f"Starting execution for task {task.id}.")
            result = self.runner.run_locust_process(task)
            return result
        except Exception as e:
            task_logger.exception(f"An unexpected error occurred during execution: {e}")
            return {
                "status": "FAILED",
                "locust_result": {},
                "stderr": str(e),
                "return_code": -1,
            }

    def process_task_pipeline(self, task: Task, session: Session):  # noqa: C901
        """
        Manages the complete pipeline for processing a single task.

        Args:
            task (Task): The task to process.
            session (Session): The SQLAlchemy database session.
        """
        handler_id = None
        task_logger = logger.bind(task_id=task.id)
        try:
            # Add task log sink first
            handler_id = add_task_log_sink(task.id)

            # Update task status to running
            self.update_task_status(session, task, TASK_STATUS_RUNNING)

            # Start the task execution
            run_result = self.start_task(task)
            task_logger.info(
                f"Task execution completed for task {task.id}, result status: {run_result.get('status', 'unknown')}"
            )

            run_status = run_result.get("status")
            locust_result = run_result.get("locust_result", {})

            # Refresh the task state to get any updates that may have occurred
            # during the run, such as a manual stop request.
            try:
                session.refresh(task)
            except (OperationalError, pymysql.err.OperationalError) as e:
                task_logger.warning(
                    f"Database connection error while refreshing task state: {e}. "
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
                    f"Task {task.id} was stopped during execution. Marking as '{TASK_STATUS_STOPPED}'."
                )
                self.update_task_status(session, task, TASK_STATUS_STOPPED)
            elif run_status == "STOPPED":
                # Task was stopped during warmup or main test phase
                task_logger.info(
                    f"Task {task.id} was stopped (possibly during warmup). Marking as '{TASK_STATUS_STOPPED}'."
                )
                self.update_task_status(session, task, TASK_STATUS_STOPPED)
            elif run_status == "COMPLETED":
                task_logger.info(
                    f"Runner completed successfully. Processing results..."
                )
                self.update_task_status(session, task, TASK_STATUS_COMPLETED)
                if locust_result:
                    # Always insert results first, regardless of outcome
                    task_logger.info(f"Inserting locust results for task {task.id}")
                    self.result_service.insert_locust_results(
                        session, locust_result, task.id
                    )
                    task_logger.info(
                        f"Locust results inserted successfully for task {task.id}"
                    )
                else:
                    error_message = (
                        f"Runner completed but no result file was generated."
                    )
                    task_logger.error(f"{error_message}")
                    self.update_task_status(
                        session, task, TASK_STATUS_FAILED, error_message
                    )
            elif run_status == "FAILED_REQUESTS":
                task_logger.warning(
                    f"Runner completed with failed requests. Processing results..."
                )
                if locust_result:
                    # Insert results even when there are failures
                    self.result_service.insert_locust_results(
                        session, locust_result, task.id
                    )

                    error_message = f"Task {task.id} completed with failed requests."
                    task_logger.warning(f"{error_message}")
                    self.update_task_status(
                        session, task, TASK_STATUS_FAILED_REQUESTS, error_message
                    )
                else:
                    error_message = f"Task {task.id} had request failures but no result file was generated."
                    task_logger.error(f"{error_message}")
                    self.update_task_status(
                        session, task, TASK_STATUS_FAILED, error_message
                    )
            elif run_status == "FAILED":
                return_code = run_result.get("return_code", "unknown")
                stderr_details = run_result.get("stderr", "No stderr.")
                error_message = f"Task {task.id} execution failed (Locust exit code: {return_code}). Details: {stderr_details}"
                task_logger.error(f"Task execution failed.")
                task_logger.error(f"Return code: {return_code}")
                task_logger.error(f"Stderr: {stderr_details}")
                self.update_task_status(
                    session, task, TASK_STATUS_FAILED, error_message
                )
            else:
                # Unexpected status from runner
                return_code = run_result.get("return_code", "unknown")
                stderr_details = run_result.get("stderr", "No stderr.")
                error_message = f"Task {task.id} returned unexpected status '{run_status}' (return code: {return_code}). Details: {stderr_details}"
                task_logger.error(f"Unexpected runner status: {run_status}")
                task_logger.error(f"Return code: {return_code}")
                task_logger.error(f"Stderr: {stderr_details}")
                self.update_task_status(
                    session, task, TASK_STATUS_FAILED, error_message
                )

        except (OperationalError, pymysql.err.OperationalError) as e:
            task_logger.warning(
                f"Database connection error in pipeline: {e}. "
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
                    f"Could not update task {task.id} status due to database error: {status_update_error}"
                )
        except Exception as e:
            error_message = f"An unexpected error occurred in the pipeline: {e}"
            task_logger.exception(f"Pipeline failed with an unexpected error: {e}")
            # Log the full traceback for debugging
            import traceback

            task_logger.error(f"Full traceback: {traceback.format_exc()}")

            # Ensure the task status is updated even if there's an exception
            try:
                self.update_task_status(
                    session, task, TASK_STATUS_FAILED, error_message
                )
                task_logger.info(
                    f"Task {task.id} status updated to FAILED after exception"
                )
            except (OperationalError, pymysql.err.OperationalError) as db_error:
                logger.warning(
                    f"Database connection error while updating failed task status: {db_error}"
                )
            except Exception as status_update_error:
                task_logger.error(
                    f"Failed to update task status after pipeline error: {status_update_error}"
                )
                # Also log to the system logger in case task logger is broken
                logger.error(
                    f"Critical: Failed to update status for task {task.id}: {status_update_error}"
                )
        finally:
            if handler_id is not None:
                remove_task_log_sink(handler_id)

    def stop_task(self, task_id: str) -> bool:
        """
        Stops a running task by delegating the termination to the LocustRunner.
        This method handles both warmup and main test phases for LLM API tasks.
        This method is designed to be called from the API or UI.
        Args:
            task_id (str): The ID of the task to stop.
        Returns:
            bool: True if the stop command was successfully dispatched or the task was not running locally.
                  False if an error occurred while trying to stop a local process.
        """
        task_logger = logger.bind(task_id=task_id)
        try:
            task_logger.info(f"Received stop request for task {task_id}.")

            # Mark this task as stopped so warmup phase can detect it
            # This is critical for stopping tasks during warmup before main test starts
            self.runner._stopped_task_ids.add(task_id)
            task_logger.debug(f"Marked task {task_id} in _stopped_task_ids.")

            # Stop both warmup and main test processes
            # Warmup process uses {task_id}_warmup as key
            warmup_task_id = f"{task_id}_warmup"
            process_ids_to_stop = [warmup_task_id, task_id]
            any_process_found = False
            all_stopped_successfully = True

            for proc_id in process_ids_to_stop:
                process = self.runner._process_dict.get(proc_id)
                if not process:
                    task_logger.debug(
                        f"Process for '{proc_id}' not found in runner's dictionary."
                    )
                    continue

                any_process_found = True
                task_logger.info(f"Found process for '{proc_id}', attempting to stop.")

                if process.poll() is not None:
                    task_logger.info(
                        f"Process '{proc_id}' with PID {process.pid} has already terminated. Cleaning up."
                    )
                    self.runner._process_dict.pop(proc_id, None)
                    cleanup_task_resources(proc_id)
                    continue

                # Check for multiprocess group
                group_info = get_task_process_status(proc_id)
                if group_info:
                    task_logger.info(
                        f"Terminating registered multiprocess group for '{proc_id}'."
                    )
                    group_terminated = terminate_locust_process_group(
                        proc_id, timeout=15.0
                    )
                    if not group_terminated:
                        task_logger.warning(
                            f"Multiprocess group termination for '{proc_id}' reported failure. "
                            "Falling back to direct termination."
                        )
                else:
                    task_logger.debug(
                        f"No registered multiprocess group for '{proc_id}'. "
                        "Using direct termination."
                    )

                # Terminate local process if still running
                if process.poll() is None:
                    if not self._terminate_local_process(process, proc_id, task_logger):
                        all_stopped_successfully = False
                else:
                    task_logger.info(
                        f"Process '{proc_id}' exited after multiprocess termination."
                    )

                self.runner._process_dict.pop(proc_id, None)
                cleanup_task_resources(proc_id)

            if not any_process_found:
                task_logger.warning(
                    f"Task {task_id}: No processes found in runner's dictionary. "
                    f"It might have finished, be on another node, or not started yet. "
                    f"Attempting to find and kill any orphaned locust processes."
                )
                # Try to find and kill any orphaned processes by task_id
                self._kill_orphaned_processes(task_id, task_logger)
                return True

            return all_stopped_successfully

        except Exception as e:
            task_logger.exception(
                f"An unexpected error occurred while stopping task {task_id}: {e}"
            )
            return False

    def _kill_orphaned_processes(self, task_id: str, task_logger) -> None:
        """
        Kill any orphaned locust processes associated with a task.
        This is a fallback when processes are not found in _process_dict.

        Args:
            task_id (str): The ID of the task.
            task_logger: Structured logger bound to the task.
        """
        try:
            import psutil

            # Find processes matching this task_id (including warmup)
            killed_count = 0
            for proc in psutil.process_iter(["pid", "cmdline"]):
                try:
                    cmdline = proc.info.get("cmdline") or []
                    if not isinstance(cmdline, list):
                        continue
                    cmdline_str = " ".join(str(arg) for arg in cmdline)

                    # Match both main task and warmup task
                    if "locust" in cmdline_str.lower() and (
                        f"--task-id {task_id}" in cmdline_str
                        or f"--task-id {task_id}_warmup" in cmdline_str
                    ):
                        task_logger.info(
                            f"Found orphaned locust process PID={proc.pid}, terminating."
                        )
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except psutil.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
                        killed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if killed_count > 0:
                task_logger.info(
                    f"Killed {killed_count} orphaned locust process(es) for task {task_id}."
                )
        except Exception as e:
            task_logger.warning(f"Error while killing orphaned processes: {e}")

    def _terminate_local_process(
        self,
        process: subprocess.Popen,
        task_id: str,
        task_logger,
        term_timeout: float = 10.0,
    ) -> bool:
        """
        Terminate a single Locust process with graceful fallback to SIGKILL.

        Args:
            process (subprocess.Popen): The process to terminate.
            task_id (str): The task identifier for logging.
            task_logger: Structured logger bound to the task.
            term_timeout (float): Timeout for graceful termination.

        Returns:
            bool: True if the process was terminated or already exited, False otherwise.
        """
        try:
            if process.poll() is not None:
                task_logger.debug(
                    f"Task {task_id}: Process already exited with code {process.returncode}."
                )
                return True

            task_logger.info(
                f"Task {task_id}: Sending SIGTERM to process PID {process.pid}."
            )
            process.terminate()
            try:
                process.wait(timeout=term_timeout)
                task_logger.info(
                    f"Task {task_id}: Process PID {process.pid} terminated via SIGTERM."
                )
                return True
            except subprocess.TimeoutExpired:
                task_logger.warning(
                    f"Task {task_id}: SIGTERM timed out after {term_timeout}s. Sending SIGKILL."
                )
                process.kill()
                process.wait(timeout=5.0)
                task_logger.info(
                    f"Task {task_id}: Process PID {process.pid} terminated via SIGKILL."
                )
                return True
        except subprocess.TimeoutExpired:
            task_logger.error(
                f"Task {task_id}: SIGKILL timed out. Manual intervention may be required."
            )
        except ProcessLookupError:
            task_logger.info(
                f"Task {task_id}: Process PID {process.pid if process else 'unknown'} no longer exists."
            )
            return True
        except Exception as e:
            task_logger.exception(
                f"Task {task_id}: Unexpected error during process termination: {e}"
            )

        return False

    def get_stopping_task_ids(self, session: Session) -> list[str]:
        """
        Retrieves a list of task IDs with the 'stopping' status.

        Args:
            session (Session): The SQLAlchemy database session.

        Returns:
            list[str]: A list of task IDs to be stopped.
        """
        try:
            query = select(Task.id).where(Task.status == TASK_STATUS_STOPPING)
            stopping_task_ids = list(session.execute(query).scalars().all())
            if stopping_task_ids:
                logger.info(f"Found stopping tasks: {stopping_task_ids}")
            return stopping_task_ids
        except (OperationalError, pymysql.err.OperationalError) as e:
            logger.warning(
                f"Database connection error while fetching stopping tasks: {e}. "
                "This may be a transient database issue. Returning empty list."
            )
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after DB error.", exc_info=True
                )
            return []
        except Exception as e:
            logger.exception("Failed to get stopping task IDs from the database.")
            try:
                session.rollback()
            except Exception:
                logger.debug(
                    "Failed to rollback session after unexpected error.",
                    exc_info=True,
                )
            return []
