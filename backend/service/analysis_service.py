"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
from typing import Any, Dict, List, Optional, Union

import httpx  # Add httpx import for async HTTP calls
import requests
from fastapi import HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, PendingRollbackError
from sqlalchemy.ext.asyncio import AsyncSession

from model.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    GetAnalysisResponse,
    TaskAnalysis,
)
from model.task import Task, TaskResult
from service.system_service import get_ai_service_config_internal_svc
from service.task_service import get_task_result_svc
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger


async def analyze_tasks_svc(
    request: Request, analysis_request: AnalysisRequest
) -> AnalysisResponse:
    """
    Perform AI analysis on task results (single or multiple tasks).

    Args:
        request: The incoming request.
        analysis_request: The analysis request containing task_ids and options.

    Returns:
        AnalysisResponse: The analysis result.
    """
    try:
        db: AsyncSession = request.state.db
        task_ids = analysis_request.task_ids

        if len(task_ids) < 1:
            return AnalysisResponse(
                task_ids=[],
                analysis_report="",
                status="failed",
                error_message="At least 1 task is required for analysis",
                created_at="",
                job_id=None,
            )

        if len(task_ids) > 10:
            return AnalysisResponse(
                task_ids=task_ids,
                analysis_report="",
                status="failed",
                error_message="Maximum 10 tasks can be analyzed at once",
                created_at="",
                job_id=None,
            )

        # Get AI service configuration from system config
        try:
            ai_config = await get_ai_service_config_internal_svc(request)
        except HTTPException as e:
            error_msg = "Failed to get AI service configuration."
            logger.error(error_msg, exc_info=True)
            return AnalysisResponse(
                task_ids=task_ids,
                analysis_report="",
                status="failed",
                error_message=f"{ErrorMessages.MISSING_AI_CONFIG}. Please configure AI service in System Configuration.",
                created_at="",
                job_id=None,
            )

        # Determine analysis type (0=single, 1=multiple)
        analysis_type = 0 if len(task_ids) == 1 else 1

        # Extract metrics for all tasks using shared utility
        from utils.tools import extract_multiple_task_metrics, extract_task_metrics

        model_info: Union[Dict[str, Any], List[Dict[str, Any]], None]

        if analysis_type == 0:
            # Single task analysis
            task_id = task_ids[0]
            model_info = await extract_task_metrics(db, task_id)
            if not model_info:
                return AnalysisResponse(
                    task_ids=task_ids,
                    analysis_report="",
                    status="failed",
                    error_message=f"No valid task results found for task {task_id}",
                    created_at="",
                    job_id=None,
                )
        else:
            # Multiple tasks analysis
            model_info_list: List[Dict[str, Any]] = await extract_multiple_task_metrics(
                db, task_ids
            )
            if not model_info_list:
                return AnalysisResponse(
                    task_ids=task_ids,
                    analysis_report="",
                    status="failed",
                    error_message="No valid task results found for analysis",
                    created_at="",
                    job_id=None,
                )
            model_info = model_info_list

        # Call AI service for analysis
        try:
            analysis_report = await _call_ai_service(
                ai_config.host,
                ai_config.model,
                ai_config.api_key,
                type=analysis_type,
                language=analysis_request.language or "en",
                model_info=model_info,
            )

            # For single task analysis, store in database
            if analysis_type == 0:
                task_id = task_ids[0]
                # Check if analysis already exists for this task
                existing_analysis_query = select(TaskAnalysis).where(
                    TaskAnalysis.task_id == task_id
                )
                existing_analysis_result = await db.execute(existing_analysis_query)
                existing_analysis = existing_analysis_result.scalar_one_or_none()

                if existing_analysis:
                    # Update existing analysis
                    logger.debug(f"Updating existing analysis for task {task_id}")
                    update_stmt = (
                        update(TaskAnalysis)
                        .where(TaskAnalysis.task_id == task_id)
                        .values(
                            eval_prompt=analysis_request.eval_prompt
                            or "AI analysis prompt",
                            analysis_report=analysis_report,
                            status="completed",
                            error_message=None,
                        )
                    )
                    await db.execute(update_stmt)
                    await db.commit()

                    # Refresh the existing analysis object
                    await db.refresh(existing_analysis)
                    analysis = existing_analysis
                else:
                    # Create new analysis
                    logger.debug(f"Creating new analysis for task {task_id}")
                    analysis = TaskAnalysis(
                        task_id=task_id,
                        eval_prompt=analysis_request.eval_prompt
                        or "AI analysis prompt",
                        analysis_report=analysis_report,
                        status="completed",
                    )
                    db.add(analysis)
                    await db.commit()
                    await db.refresh(analysis)

                created_at = (
                    analysis.created_at.isoformat() if analysis.created_at else ""
                )
            else:
                # For multiple tasks analysis, don't store in database
                created_at = ""

            return AnalysisResponse(
                task_ids=task_ids,
                analysis_report=analysis_report,
                status="completed",
                error_message=None,
                created_at=created_at,
                job_id=None,
            )

        except Exception as ai_error:
            # Handle AI service errors - only log error, don't update database
            error_message = f"AI analysis failed for tasks {task_ids}: {str(ai_error)}"
            logger.error(error_message, exc_info=True)
            return AnalysisResponse(
                task_ids=task_ids,
                analysis_report="",
                status="failed",
                error_message="AI analysis failed. Please check the AI service configuration and try again.",
                created_at="",
                job_id=None,
            )

    except Exception as e:
        # Handle other exceptions - only log error, don't update database
        error_message = (
            f"Analysis failed for tasks {analysis_request.task_ids}: {str(e)}"
        )
        logger.error(error_message, exc_info=True)
        return AnalysisResponse(
            task_ids=analysis_request.task_ids,
            analysis_report="",
            status="failed",
            error_message="Analysis failed due to internal error. Please try again later.",
            created_at="",
            job_id=None,
        )


async def get_analysis_svc(request: Request, task_id: str) -> GetAnalysisResponse:
    """
    Get analysis result for a task.

    Args:
        request: The incoming request.
        task_id: The task ID.

    Returns:
        GetAnalysisResponse: The analysis result.
    """
    try:
        db: AsyncSession = request.state.db

        # Check if analysis exists
        analysis_query = select(TaskAnalysis).where(TaskAnalysis.task_id == task_id)
        analysis_result = await db.execute(analysis_query)
        analysis = analysis_result.scalar_one_or_none()

        if not analysis:
            # logger.warning(f"Analysis not found for task: {task_id}")
            return GetAnalysisResponse(
                data=None,
                status="not_found",
                error="Analysis not found for this task",
            )

        return GetAnalysisResponse(
            data=AnalysisResponse(
                task_ids=(
                    [str(analysis.task_id)] if analysis.task_id is not None else []
                ),
                analysis_report=(
                    str(analysis.analysis_report)
                    if analysis.analysis_report is not None
                    else ""
                ),
                status=str(analysis.status) if analysis.status is not None else "",
                error_message=(
                    str(analysis.error_message)
                    if analysis.error_message is not None
                    else None
                ),
                created_at=(
                    analysis.created_at.isoformat() if analysis.created_at else ""
                ),
                job_id=None,
            ),
            status="success",
            error=None,
        )

    except Exception as e:
        error_msg = f"Failed to retrieve analysis for task {task_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return GetAnalysisResponse(
            data=None,
            status="error",
            error="Failed to retrieve analysis result",
        )


async def _call_ai_service(
    host: str,
    model: str,
    api_key: str,
    type: int = 0,
    language: str = "en",
    model_info=None,
) -> str:
    """
    Call AI service for analysis using async HTTP client.

    Args:
        host: The AI service host URL.
        model: The AI model name.
        api_key: The API key for authentication.
        type: Analysis type (0=single task, 1=multiple tasks).
        language: The language for analysis prompt (en/zh).
        model_info: Dict (single task) or List[Dict] (multiple tasks) containing model info.

    Returns:
        str: The analysis content.

    Raises:
        Exception: If the AI service call fails.
    """
    url = f"{host}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    from utils.prompt import get_analysis_prompt, get_comparison_analysis_prompt

    # Select prompt template based on type and language
    if type == 0:  # Single task analysis
        prompt_template = get_analysis_prompt(language)
    else:  # Multiple tasks analysis
        prompt_template = get_comparison_analysis_prompt(language)

    if model_info:
        try:
            # Serialize model_info to JSON string
            model_info_str = json.dumps(model_info, ensure_ascii=False, indent=2)
            prompt = prompt_template.format(model_info=model_info_str)
        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize model_info: {}", e)
            # Try fallback serialization
            try:
                model_info_str = str(model_info)
                prompt = prompt_template.format(model_info=model_info_str)
            except Exception as fallback_error:
                logger.error("Fallback serialization failed: {}", fallback_error)
                raise Exception(f"Failed to serialize model_info: {str(e)}")
        except Exception as format_error:
            logger.error("Prompt formatting error: {}", format_error)
            raise Exception(f"Failed to format prompt: {str(format_error)}")
    else:
        error_msg = "model_info is required for task analysis"
        raise ValueError(error_msg)

    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
    }

    try:
        # Use async HTTP client instead of synchronous requests
        timeout = httpx.Timeout(300.0)  # 5 minutes timeout
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=data,  # Use json parameter instead of data with json.dumps
            )
            response.raise_for_status()

        response_data = response.json()
        if "choices" in response_data and len(response_data["choices"]) > 0:
            content = response_data["choices"][0]["message"]["content"]
            return content
        else:
            error_msg = "Invalid response format from AI service - missing content"
            logger.error("AI service error: {}", error_msg)
            logger.error("AI service response: {}", response_data)
            raise Exception(error_msg)

    except httpx.TimeoutException as e:
        error_msg = f"AI service request timeout: {str(e)}"
        logger.error("AI service timeout error: {}", error_msg)
        raise Exception(error_msg)
    except httpx.ConnectError as e:
        error_msg = f"AI service connection error: {str(e)}"
        logger.error("AI service connection error: {}", error_msg)
        raise Exception(error_msg)
    except httpx.HTTPStatusError as e:
        error_msg = f"AI service HTTP error: {e.response.status_code} - {str(e)}"
        logger.error("AI service HTTP error: {}", error_msg)
        raise Exception(error_msg)
    except httpx.RequestError as e:
        error_msg = f"AI service request failed: {str(e)}"
        logger.error("AI service request error: {}", error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"AI service call failed: {str(e)}"
        logger.error("AI service general error: {}", error_msg)
        raise Exception(error_msg)
