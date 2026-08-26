"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from sqlalchemy import Column, DateTime, Enum, Float, Index, Integer, String, Text, func

from db.mysql import Base


class EngineHeartbeat(Base):
    __tablename__ = "engine_heartbeats"
    __table_args__ = (Index("idx_cluster_status", "cluster_id", "status"),)

    engine_id = Column(String(64), primary_key=True)
    deployment_name = Column(String(128), nullable=True)
    pod_name = Column(String(253), nullable=True)
    cluster_id = Column(String(64), nullable=False, default="local")
    status = Column(Enum("online", "busy", "offline"), nullable=False, default="online")
    last_heartbeat = Column(DateTime, nullable=False, server_default=func.now())
    running_tasks = Column(Text, nullable=True)
    cpu_usage = Column(Float, nullable=False, default=0)
    memory_usage = Column(Float, nullable=False, default=0)
    available_slots = Column(Integer, nullable=False, default=1)
    version = Column(String(32), nullable=True)
    registered_at = Column(DateTime, nullable=False, server_default=func.now())
