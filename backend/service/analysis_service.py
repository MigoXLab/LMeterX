"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import re
import ssl
from typing import Any, Dict, List, Optional, Sequence, Union

import httpx  # Add httpx import for async HTTP calls
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from model.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    GetAnalysisResponse,
    TaskAnalysis,
)
from model.task import Task, TaskResult
from service.system_service import get_ai_service_config_internal_svc
from utils.converters import truthy
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger
from utils.prompt import get_analysis_prompt, get_comparison_analysis_prompt

SUPPORTED_ANALYSIS_LANGUAGES = {"en", "zh"}
ANALYSIS_TASK_LIMIT = 10
AI_SERVICE_TIMEOUT_SECONDS = 300.0
DEFAULT_EVAL_PROMPT = "AI analysis prompt"
METRIC_TYPES = (
    "Time_to_first_reasoning_token",
    "Time_to_first_output_token",
    "Total_time",
    "token_metrics",
)


def _resolve_dataset_type(task: Task) -> str:
    if (
        getattr(task, "test_data", None) == "default"
        and getattr(task, "chat_type", None) == 1
    ):
        return "Image-Text Dialogue Dataset"
    return "Text conversation dataset"


def _first_non_empty(*values: Optional[float]) -> Optional[float]:
    for value in values:
        if value is not None:
            return value
    return None


def _validate_task_ids(task_ids: Sequence[str]) -> None:
    if not task_ids:
        raise ErrorResponse.bad_request(
            ErrorMessages.VALIDATION_ERROR,
            details="At least 1 task is required for analysis",
        )
    if len(task_ids) > ANALYSIS_TASK_LIMIT:
        raise ErrorResponse.bad_request(
            ErrorMessages.VALIDATION_ERROR,
            details=f"Maximum {ANALYSIS_TASK_LIMIT} tasks can be analyzed at once",
        )


def _validate_language(language: Optional[str]) -> str:
    if not language:
        return "en"
    normalized = language.lower()
    if normalized not in SUPPORTED_ANALYSIS_LANGUAGES:
        raise ErrorResponse.unprocessable_entity(
            ErrorMessages.INVALID_LANGUAGE,
            details=f"Supported languages: {', '.join(sorted(SUPPORTED_ANALYSIS_LANGUAGES))}",
        )
    return normalized


async def _fetch_task_by_id(db: AsyncSession, task_id: str) -> Optional[Task]:
    task_query = select(Task).where(Task.id == task_id)
    task_result = await db.execute(task_query)
    return task_result.scalar_one_or_none()


async def _fetch_latest_metric_entries(
    db: AsyncSession, task_id: str
) -> Dict[str, TaskResult]:
    metric_query = (
        select(TaskResult)
        .where(
            TaskResult.task_id == task_id,
            TaskResult.metric_type.in_(METRIC_TYPES),
        )
        .order_by(TaskResult.metric_type.asc(), TaskResult.created_at.desc())
    )
    metric_result = await db.execute(metric_query)
    latest_metrics: Dict[str, TaskResult] = {}
    for metric in metric_result.scalars().all():
        metric_type = str(metric.metric_type)
        if metric_type not in latest_metrics:
            latest_metrics[metric_type] = metric
    return latest_metrics


def _build_analysis_prompt_text(
    analysis_type: int,
    language: str,
    model_info: Union[Dict[str, Any], List[Dict[str, Any]]],
) -> str:
    prompt_template = (
        get_analysis_prompt(language)
        if analysis_type == 0
        else get_comparison_analysis_prompt(language)
    )

    try:
        model_info_str = json.dumps(model_info, ensure_ascii=False, indent=2)
    except (TypeError, ValueError) as serialization_error:
        logger.error("Failed to serialize model_info: {}", serialization_error)
        try:
            model_info_str = str(model_info)
        except Exception as fallback_error:  # pragma: no cover - unexpected
            logger.error("Fallback serialization failed: {}", fallback_error)
            raise ErrorResponse.bad_request(
                ErrorMessages.VALIDATION_ERROR,
                details=(
                    "Failed to serialize model_info for prompt generation. "
                    f"Original error: {serialization_error}; fallback error: {fallback_error}"
                ),
            ) from fallback_error

    try:
        return prompt_template.format(model_info=model_info_str)
    except Exception as format_error:
        logger.error("Prompt formatting error: {}", format_error)
        raise ErrorResponse.internal_server_error(
            error="Failed to format analysis prompt",
            details=str(format_error),
        ) from format_error


async def _persist_single_task_analysis(
    db: AsyncSession, task_id: str, analysis_report: str, eval_prompt: Optional[str]
) -> str:
    eval_prompt_value = eval_prompt or DEFAULT_EVAL_PROMPT

    existing_analysis_query = select(TaskAnalysis).where(
        TaskAnalysis.task_id == task_id
    )
    existing_analysis_result = await db.execute(existing_analysis_query)
    existing_analysis = existing_analysis_result.scalar_one_or_none()

    if existing_analysis:
        update_stmt = (
            update(TaskAnalysis)
            .where(TaskAnalysis.task_id == task_id)
            .values(
                eval_prompt=eval_prompt_value,
                analysis_report=analysis_report,
                status="completed",
                error_message=None,
            )
        )
        await db.execute(update_stmt)
        await db.commit()
        await db.refresh(existing_analysis)
        return (
            existing_analysis.created_at.isoformat()
            if existing_analysis.created_at
            else ""
        )

    logger.info("Creating new analysis for task {}", task_id)
    analysis = TaskAnalysis(
        task_id=task_id,
        eval_prompt=eval_prompt_value,
        analysis_report=analysis_report,
        status="completed",
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis.created_at.isoformat() if analysis.created_at else ""


async def _build_model_info_payload(
    db: AsyncSession, task_ids: Sequence[str], analysis_type: int
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    if analysis_type == 0:
        task_id = task_ids[0]
        model_info = await extract_task_metrics(db, task_id)
        if not model_info:
            raise ErrorResponse.not_found(
                ErrorMessages.TASK_NO_RESULTS,
                details=f"No valid task results found for task {task_id}",
            )
        return model_info

    metrics = await extract_multiple_task_metrics(db, list(task_ids))
    if not metrics:
        raise ErrorResponse.not_found(
            ErrorMessages.TASK_NO_RESULTS,
            details="No valid task results found for analysis",
        )
    return metrics


async def extract_task_metrics(
    db, task_id: str, task: Optional[Task] = None
) -> Optional[Dict]:
    """
    Extract key metrics from TaskResult for a single task.
    Used by both single task analysis and task comparison.

    Args:
        db: Database session
        task_id: Task ID to extract metrics for
        task: Optional Task object (if already fetched)

    Returns:
        Dictionary containing extracted metrics or None if task not found/no results
    """
    try:
        if not task:
            task = await _fetch_task_by_id(db, task_id)

        if not task:
            return None

        metrics_map = await _fetch_latest_metric_entries(db, task_id)

        metrics_data = {}

        # Handle First Token Latency (TTFT)
        # Check both reasoning and output token metrics
        ttft_val = None
        ttft_reasoning = metrics_map.get("Time_to_first_reasoning_token")
        if (
            ttft_reasoning
            and ttft_reasoning.avg_latency
            and float(ttft_reasoning.avg_latency) > 0
        ):
            ttft_val = float(ttft_reasoning.avg_latency) / 1000.0

        if ttft_val is None:
            ttft_output = metrics_map.get("Time_to_first_output_token")
            if (
                ttft_output
                and ttft_output.avg_latency
                and float(ttft_output.avg_latency) > 0
            ):
                ttft_val = float(ttft_output.avg_latency) / 1000.0

        if ttft_val is not None:
            metrics_data["first_token_latency"] = ttft_val

        # Handle Total Time
        total_time_data = metrics_map.get("Total_time")
        if (
            total_time_data
            and total_time_data.avg_latency
            and float(total_time_data.avg_latency) > 0
        ):
            metrics_data["total_time"] = float(total_time_data.avg_latency) / 1000.0

        # Handle RPS
        rps_val = None
        # Check Total_time first
        if total_time_data and getattr(total_time_data, "rps", None):
            val = float(total_time_data.rps)
            if val > 0:
                rps_val = val

        # Fallback to Time_to_first_output_token if RPS is still None
        if rps_val is None:
            ttft_output = metrics_map.get("Time_to_first_output_token")
            if ttft_output and getattr(ttft_output, "rps", None):
                val = float(ttft_output.rps)
                if val > 0:
                    rps_val = val

        if rps_val is not None:
            metrics_data["rps"] = rps_val

        # Handle Token Metrics
        token_data = metrics_map.get("token_metrics")
        if token_data:
            total_tps = float(token_data.total_tps or 0.0)
            completion_tps = float(token_data.completion_tps or 0.0)
            avg_total = float(token_data.avg_total_tokens_per_req or 0.0)
            avg_completion = float(token_data.avg_completion_tokens_per_req or 0.0)

            if total_tps > 0:
                metrics_data["total_tps"] = total_tps
            if completion_tps > 0:
                metrics_data["completion_tps"] = completion_tps
            if avg_total > 0:
                metrics_data["avg_total_tokens_per_req"] = avg_total
            if avg_completion > 0:
                metrics_data["avg_completion_tokens_per_req"] = avg_completion

        dataset_type = _resolve_dataset_type(task)

        return {
            "task_id": task_id,
            "task_name": getattr(task, "name", f"Task {task_id}"),
            "model_name": getattr(task, "model", ""),
            "concurrent_users": getattr(task, "concurrent_users", 0),
            "duration": f"{getattr(task, 'duration', 0)}s",
            "stream_mode": truthy(getattr(task, "stream_mode", False)),
            "dataset_type": dataset_type,
            **metrics_data,
        }

    except Exception as e:
        logger.error(
            f"Failed to extract metrics for task {task_id}: {str(e)}",
            exc_info=True,
        )
        return None


async def extract_multiple_task_metrics(db, task_ids: List[str]) -> List[Dict]:
    """
    Extract key metrics for multiple tasks.
    Used by task comparison functionality.

    Args:
        db: Database session
        task_ids: List of task IDs to extract metrics for

    Returns:
        List of dictionaries containing extracted metrics
    """
    metrics_list = []

    # Get all tasks in one query for efficiency
    task_query = select(Task).where(Task.id.in_(task_ids))
    task_result = await db.execute(task_query)
    tasks = {task.id: task for task in task_result.scalars().all()}

    for task_id in task_ids:
        task = tasks.get(task_id)
        if task:
            metrics = await extract_task_metrics(db, task_id, task)
            if metrics:
                metrics_list.append(metrics)

    return metrics_list


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
    if not model_info:
        error_msg = "model_info is required for task analysis"
        raise ErrorResponse.bad_request(
            ErrorMessages.VALIDATION_ERROR, details=error_msg
        )

    prompt = _build_analysis_prompt_text(type, language, model_info)
    url = f"{host}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

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
        timeout = httpx.Timeout(AI_SERVICE_TIMEOUT_SECONDS)
        # Use verify=False to skip SSL certificate verification for self-signed certificates
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            response = await client.post(
                url,
                headers=headers,
                json=data,  # Use json parameter instead of data with json.dumps
            )
            response.raise_for_status()

        response_data = response.json()
        choices = response_data.get("choices") or []
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if content:
                # Remove thinking content wrapped in <think> tags
                # This handles models with reasoning mode that include thinking process
                content = re.sub(
                    r"<think>.*?</think>",
                    "",
                    content,
                    flags=re.DOTALL,
                )
                # Clean up any extra whitespace left after removal
                content = content.strip()
                return content

        error_msg = "Invalid response format from AI service - missing content"
        logger.error("AI service error: {}", error_msg)
        logger.error("AI service response: {}", response_data)
        raise ErrorResponse.internal_server_error(
            error="Invalid AI service response format",
            details=error_msg,
            extra={"response": response_data},
        )

    except ssl.SSLError as e:
        error_msg = f"AI service SSL error: {str(e)}"
        logger.error("AI service SSL error: {}", error_msg)
        raise ErrorResponse.internal_server_error(
            error="AI service SSL certificate verification failed",
            details=error_msg,
        )
    except httpx.TimeoutException as e:
        error_msg = f"AI service request timeout: {str(e)}"
        logger.error("AI service timeout error: {}", error_msg)
        raise ErrorResponse.internal_server_error(
            error="AI service request timeout",
            details=error_msg,
        )
    except httpx.ConnectError as e:
        error_msg = f"AI service connection error: {str(e)}"
        logger.error("AI service connection error: {}", error_msg)
        raise ErrorResponse.internal_server_error(
            error="AI service connection error",
            details=error_msg,
        )
    except httpx.HTTPStatusError as e:
        error_msg = f"AI service HTTP error: {e.response.status_code} - {str(e)}"
        logger.error("AI service HTTP error: {}", error_msg)
        raise ErrorResponse.internal_server_error(
            error="AI service HTTP error",
            details=error_msg,
        )
    except httpx.RequestError as e:
        error_msg = f"AI service request failed: {str(e)}"
        logger.error("AI service request error: {}", error_msg)
        raise ErrorResponse.internal_server_error(
            error="AI service request failed",
            details=error_msg,
        )
    except ErrorResponse:
        raise
    except Exception as e:
        error_msg = f"AI service call failed: {str(e)}"
        logger.error("AI service general error: {}", error_msg)
        raise ErrorResponse.internal_server_error(
            error="AI service call failed",
            details=error_msg,
        )


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

        _validate_task_ids(task_ids)

        # Get AI service configuration from system config
        try:
            ai_config = await get_ai_service_config_internal_svc(request)
        except ErrorResponse:
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

        analysis_type = 0 if len(task_ids) == 1 else 1
        language = _validate_language(analysis_request.language)
        model_info = await _build_model_info_payload(db, task_ids, analysis_type)

        try:
            analysis_report = await _call_ai_service(
                ai_config.host,
                ai_config.model,
                ai_config.api_key,
                type=analysis_type,
                language=language,
                model_info=model_info,
            )

            created_at = ""
            if analysis_type == 0:
                created_at = await _persist_single_task_analysis(
                    db, task_ids[0], analysis_report, analysis_request.eval_prompt
                )

            return AnalysisResponse(
                task_ids=task_ids,
                analysis_report=analysis_report,
                status="completed",
                error_message=None,
                created_at=created_at,
                job_id=None,
            )

        except ErrorResponse:
            raise
        except Exception as ai_error:
            error_message = f"AI analysis failed for tasks {task_ids}: {str(ai_error)}"
            logger.error(error_message, exc_info=True)
            raise ErrorResponse.internal_server_error(
                error="AI analysis failed",
                details=error_message,
            )

    except ErrorResponse:
        raise
    except Exception as e:
        error_message = (
            f"Analysis failed for tasks {analysis_request.task_ids}: {str(e)}"
        )
        logger.error(error_message, exc_info=True)
        raise ErrorResponse.internal_server_error(
            error="Analysis failed due to internal error",
            details=error_message,
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
            # Gracefully return empty result instead of 404 to avoid noisy errors on UI load
            return GetAnalysisResponse(
                data=None,
                status="not_found",
                error=ErrorMessages.ANALYSIS_NOT_FOUND,
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

    except ErrorResponse:
        raise
    except Exception as e:
        error_msg = f"Failed to retrieve analysis for task {task_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise ErrorResponse.internal_server_error(
            error="Failed to retrieve analysis result",
            details=error_msg,
        )
