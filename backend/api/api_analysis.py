"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from fastapi import APIRouter, Request

from model.analysis import AnalysisRequest, AnalysisResponse, GetAnalysisResponse
from service.analysis_service import analyze_tasks_svc, get_analysis_svc

# Create an API router for analysis-related endpoints
router = APIRouter()


@router.post("", response_model=AnalysisResponse)
async def analyze_tasks(request: Request, analysis_request: AnalysisRequest):
    """
    Perform AI analysis on task results (single or multiple tasks).

    Args:
        request: The incoming request.
        analysis_request: The analysis request containing task_ids and options.

    Returns:
        AnalysisResponse: The analysis result.

    Raises:
        HTTPException: If the task doesn't exist or analysis fails.
    """

    return await analyze_tasks_svc(request, analysis_request)


@router.get("/{task_id}", response_model=GetAnalysisResponse)
async def get_analysis(request: Request, task_id: str):
    """
    Get analysis result for a task.

    Args:
        request: The incoming request.
        task_id: The task ID.

    Returns:
        GetAnalysisResponse: The analysis result.
    """
    return await get_analysis_svc(request, task_id)
