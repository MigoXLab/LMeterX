"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Probe task model: lightweight connectivity test tasks dispatched to engines.
"""

from sqlalchemy import Column, DateTime, Index, String, func
from sqlalchemy.dialects.mysql import JSON

from db.mysql import Base


class ProbeTask(Base):
    __tablename__ = "probe_tasks"
    __table_args__ = (
        Index("idx_probe_cluster_status", "cluster_id", "status"),
        Index("idx_probe_created_at", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    cluster_id = Column(String(64), nullable=False)
    probe_type = Column(String(10), nullable=False)  # "llm" | "http"
    status = Column(String(16), nullable=False, default="pending")
    engine_id = Column(String(64), nullable=True)
    request_config = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
