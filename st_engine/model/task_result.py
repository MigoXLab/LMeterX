"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Float, Index, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class TaskResult(Base):
    __tablename__ = "task_results"
    __table_args__ = (Index("idx_task_id", "task_id"),)
    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary key ID")
    task_id = Column(String(36), nullable=False, comment="Task ID")
    metric_type = Column(String(36), comment="Metric type")
    num_requests = Column(Integer, default=0, comment="Total number of requests")
    num_failures = Column(Integer, default=0, comment="Number of failed requests")
    avg_latency = Column(Float, default=0, comment="Average response time")
    min_latency = Column(Float, default=0, comment="Minimum response time")
    max_latency = Column(Float, default=0, comment="Maximum response time")
    median_latency = Column(Float, default=0, comment="Median response time")
    p90_latency = Column(Float, default=0, comment="90th percentile response time")
    rps = Column(Float, default=0, comment="Requests per second")
    avg_content_length = Column(
        Float, default=0, comment="Average output character length"
    )
    completion_tps = Column(Float, default=0, comment="Completion tokens per second")
    total_tps = Column(
        Float, default=0, comment="Total tokens per second (input + output)"
    )
    avg_total_tokens_per_req = Column(
        Float, default=0, comment="Average total tokens per request (input + output)"
    )
    avg_completion_tokens_per_req = Column(
        Float, default=0, comment="Average completion tokens per request"
    )

    created_at = Column(DateTime, default=datetime.now(timezone(timedelta(hours=8))))
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone(timedelta(hours=8))),
        onupdate=datetime.now(timezone(timedelta(hours=8))),
    )
