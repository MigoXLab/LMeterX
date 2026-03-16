"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from sqlalchemy import Column, DateTime, String, func

from db.mysql import Base


class EngineHeartbeat(Base):
    """Tracks engine instance liveness for cross-instance task reconciliation.

    Each engine periodically updates its ``last_heartbeat`` timestamp.
    When an engine instance disappears (e.g. due to ``docker compose --scale``
    or a crash), its heartbeat becomes stale. Surviving instances detect the
    stale heartbeat and mark orphaned tasks as failed.
    """

    __tablename__ = "engine_heartbeats"

    engine_id = Column(String(64), primary_key=True)
    last_heartbeat = Column(DateTime, nullable=False, server_default=func.now())
