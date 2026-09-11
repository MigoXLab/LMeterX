"""Helpers for maintaining the unified task dispatch queue."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from model.task_dispatch_queue import TaskDispatchQueue


def add_dispatch_entry(
    db: AsyncSession, *, task_type: str, task_id: str, cluster_id: str
) -> TaskDispatchQueue:
    """Add a dispatch entry to the same transaction as its business task."""
    entry = TaskDispatchQueue(
        task_type=task_type,
        task_id=task_id,
        cluster_id=cluster_id,
        status="created",
    )
    db.add(entry)
    return entry


async def cancel_dispatch_entry(
    db: AsyncSession, *, task_type: str, task_id: str
) -> None:
    """Make an unclaimed task ineligible for future dispatch."""
    await db.execute(
        update(TaskDispatchQueue)
        .where(
            TaskDispatchQueue.task_type == task_type,
            TaskDispatchQueue.task_id == task_id,
            TaskDispatchQueue.status.in_(["created", "queued"]),
        )
        .values(status="cancelled")
    )
