"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from db.mysql import Base


class CommonTask(Base):
    """SQLAlchemy model for common API load test tasks."""

    __tablename__ = "common_tasks"

    id = Column(String(40), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    created_by = Column(String(100), nullable=True)
    method = Column(String(16), nullable=False)
    target_url = Column(String(2000), nullable=False)
    target_host = Column(String(255), nullable=False)
    api_path = Column(String(1024), nullable=False)
    headers = Column(Text, nullable=True)
    cookies = Column(Text, nullable=True)
    request_body = Column(Text, nullable=True)
    dataset_file = Column(Text, nullable=True)
    curl_command = Column(Text, nullable=True)
    stream_mode = Column(String(8), nullable=True)
    concurrent_users = Column(Integer, nullable=False)
    spawn_rate = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    log_file = Column(Text, nullable=True)
    result_file = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CommonTaskResult(Base):
    """SQLAlchemy model for common API task results."""

    __tablename__ = "common_task_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(40), nullable=False)
    metric_type = Column(String(64), nullable=False)
    num_requests = Column(Integer, nullable=False)
    num_failures = Column(Integer, nullable=False)
    avg_latency = Column(Float, nullable=False)
    min_latency = Column(Float, nullable=False)
    max_latency = Column(Float, nullable=False)
    median_latency = Column(Float, nullable=False)
    p90_latency = Column(Float, nullable=False)
    rps = Column(Float, nullable=False)
    avg_content_length = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
