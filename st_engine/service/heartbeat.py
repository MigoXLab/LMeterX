"""
Engine heartbeat service.

Provides liveness tracking for engine instances so that surviving instances
can detect dead peers and reconcile their orphaned tasks.

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import time
from typing import List

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from db.database import get_db_session
from model.engine_heartbeat import EngineHeartbeat
from utils.logger import logger
from utils.vm_push import ENGINE_ID

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------

# How often to write heartbeat (seconds)
HEARTBEAT_INTERVAL: int = int(os.environ.get("ENGINE_HEARTBEAT_INTERVAL", "10"))

# How long before an engine is considered dead (seconds).
# Must be significantly larger than HEARTBEAT_INTERVAL to tolerate transient
# database hiccups.
HEARTBEAT_STALE_SECONDS: int = int(
    os.environ.get("ENGINE_HEARTBEAT_STALE_SECONDS", "60")
)

# How often to run cross-engine reconciliation (seconds)
RECONCILE_INTERVAL: int = int(os.environ.get("ENGINE_RECONCILE_INTERVAL", "30"))


# ---------------------------------------------------------------------------
# Table management
# ---------------------------------------------------------------------------


def ensure_heartbeat_table():
    """Create the ``engine_heartbeats`` table if it does not already exist.

    Must be called **after** :func:`db.database.init_db` has successfully
    initialised the synchronous engine.
    """
    from db import database as db_mod

    if db_mod.engine is None:
        raise RuntimeError("Database engine is not initialised; call init_db() first.")

    EngineHeartbeat.__table__.create(db_mod.engine, checkfirst=True)
    logger.info("Engine heartbeat table ensured.")


# ---------------------------------------------------------------------------
# Heartbeat read / write
# ---------------------------------------------------------------------------


def update_heartbeat(session: Session):
    """Insert or update the heartbeat timestamp for the current engine.

    Uses MySQL ``INSERT … ON DUPLICATE KEY UPDATE`` to guarantee a single
    round-trip regardless of whether the row already exists.  The timestamp
    is always ``NOW()`` (database server time) to avoid clock-skew between
    containers.
    """
    session.execute(
        text(
            "INSERT INTO engine_heartbeats (engine_id, last_heartbeat) "
            "VALUES (:engine_id, NOW()) "
            "ON DUPLICATE KEY UPDATE last_heartbeat = NOW()"
        ),
        {"engine_id": ENGINE_ID},
    )
    session.commit()


def get_stale_engine_ids(session: Session) -> List[str]:
    """Return engine IDs whose heartbeat is older than the stale threshold.

    Only returns engines other than the current one.  Engines without any
    heartbeat record are **not** included (they may be running an older
    version that does not support heartbeats).
    """
    result = (
        session.execute(
            select(EngineHeartbeat.engine_id)
            .where(
                EngineHeartbeat.last_heartbeat
                < text(f"NOW() - INTERVAL {HEARTBEAT_STALE_SECONDS} SECOND")
            )
            .where(EngineHeartbeat.engine_id != ENGINE_ID)
        )
        .scalars()
        .all()
    )
    return list(result)


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------


def heartbeat_and_reconcile_loop():
    """Background daemon thread: heartbeat writer + periodic dead-engine reconciler.

    * Writes a heartbeat every ``HEARTBEAT_INTERVAL`` seconds.
    * Runs cross-engine orphan-task reconciliation every ``RECONCILE_INTERVAL``
      seconds.
    """
    # Lazy imports to break circular dependency
    # (task_service -> heartbeat -> task_service)
    from service.common_task_service import CommonTaskService
    from service.task_service import TaskService

    task_svc = TaskService()
    common_task_svc = CommonTaskService()
    last_reconcile: float = 0

    logger.info(
        f"Heartbeat loop started: engine_id={ENGINE_ID}, "
        f"heartbeat_interval={HEARTBEAT_INTERVAL}s, "
        f"stale_threshold={HEARTBEAT_STALE_SECONDS}s, "
        f"reconcile_interval={RECONCILE_INTERVAL}s"
    )

    while True:
        # --- heartbeat ---
        try:
            with get_db_session() as session:
                update_heartbeat(session)
        except Exception as e:
            logger.debug(f"Heartbeat write failed (non-fatal): {e}")

        # --- periodic dead-engine reconciliation ---
        now = time.time()
        if now - last_reconcile > RECONCILE_INTERVAL:
            _run_dead_engine_reconciliation(task_svc, common_task_svc)
            last_reconcile = now

        time.sleep(HEARTBEAT_INTERVAL)


def _run_dead_engine_reconciliation(task_svc, common_task_svc):
    """Execute one round of dead-engine task reconciliation."""
    try:
        with get_db_session() as session:
            task_svc.reconcile_dead_engine_tasks(session)
    except Exception as e:
        logger.debug(f"Dead engine reconciliation (LLM tasks) failed: {e}")

    try:
        with get_db_session() as session:
            common_task_svc.reconcile_dead_engine_tasks(session)
    except Exception as e:
        logger.debug(f"Dead engine reconciliation (common tasks) failed: {e}")
