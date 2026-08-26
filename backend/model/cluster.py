"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text, func

from db.mysql import Base


class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        Enum("active", "inactive", "draining"), nullable=False, default="active"
    )
    desired_replicas = Column(Integer, nullable=False, default=1)
    min_replicas = Column(Integer, nullable=False, default=1)
    max_replicas = Column(Integer, nullable=False, default=10)
    current_replicas = Column(Integer, nullable=False, default=0)
    ready_replicas = Column(Integer, nullable=False, default=0)
    api_token = Column(String(128), nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
