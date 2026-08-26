"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Cluster management service: list, status, scaling operations.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from model.cluster import Cluster
from model.engine import EngineHeartbeat
from service.engine_service import HEARTBEAT_STALE_SECONDS
from utils.logger import logger


async def list_clusters(db: AsyncSession) -> List[dict]:
    result = await db.execute(select(Cluster).order_by(Cluster.created_at.asc()))
    clusters = result.scalars().all()

    output = []
    for cluster in clusters:
        stale_cutoff = datetime.utcnow() - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
        alive_condition = and_(
            EngineHeartbeat.status != "offline",
            EngineHeartbeat.last_heartbeat >= stale_cutoff,
        )

        engine_stats = await db.execute(
            select(
                func.count(EngineHeartbeat.engine_id).label("total"),
                func.sum(func.IF(alive_condition, 1, 0)).label("online"),
                func.coalesce(
                    func.sum(
                        func.IF(
                            alive_condition,
                            EngineHeartbeat.available_slots,
                            0,
                        )
                    ),
                    0,
                ).label("available_slots"),
            ).where(EngineHeartbeat.cluster_id == cluster.id)
        )
        stats = engine_stats.one()

        online_engines = int(stats.online or 0)
        available_slots = int(stats.available_slots or 0)

        output.append(
            {
                "id": cluster.id,
                "name": cluster.name,
                "description": cluster.description,
                "status": cluster.status,
                "online_engines": online_engines,
                "available_slots": available_slots,
                "running_tasks": await _count_running_tasks(db, cluster.id),
                "desired_replicas": cluster.desired_replicas,
                "current_replicas": cluster.current_replicas,
                "ready_replicas": cluster.ready_replicas,
                "min_replicas": cluster.min_replicas,
                "max_replicas": cluster.max_replicas,
            }
        )

    return output


async def get_cluster(db: AsyncSession, cluster_id: str) -> Optional[dict]:
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        return None

    return {
        "id": cluster.id,
        "name": cluster.name,
        "description": cluster.description,
        "status": cluster.status,
        "desired_replicas": cluster.desired_replicas,
        "min_replicas": cluster.min_replicas,
        "max_replicas": cluster.max_replicas,
        "current_replicas": cluster.current_replicas,
        "ready_replicas": cluster.ready_replicas,
    }


async def get_desired_state(db: AsyncSession, cluster_id: str) -> Optional[dict]:
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        return None

    return {
        "desired_replicas": cluster.desired_replicas,
        "min_replicas": cluster.min_replicas,
        "max_replicas": cluster.max_replicas,
    }


async def update_actual_state(
    db: AsyncSession,
    cluster_id: str,
    current_replicas: int,
    ready_replicas: int,
    available_replicas: int,
) -> bool:
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        return False

    cluster.current_replicas = current_replicas
    cluster.ready_replicas = ready_replicas
    await db.flush()
    return True


async def scale_cluster(
    db: AsyncSession, cluster_id: str, desired_replicas: int
) -> Optional[dict]:
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        return None

    clamped = max(cluster.min_replicas, min(desired_replicas, cluster.max_replicas))
    cluster.desired_replicas = clamped
    await db.flush()

    return {
        "cluster_id": cluster_id,
        "desired_replicas": clamped,
        "min_replicas": cluster.min_replicas,
        "max_replicas": cluster.max_replicas,
    }


async def create_cluster(
    db: AsyncSession,
    cluster_id: str,
    name: str,
    description: Optional[str] = None,
    min_replicas: int = 1,
    max_replicas: int = 10,
) -> dict:
    cluster = Cluster(
        id=cluster_id,
        name=name,
        description=description,
        status="active",
        desired_replicas=min_replicas,
        min_replicas=min_replicas,
        max_replicas=max_replicas,
    )
    db.add(cluster)
    await db.flush()
    return {
        "id": cluster.id,
        "name": cluster.name,
        "status": cluster.status,
    }


async def _count_running_tasks(db: AsyncSession, cluster_id: str) -> int:
    from model.http_task import HttpTask
    from model.llm_task import Task as LlmTask

    total = 0
    for TaskModel in [LlmTask, HttpTask]:
        result = await db.execute(
            select(func.count()).where(
                and_(
                    TaskModel.cluster_id == cluster_id,
                    TaskModel.status.in_(["running", "queuing"]),
                    TaskModel.is_deleted == 0,
                )
            )
        )
        total += result.scalar() or 0

    return total
