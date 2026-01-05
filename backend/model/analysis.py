"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from db.mysql import Base


class TaskAnalysis(Base):
    """
    SQLAlchemy model for storing AI analysis results of a task in the 'test_insights' table.
    """

    __tablename__ = "test_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), nullable=False, unique=True)
    eval_prompt = Column(Text, nullable=False)
    analysis_report = Column(Text, nullable=False)
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AnalysisJob(Base):
    """
    SQLAlchemy model for tracking background analysis jobs.
    """

    __tablename__ = "analysis_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_ids = Column(Text, nullable=False)  # JSON string of task IDs
    analysis_type = Column(Integer, nullable=False)  # 0=single, 1=multiple
    language = Column(String(10), nullable=False, default="en")
    eval_prompt = Column(Text, nullable=True)
    status = Column(
        String(20), nullable=False, default="pending"
    )  # pending, processing, completed, failed
    result_data = Column(Text, nullable=True)  # JSON string of analysis result
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AnalysisRequest(BaseModel):
    """
    Request model for AI analysis (single or multiple tasks).
    """

    task_ids: List[str] = Field(..., description="List of task IDs to analyze")
    eval_prompt: Optional[str] = Field(
        None, description="Custom evaluation prompt for analysis"
    )
    language: Optional[str] = Field("en", description="Language for analysis report")
    background: Optional[bool] = Field(False, description="Process in background")


class AnalysisJobRequest(BaseModel):
    """
    Request model for starting a background analysis job.
    """

    task_ids: List[str] = Field(..., description="List of task IDs to analyze")
    eval_prompt: Optional[str] = Field(
        None, description="Custom evaluation prompt for analysis"
    )
    language: Optional[str] = Field("en", description="Language for analysis report")


class AnalysisResponse(BaseModel):
    """
    Response model for AI analysis.
    """

    task_ids: List[str]
    analysis_report: str
    status: str
    error_message: Optional[str] = None
    created_at: str
    job_id: Optional[str] = Field(
        None, description="Background job ID if processed asynchronously"
    )


class AnalysisJobResponse(BaseModel):
    """
    Response model for background analysis job status.
    """

    job_id: str
    task_ids: List[str]
    status: str
    result_data: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class GetAnalysisResponse(BaseModel):
    """
    Response model for getting AI analysis.
    """

    data: Union[AnalysisResponse, None]
    status: str
    error: Optional[str] = None
