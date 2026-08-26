"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Backend background scheduler for task lifecycle management.
Runs periodic tasks:
1. Enqueue: Move 'created' tasks to 'queuing' status
2. Reconcile: Detect dead engines and fail their orphaned tasks
"""

import asyncio
import os
from datetime import datetime, timedelta

from sqlalchemy import and_, select, update

from db.mysql import async_session_factory
from model.engine import EngineHeartbeat
from utils.logger import logger

ENQUEUE_INTERVAL = int(os.getenv("BACKEND_ENQUEUE_INTERVAL", "3"))
RECONCILE_INTERVAL = int(os.getenv("BACKEND_RECONCILE_INTERVAL", "30"))
K8S_RECONCILE_INTERVAL = int(os.getenv("K8S_RECONCILE_INTERVAL", "60"))
K8S_RECONCILE_ENABLED = os.getenv("K8S_RECONCILE_ENABLED", "false").lower() == "true"
RECONCILE_CLUSTER_ID = os.getenv("RECONCILE_CLUSTER_ID") or os.getenv("CLUSTER_ID", "")
PROBE_CLEANUP_INTERVAL = 60
HEARTBEAT_STALE_SECONDS = int(os.getenv("ENGINE_HEARTBEAT_STALE_SECONDS", "60"))

_scheduler_task: asyncio.Task = None


async def _enqueue_created_tasks():
    """Move all 'created' tasks to 'queuing' status."""
    from model.http_task import HttpTask
    from model.llm_task import Task as LlmTask
    from model.task_dispatch_queue import TaskDispatchQueue

    async with async_session_factory() as session:
        try:
            total = 0
            for task_type, TaskModel in [("llm", LlmTask), ("http", HttpTask)]:
                result = await session.execute(
                    update(TaskModel)
                    .where(
                        and_(
                            TaskModel.status == "created",
                            TaskModel.is_deleted == 0,
                        )
                    )
                    .values(status="queuing")
                )
                total += result.rowcount

                # Only activate entries whose business task is already queuing.
                # The correlation prevents a task created concurrently with this
                # scheduler pass from exposing its queue row one cycle too early.
                await session.execute(
                    update(TaskDispatchQueue)
                    .where(
                        TaskDispatchQueue.status == "created",
                        TaskDispatchQueue.task_type == task_type,
                        TaskDispatchQueue.task_id.in_(
                            select(TaskModel.id).where(
                                TaskModel.status == "queuing",
                                TaskModel.is_deleted == 0,
                            )
                        ),
                    )
                    .values(status="queued")
                )

            await session.commit()
            if total > 0:
                logger.info(f"[Scheduler] Enqueued {total} task(s): created -> queuing")
        except Exception as e:
            await session.rollback()
            logger.warning(f"[Scheduler] Enqueue error: {e}")


async def _reconcile_dead_engines():
    """Detect dead engines and fail their running tasks."""
    from model.http_task import HttpTask
    from model.llm_task import Task as LlmTask

    async with async_session_factory() as session:
        try:
            stale_cutoff = datetime.utcnow() - timedelta(
                seconds=HEARTBEAT_STALE_SECONDS
            )

            stale_result = await session.execute(
                select(EngineHeartbeat.engine_id).where(
                    EngineHeartbeat.last_heartbeat < stale_cutoff
                )
            )
            stale_ids = [row[0] for row in stale_result.all()]

            if not stale_ids:
                return

            count = 0
            for TaskModel in [LlmTask, HttpTask]:
                result = await session.execute(
                    update(TaskModel)
                    .where(
                        and_(
                            TaskModel.status.in_(["running", "stopping"]),
                            TaskModel.engine_id.in_(stale_ids),
                            TaskModel.is_deleted == 0,
                        )
                    )
                    .values(
                        status="failed",
                        error_message="Engine instance is no longer alive (heartbeat timeout).",
                    )
                )
                count += result.rowcount

            await session.execute(
                update(EngineHeartbeat)
                .where(EngineHeartbeat.engine_id.in_(stale_ids))
                .values(status="offline")
            )

            await session.commit()

            if count > 0:
                logger.info(
                    f"[Scheduler] Reconciled {count} orphaned task(s) from dead engines: {stale_ids}"
                )
        except Exception as e:
            await session.rollback()
            logger.warning(f"[Scheduler] Reconciliation error: {e}")


async def _reconcile_with_k8s():
    """Cross-check registered engines against actual running K8s pods.
    Only cleans engines in RECONCILE_CLUSTER_ID to avoid affecting remote clusters.
    """
    if not K8S_RECONCILE_ENABLED:
        return

    if not RECONCILE_CLUSTER_ID:
        logger.debug("[Scheduler] K8s reconcile skipped: RECONCILE_CLUSTER_ID not set")
        return

    from service.k8s_service import get_active_engine_uids

    active_uids = await asyncio.get_event_loop().run_in_executor(
        None, get_active_engine_uids
    )
    if active_uids is None:
        return

    async with async_session_factory() as session:
        try:
            from service.engine_service import cleanup_stale_engines

            count = await cleanup_stale_engines(
                db=session,
                valid_engine_ids=active_uids,
                cluster_id=RECONCILE_CLUSTER_ID,
            )
            await session.commit()

            if count > 0:
                logger.info(
                    f"[Scheduler] K8s reconcile: marked {count} ghost engine(s) as offline "
                    f"in cluster={RECONCILE_CLUSTER_ID}"
                )
        except Exception as e:
            await session.rollback()
            logger.warning(f"[Scheduler] K8s reconciliation error: {e}")


async def _scheduler_loop():
    """Main scheduler loop running enqueue and reconciliation on intervals."""
    logger.info("[Scheduler] Background scheduler started.")
    enqueue_counter = 0
    reconcile_counter = 0
    k8s_reconcile_counter = 0
    probe_cleanup_counter = 0

    while True:
        try:
            await asyncio.sleep(1)
            enqueue_counter += 1
            reconcile_counter += 1
            k8s_reconcile_counter += 1
            probe_cleanup_counter += 1

            if enqueue_counter >= ENQUEUE_INTERVAL:
                enqueue_counter = 0
                await _enqueue_created_tasks()

            if reconcile_counter >= RECONCILE_INTERVAL:
                reconcile_counter = 0
                await _reconcile_dead_engines()

            if (
                K8S_RECONCILE_ENABLED
                and k8s_reconcile_counter >= K8S_RECONCILE_INTERVAL
            ):
                k8s_reconcile_counter = 0
                await _reconcile_with_k8s()

            if probe_cleanup_counter >= PROBE_CLEANUP_INTERVAL:
                probe_cleanup_counter = 0
                from service.probe_service import cleanup_expired_probes

                await cleanup_expired_probes()

        except asyncio.CancelledError:
            logger.info("[Scheduler] Background scheduler stopped.")
            break
        except Exception as e:
            logger.exception(f"[Scheduler] Unexpected error: {e}")
            await asyncio.sleep(5)


def start_scheduler():
    """Start the background scheduler as an asyncio task."""
    global _scheduler_task
    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(_scheduler_loop())
    logger.info("[Scheduler] Background scheduler task created.")


def stop_scheduler():
    """Cancel the background scheduler task."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
