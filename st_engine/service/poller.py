"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import time

from config.business import TASK_STATUS_FAILED, TASK_STATUS_LOCKED, TASK_STATUS_STOPPED
from db.database import get_db_session
from service.common_task_service import CommonTaskService
from service.task_service import TaskService
from utils.logger import logger


def task_create_poller():
    """
    Periodically polls the database for new tasks to execute.

    This function runs in an infinite loop, checking for tasks with the 'created'
    status. When a new task is found, it locks the task and initiates the
    processing pipeline.
    """
    task_service = TaskService()

    # Perform startup reconciliation to clean up stale tasks from a previous run.
    try:
        with get_db_session() as session:
            task_service.reconcile_tasks_on_startup(session)
    except Exception as e:
        logger.exception(f"Failed to run startup task reconciliation: {e}")

    logger.info(
        "[LLM] Task creation poller started. Listening for new performance tasks..."
    )

    while True:
        try:
            with get_db_session() as session:
                task = task_service.get_and_lock_task(session)
                if task:
                    logger.info(
                        f"[LLM] Poller found new task: {task.id}. Locking and processing."
                    )
                    # The status is already set to 'locked' within get_and_lock_task,
                    # but an explicit update here can be a safeguard.
                    task_service.update_task_status(session, task, TASK_STATUS_LOCKED)
                    task_service.process_task_pipeline(task, session)
            # Wait for a short interval before the next poll
            time.sleep(3)
        except Exception as e:
            logger.exception(
                f"[LLM] An error occurred in the task creation poller: {e}"
            )
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                logger.warning(
                    "[LLM] Database connection lost. Retrying in 30 seconds..."
                )
                time.sleep(30)
            else:
                # Wait longer for other types of errors before retrying
                time.sleep(10)


def task_stop_poller():
    """
    Periodically polls the database for tasks that need to be stopped.

    This function checks for tasks with the 'stopping' status and attempts to
    terminate the corresponding Locust process.
    """
    logger.info("[LLM] Task stopping poller started. Listening for tasks to stop...")
    task_service = TaskService()

    while True:
        try:
            with get_db_session() as session:
                stopping_task_ids = task_service.get_stopping_task_ids(session)
                if not stopping_task_ids:
                    # No tasks to stop, continue to the next iteration
                    time.sleep(5)
                    continue

                for task_id in stopping_task_ids:
                    logger.info(
                        f"[LLM] Poller found task to stop: {task_id}. Attempting to stop."
                    )

                    # Add a small delay to avoid conflicting with natural shutdown processes
                    # that might be happening around the same time
                    time.sleep(1)

                    try:
                        if task_service.stop_task(task_id):
                            task_service.update_task_status_by_id(
                                session, task_id, TASK_STATUS_STOPPED
                            )
                            logger.info(
                                f"[LLM] Poller successfully stopped task {task_id} and updated status to '{TASK_STATUS_STOPPED}'."
                            )
                        else:
                            logger.error(
                                f"[LLM] Poller failed to stop task {task_id} (stop_task returned False)."
                            )
                            task_service.update_task_status_by_id(
                                session,
                                task_id,
                                TASK_STATUS_FAILED,
                            )
                    except Exception as stop_e:
                        logger.error(
                            f"[LLM] Poller encountered exception while stopping task {task_id}: {stop_e}"
                        )
                        # Still try to update status to failed
                        try:
                            task_service.update_task_status_by_id(
                                session,
                                task_id,
                                TASK_STATUS_FAILED,
                            )
                        except Exception as update_e:
                            logger.error(
                                f"[LLM] Poller failed to update task {task_id} status to failed: {update_e}"
                            )
            # Wait after processing a batch of tasks
            time.sleep(5)
        except Exception as e:
            logger.exception(
                f"[LLM] An error occurred in the task stopping poller: {e}"
            )
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                logger.warning(
                    "[LLM] Database connection lost. Retrying in 30 seconds..."
                )
                time.sleep(30)
            else:
                time.sleep(10)


def common_task_create_poller():
    """Poller for common API tasks."""
    task_service = CommonTaskService()

    try:
        with get_db_session() as session:
            try:
                task_service.reconcile_tasks_on_startup(session)
            except Exception:
                pass
    except Exception as e:
        logger.exception(f" Failed to run startup reconciliation: {e}")

    logger.info(" Task creation poller started.")
    while True:
        try:
            with get_db_session() as session:
                task = task_service.get_and_lock_task(session)
                if task:
                    logger.info(f" Poller found new task: {task.id}")
                    task_service.update_task_status(session, task, TASK_STATUS_LOCKED)
                    task_service.process_task_pipeline(task, session)
            time.sleep(3)
        except Exception as e:
            logger.exception(f" Error in common task creation poller: {e}")
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                time.sleep(30)
            else:
                time.sleep(10)


def common_task_stop_poller():
    """Poller to stop common API tasks."""
    logger.info(" Task stopping poller started.")
    task_service = CommonTaskService()

    while True:
        try:
            with get_db_session() as session:
                stopping_ids = task_service.get_stopping_task_ids(session)
                if not stopping_ids:
                    time.sleep(5)
                    continue
                for task_id in stopping_ids:
                    time.sleep(1)
                    try:
                        if task_service.stop_task(task_id):
                            task_service.update_task_status_by_id(
                                session, task_id, TASK_STATUS_STOPPED
                            )
                        else:
                            task_service.update_task_status_by_id(
                                session, task_id, TASK_STATUS_FAILED
                            )
                    except Exception as stop_e:
                        logger.error(
                            f" Exception while stopping task {task_id}: {stop_e}"
                        )
                        try:
                            task_service.update_task_status_by_id(
                                session, task_id, TASK_STATUS_FAILED
                            )
                        except Exception as update_e:
                            logger.error(
                                f" Failed to update task {task_id} status to failed: {update_e}"
                            )
            time.sleep(5)
        except Exception as e:
            logger.exception(f" Error in common task stopping poller: {e}")
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                time.sleep(30)
            else:
                time.sleep(10)
