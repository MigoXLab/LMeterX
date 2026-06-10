"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import time
from datetime import datetime, timezone

from config.base import LOCUST_STOP_TIMEOUT
from config.business import TASK_STATUS_FAILED, TASK_STATUS_STOPPED
from db.database import get_db_session
from service.http_task_service import HttpTaskService
from service.llm_task_service import LlmTaskService
from utils.logger import logger

STOPPING_TIMEOUT_SECONDS = LOCUST_STOP_TIMEOUT * 2


def _is_stopping_timed_out(session, task_id: str, task_service) -> bool:
    """Check if a task in 'stopping' state has exceeded the timeout threshold."""
    try:
        model_cls = task_service.model_cls
        task = session.get(model_cls, task_id)
        if task and task.updated_at:
            updated_at = task.updated_at
            if updated_at.tzinfo is None:
                elapsed = (datetime.now() - updated_at).total_seconds()
            else:
                elapsed = (datetime.now(timezone.utc) - updated_at).total_seconds()
            return elapsed > STOPPING_TIMEOUT_SECONDS
    except Exception as e:
        logger.debug(f"Error checking stopping timeout for task {task_id}: {e}")
    return False


def llm_task_enqueue_poller():
    """
    Lightweight non-blocking loop that moves 'created' tasks to 'pending'.

    Runs independently from the execution poller so that new tasks become
    visible as "queuing" even when the engine is busy executing another task.
    """
    task_service = LlmTaskService()
    logger.info("[LLM] Task enqueue poller started.")

    while True:
        try:
            with get_db_session() as session:
                task_service.enqueue_created_tasks(session)
            time.sleep(3)
        except Exception as e:
            logger.exception(f"[LLM] Error in task enqueue poller: {e}")
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                time.sleep(30)
            else:
                time.sleep(10)


def llm_task_create_poller():
    """
    Polls for pending tasks and executes them when engine has capacity.

    This poller only handles claiming and executing tasks. The separate
    enqueue poller (llm_task_enqueue_poller) handles moving tasks from
    'created' to 'pending' independently.
    """
    task_service = LlmTaskService()

    # Perform startup reconciliation to clean up stale tasks from a previous run.
    try:
        with get_db_session() as session:
            task_service.reconcile_tasks_on_startup(session)
    except Exception as e:
        logger.exception(f"Failed to run startup task reconciliation: {e}")

    logger.info("[LLM] Task execution poller started. Listening for pending tasks...")

    while True:
        try:
            with get_db_session() as session:
                task = task_service.claim_pending_task(session)
                if task:
                    logger.info(
                        f"[LLM] Poller claimed task: {task.id}. Starting execution."
                    )
                    task_service.process_task_pipeline(task, session)
            # Wait for a short interval before the next poll
            time.sleep(3)
        except Exception as e:
            logger.exception(
                f"[LLM] An error occurred in the task execution poller: {e}"
            )
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                logger.warning(
                    "[LLM] Database connection lost. Retrying in 30 seconds..."
                )
                time.sleep(30)
            else:
                # Wait longer for other types of errors before retrying
                time.sleep(10)


def llm_task_stop_poller():
    """
    Periodically polls the database for tasks that need to be stopped.

    This function checks for tasks with the 'stopping' status and attempts to
    terminate the corresponding Locust process.
    """
    logger.info("[LLM] Task stopping poller started. Listening for tasks to stop...")
    task_service = LlmTaskService()

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
                            if _is_stopping_timed_out(session, task_id, task_service):
                                logger.warning(
                                    f"[LLM] Task {task_id} exceeded stopping timeout ({STOPPING_TIMEOUT_SECONDS}s). Force marking as stopped."
                                )
                                task_service.update_task_status_by_id(
                                    session, task_id, TASK_STATUS_STOPPED
                                )
                            else:
                                logger.warning(
                                    f"[LLM] Poller failed to stop task {task_id} (stop_task returned False). Will retry."
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


def http_task_enqueue_poller():
    """
    Lightweight non-blocking loop that moves 'created' HTTP tasks to 'pending'.

    Runs independently from the execution poller so that new tasks become
    visible as "queuing" even when the engine is busy executing another task.
    """
    task_service = HttpTaskService()
    logger.info("[HTTP] Task enqueue poller started.")

    while True:
        try:
            with get_db_session() as session:
                task_service.enqueue_created_tasks(session)
            time.sleep(3)
        except Exception as e:
            logger.exception(f"[HTTP] Error in task enqueue poller: {e}")
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                time.sleep(30)
            else:
                time.sleep(10)


def http_task_create_poller():
    """Poller for HTTP API tasks: claims pending tasks and executes them."""
    task_service = HttpTaskService()

    try:
        with get_db_session() as session:
            try:
                task_service.reconcile_tasks_on_startup(session)
            except Exception:
                logger.debug(
                    "Failed to run startup reconciliation for HTTP tasks.",
                    exc_info=True,
                )
    except Exception as e:
        logger.exception(f" Failed to run startup reconciliation: {e}")

    logger.info("[HTTP] Task execution poller started.")
    while True:
        try:
            with get_db_session() as session:
                task = task_service.claim_pending_task(session)
                if task:
                    logger.info(
                        f"[HTTP] Poller claimed task: {task.id}. Starting execution."
                    )
                    task_service.process_task_pipeline(task, session)
            time.sleep(3)
        except Exception as e:
            logger.exception(f"[HTTP] Error in task execution poller: {e}")
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                time.sleep(30)
            else:
                time.sleep(10)


def http_task_stop_poller():
    """Poller to stop HTTP API tasks."""
    logger.info(" Task stopping poller started.")
    task_service = HttpTaskService()

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
                            if _is_stopping_timed_out(session, task_id, task_service):
                                logger.warning(
                                    f" Task {task_id} exceeded stopping timeout ({STOPPING_TIMEOUT_SECONDS}s). Force marking as stopped."
                                )
                                task_service.update_task_status_by_id(
                                    session, task_id, TASK_STATUS_STOPPED
                                )
                            else:
                                logger.warning(
                                    f" Failed to stop task {task_id} (stop_task returned False). Will retry."
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
            logger.exception(f" Error in HTTP task stopping poller: {e}")
            if "Lost connection" in str(e) or "Connection refused" in str(e):
                time.sleep(30)
            else:
                time.sleep(10)
