"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Probe service: create, wait, submit, and cleanup probe tasks.
Probes are lightweight connectivity tests dispatched to engine clusters.
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.mysql import async_session_factory
from model.probe_task import ProbeTask
from utils.logger import logger

PROBE_EXECUTION_TIMEOUT = float(os.getenv("PROBE_EXECUTION_TIMEOUT", "30"))
PROBE_RESULT_GRACE_SECONDS = float(os.getenv("PROBE_RESULT_GRACE_SECONDS", "15"))
PROBE_TIMEOUT_DEFAULT = float(
    os.getenv(
        "PROBE_RESULT_TIMEOUT",
        str(PROBE_EXECUTION_TIMEOUT + PROBE_RESULT_GRACE_SECONDS),
    )
)
PROBE_POLL_INTERVAL = 0.5
PROBE_EXPIRE_SECONDS = max(60, int(PROBE_TIMEOUT_DEFAULT + 15))
PROBE_DELETE_SECONDS = 300


async def create_probe(
    db: AsyncSession,
    cluster_id: str,
    probe_type: str,
    request_config: dict,
) -> str:
    probe_id = str(uuid.uuid4())
    probe = ProbeTask(
        id=probe_id,
        cluster_id=cluster_id,
        probe_type=probe_type,
        status="pending",
        request_config=request_config,
    )
    db.add(probe)
    await db.commit()
    return probe_id


async def wait_for_probe_result(
    probe_id: str, timeout: float = PROBE_TIMEOUT_DEFAULT
) -> dict:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_probe = None

    while True:
        async with async_session_factory() as session:
            probe = await session.get(ProbeTask, probe_id)
            last_probe = probe
            if probe and probe.status in ("completed", "failed"):
                return probe.result or {
                    "status": "error",
                    "error": "The engine returned an empty probe result.",
                    "response": None,
                }

        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        await asyncio.sleep(min(PROBE_POLL_INTERVAL, remaining))

    if last_probe and last_probe.status == "claimed":
        error = (
            f"Engine {last_probe.engine_id or 'unknown'} claimed the API test but "
            f"did not return a result within {timeout:g} seconds. The target API "
            "may be responding slowly."
        )
    elif last_probe and last_probe.status == "pending":
        error = (
            "No engine in the selected cluster claimed the API test within "
            f"{timeout:g} seconds. Please verify engine registration and health."
        )
    else:
        error = (
            f"The API test did not complete within {timeout:g} seconds. "
            "Please retry and verify engine health."
        )

    return {"status": "error", "error": error, "response": None}


async def submit_probe_result(
    db: AsyncSession,
    probe_id: str,
    engine_id: str,
    result: dict,
) -> bool:
    probe = await db.get(ProbeTask, probe_id)
    if not probe:
        logger.warning(f"Probe {probe_id} not found for result submission")
        return False
    if probe.engine_id and probe.engine_id != engine_id:
        logger.warning(
            f"Engine {engine_id} tried to submit result for probe {probe_id} "
            f"owned by {probe.engine_id}"
        )
        return False

    status = result.get("status", "error")
    probe.status = "completed" if status == "success" else "failed"
    probe.result = result
    probe.completed_at = datetime.utcnow()
    await db.commit()
    return True


async def cleanup_expired_probes():
    async with async_session_factory() as session:
        try:
            now = datetime.utcnow()

            # Expiration always remains beyond the synchronous result deadline.
            expire_cutoff = now - timedelta(seconds=PROBE_EXPIRE_SECONDS)
            await session.execute(
                update(ProbeTask)
                .where(
                    and_(
                        ProbeTask.status.in_(["pending", "claimed"]),
                        ProbeTask.created_at < expire_cutoff,
                    )
                )
                .values(status="expired")
            )

            # Delete probes older than 5 minutes
            delete_cutoff = now - timedelta(seconds=PROBE_DELETE_SECONDS)
            await session.execute(
                delete(ProbeTask).where(ProbeTask.created_at < delete_cutoff)
            )

            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning(f"[ProbeService] Cleanup error: {e}")
