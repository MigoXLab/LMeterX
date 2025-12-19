"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import asyncio
import json
import os
import ssl
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import httpx
from fastapi import Query, Request
from sqlalchemy import func, or_, select, text
from starlette.responses import JSONResponse

from model.common_task import CommonTask
from model.task import (
    ComparisonMetrics,
    ComparisonRequest,
    ComparisonResponse,
    ModelTaskInfo,
    ModelTasksResponse,
    Pagination,
    Task,
    TaskCreateReq,
    TaskCreateRsp,
    TaskResponse,
    TaskResult,
    TaskResultItem,
    TaskResultRsp,
    TaskStatusRsp,
)
from service.analysis_service import extract_multiple_task_metrics
from utils.be_config import UPLOAD_FOLDER
from utils.converters import (
    dict_to_kv_list,
    enforce_collection_limit,
    kv_items_to_dict,
    safe_isoformat,
    safe_json_loads,
    truthy,
)
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger

# Testing configuration
MAX_DURATION_FOR_TESTING = 120  # max duration to wait for testing

MAX_HEADER_ITEMS = 20
MAX_COOKIE_ITEMS = 20
DEFAULT_API_TYPE = "openai-chat"
AUTO_FIELD_MAPPING_APIS = {"openai-chat", "claude-chat"}


def _build_task_summary(task: Task) -> Dict[str, Any]:
    field_mapping_dict = safe_json_loads(
        task.field_mapping, f"field_mapping for task {task.id}", {}
    )
    return {
        "id": task.id,
        "name": task.name,
        "status": task.status,
        "target_host": task.target_host,
        "api_path": task.api_path,
        "model": task.model,
        "request_payload": task.request_payload,
        "field_mapping": field_mapping_dict,
        "api_type": task.api_type or DEFAULT_API_TYPE,
        "concurrent_users": task.concurrent_users,
        "duration": task.duration,
        "spawn_rate": task.spawn_rate,
        "chat_type": task.chat_type,
        "stream_mode": truthy(task.stream_mode),
        "headers": "",
        "cookies": "",
        "cert_config": "",
        "test_data": task.test_data or "",
        "created_at": safe_isoformat(task.created_at),
        "updated_at": safe_isoformat(task.updated_at),
    }


def _build_task_detail(task: Task) -> Dict[str, Any]:
    headers_dict = safe_json_loads(task.headers, f"headers for task {task.id}", {})
    cookies_dict = safe_json_loads(task.cookies, f"cookies for task {task.id}", {})
    field_mapping_dict = safe_json_loads(
        task.field_mapping, f"field_mapping for task {task.id}", {}
    )

    return {
        "id": task.id,
        "name": task.name,
        "status": task.status,
        "target_host": task.target_host,
        "model": task.model,
        "duration": task.duration,
        "concurrent_users": task.concurrent_users,
        "spawn_rate": task.spawn_rate,
        "chat_type": task.chat_type,
        "stream_mode": truthy(task.stream_mode),
        "headers": dict_to_kv_list(headers_dict),
        "cookies": dict_to_kv_list(cookies_dict),
        "cert_config": {"cert_file": task.cert_file, "key_file": task.key_file},
        "api_path": task.api_path,
        "request_payload": task.request_payload,
        "field_mapping": field_mapping_dict,
        "api_type": task.api_type or DEFAULT_API_TYPE,
        "test_data": task.test_data or "",
        "error_message": task.error_message,
        "created_at": safe_isoformat(task.created_at),
        "updated_at": safe_isoformat(task.updated_at),
    }


def _build_common_task_detail(task: CommonTask) -> Dict[str, Any]:
    """Build a task-like payload for common API tasks so shared pages work."""
    return {
        "id": task.id,
        "name": task.name,
        "status": task.status,
        "target_host": task.target_host,
        "api_path": task.api_path,
        "model": task.method,  # reuse method label for display
        "duration": task.duration,
        "concurrent_users": task.concurrent_users,
        "spawn_rate": task.spawn_rate,
        "chat_type": 0,
        "stream_mode": False,
        "headers": [],
        "cookies": [],
        "cert_config": {"cert_file": "", "key_file": ""},
        "api_path": getattr(task, "api_path", ""),
        "request_payload": task.request_body or "",
        "field_mapping": {},
        "api_type": "common-api",
        "test_data": task.request_body or "",
        "error_message": task.error_message,
        "created_at": safe_isoformat(task.created_at),
        "updated_at": safe_isoformat(task.updated_at),
    }


def _get_cert_config(body: TaskCreateReq) -> Tuple[str, str]:
    """
    Get certificate configuration from the request body.

    Args:
        body: The task creation request body

    Returns:
        A tuple of (cert_file, key_file) absolute paths
    """
    cert_file = ""
    key_file = ""

    if body.cert_config:
        cert_file = body.cert_config.cert_file or ""
        key_file = body.cert_config.key_file or ""
    else:
        # Try to get certificate configuration from upload service
        from service.upload_service import get_task_cert_config

        cert_config = get_task_cert_config(body.temp_task_id)
        cert_file = cert_config.get("cert_file", "")
        key_file = cert_config.get("key_file", "")

    return cert_file, key_file


async def _is_task_exist(request: Request, task_id: str) -> bool:
    """
    Checks if a task with the given ID exists in the database efficiently.

    Args:
        request: The FastAPI request object.
        task_id: The ID of the task to check.

    Returns:
        True if the task exists, False otherwise.
    """
    try:
        db = request.state.db
        query = select(Task.id).where(Task.id == task_id)
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(
            "Failed to query for task existence (id={}): {}",
            task_id,
            e,
            exc_info=True,
        )
        return False


async def get_tasks_svc(
    request: Request,
    page: int = Query(1, ge=1, alias="page"),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Retrieves a paginated list of tasks from the database, with optional filtering.

    Args:
        request: The FastAPI request object, used to access the database session.
        page: The page number for pagination.
        page_size: The number of items per page.
        status: An optional filter to get tasks with a specific status.
                Can be a single status or comma-separated multiple statuses.
        search: An optional search term to filter tasks by name or ID.

    Returns:
        A `TaskResponse` object containing the list of tasks and pagination details.
    """
    task_list: List[Dict] = []
    pagination = Pagination()
    try:
        db = request.state.db
        # Base query to select tasks.
        query = select(Task)

        # Apply filters if provided.
        if status:
            # Handle multiple statuses separated by comma
            status_list = [s.strip() for s in status.split(",") if s.strip()]
            if len(status_list) == 1:
                query = query.where(Task.status == status_list[0])
            else:
                query = query.where(Task.status.in_(status_list))
        if search:
            query = query.where(
                or_(
                    Task.name.ilike(f"%{search}%"),
                    Task.id.ilike(f"%{search}%"),
                    Task.model.ilike(f"%{search}%"),
                )
            )

        # Get the total count of records matching the filters for pagination.
        total_count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(total_count_query)

        # Apply ordering and pagination to the main query.
        query = query.order_by(Task.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # Execute the query.
        result = await db.execute(query)
        tasks = result.scalars().all()

        # Build pagination metadata.
        pagination = Pagination(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(
                (total + page_size - 1) // page_size if total is not None else 0
            ),
        )

        # Format the task data for the response.
        task_list = [_build_task_summary(task) for task in tasks]
    except Exception as e:
        logger.error("Error getting tasks: {}", e, exc_info=True)
        return TaskResponse(data=[], pagination=Pagination(), status="error")

    return TaskResponse(data=task_list, pagination=pagination, status="success")


async def get_tasks_status_svc(request: Request, page_size: int):
    """
    Retrieves the status of the most recent tasks.

    Args:
        request: The FastAPI request object.
        page_size: The maximum number of task statuses to retrieve.

    Returns:
        A `TaskStatusRsp` object with a list of statuses and a timestamp.
    """
    query = text(
        """
        SELECT id, status, UNIX_TIMESTAMP(updated_at) as updated_timestamp
        FROM tasks
        WHERE updated_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )
    status_list = []
    db = request.state.db
    try:
        result = await db.execute(query, {"limit": page_size})
        status_list = result.mappings().all()
    except Exception as e:
        logger.error("Error getting tasks status: {}", e, exc_info=True)

    return TaskStatusRsp(data=status_list, timestamp=int(time.time()), status="success")


async def stop_task_svc(request: Request, task_id: str):
    """
    Stops a running task by setting its status to 'stopping'.

    Args:
        request: The FastAPI request object.
        task_id: The ID of the task to stop.

    Returns:
        A `TaskCreateRsp` indicating the result of the stop request.
    """
    try:
        db = request.state.db
        task = await db.get(Task, task_id)
        if not task:
            logger.warning("Stop request for non-existent task ID: {}", task_id)
            return TaskCreateRsp(
                status="unknown", task_id=task_id, message="Task not found"
            )

        if task.status != "running":
            return TaskCreateRsp(
                status=task.status,
                task_id=task_id,
                message="Task is not currently running.",
            )
        task.status = "stopping"
        await db.commit()
        return TaskCreateRsp(
            status="stopping", task_id=task_id, message="Task is being stopped."
        )
    except Exception as e:
        logger.error("Failed to stop task {}: {}", task_id, e, exc_info=True)
        return TaskCreateRsp(
            status="error", task_id=task_id, message="Failed to stop task."
        )


async def create_task_svc(request: Request, body: TaskCreateReq):
    """
    Creates a new performance testing task and saves it to the database.
    """
    task_id = str(uuid.uuid4())
    logger.info("Creating task '{}' with ID: {}", body.name, task_id)
    if body.model and len(body.model) > 255:
        raise ErrorResponse.bad_request("Model name must be less than 255 characters")

    cert_file, key_file = _get_cert_config(body)

    try:
        enforce_collection_limit(
            body.headers, MAX_HEADER_ITEMS, ErrorMessages.HEADERS_LIMIT_EXCEEDED
        )
        enforce_collection_limit(
            body.cookies, MAX_COOKIE_ITEMS, ErrorMessages.COOKIES_LIMIT_EXCEEDED
        )
    except ValueError as exc:
        raise ErrorResponse.bad_request(str(exc))

    headers_json = json.dumps(kv_items_to_dict(body.headers))
    cookies_json = json.dumps(kv_items_to_dict(body.cookies))

    test_data = body.test_data or ""

    request_payload_dict = _prepare_request_payload(body)
    request_payload = json.dumps(request_payload_dict)

    db = request.state.db
    try:
        # Convert field_mapping to JSON string if provided
        # For standard chat APIs (openai-chat, claude-chat), empty field_mapping is acceptable
        # as st_engine will auto-generate it based on api_type
        api_type = body.api_type or DEFAULT_API_TYPE
        field_mapping_data = body.field_mapping or {}
        field_mapping_json = json.dumps(field_mapping_data)

        if not field_mapping_data and api_type not in AUTO_FIELD_MAPPING_APIS:
            # For custom-chat and embeddings, field_mapping should be provided
            logger.warning(
                "Creating task with api_type '{}' but no field_mapping provided",
                api_type,
            )

        # Create a new Task ORM instance.
        new_task = Task(
            id=task_id,
            name=body.name,
            target_host=body.target_host,
            model=body.model,
            duration=body.duration,
            concurrent_users=body.concurrent_users,
            spawn_rate=body.spawn_rate if body.spawn_rate else body.concurrent_users,
            chat_type=body.chat_type,
            stream_mode=str(body.stream_mode),
            headers=headers_json,
            cookies=cookies_json,
            status="created",
            error_message="",
            cert_file=cert_file,
            key_file=key_file,
            api_path=body.api_path,
            request_payload=request_payload,
            field_mapping=field_mapping_json,
            api_type=api_type,
            test_data=test_data,
        )

        db.add(new_task)
        await db.flush()
        await db.commit()
        logger.info("Task created successfully: {}", new_task.id)

        return TaskCreateRsp(
            task_id=str(new_task.id),
            status="created",
            message="Task created successfully",
        )
    except Exception as e:
        await db.rollback()
        error_msg = "Failed to create task in database"
        logger.error("Failed to create task in database: {}", e, exc_info=True)
        raise ErrorResponse.internal_server_error(error_msg)


async def get_task_result_svc(request: Request, task_id: str):
    """
    Retrieves the performance test results for a specific task.

    Args:
        request: The FastAPI request object.
        task_id: The ID of the task whose results are to be fetched.

    Returns:
        A `TaskResultRsp` object containing the results or an error message.
    """
    if not task_id:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_ID_MISSING)
    if not await _is_task_exist(request, task_id):
        logger.warning("Attempted to get results for non-existent task: {}", task_id)
        return TaskResultRsp(error="Task not found", status="not_found", results=[])

    query_task_result = (
        select(TaskResult)
        .where(TaskResult.task_id == task_id)
        .order_by(TaskResult.created_at.asc())
    )
    result = await request.state.db.execute(query_task_result)
    task_results = result.scalars().all()

    if not task_results:
        return TaskResultRsp(
            error="No test results found for this task",
            status="not_found",
            results=[],
        )

    result_items = [task_result.to_task_result_item() for task_result in task_results]
    return TaskResultRsp(results=result_items, status="success", error=None)


async def get_task_svc(request: Request, task_id: str):
    """
    Retrieves a single task by its ID.

    Args:
        request: The FastAPI request object.
        task_id: The ID of the task to retrieve.

    Returns:
        The task data as a dictionary on success, or raises ErrorResponse on failure.
    """
    db = request.state.db
    try:
        task = await db.get(Task, task_id)
        if task:
            return _build_task_detail(task)

        # Fallback to common API task to support shared log/detail pages
        common_task = await db.get(CommonTask, task_id)
        if common_task:
            return _build_common_task_detail(common_task)

            logger.warning("Get request for non-existent task ID: {}", task_id)
            raise ErrorResponse.not_found("Task not found")
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to retrieve task {}: {}", task_id, e, exc_info=True)
        raise ErrorResponse.internal_server_error(
            "An internal error occurred while retrieving the task."
        )


async def get_task_status_svc(request: Request, task_id: str):
    """
    Retrieves only the status information of a specific task for lightweight queries.

    Args:
        request: The FastAPI request object.
        task_id: The ID of the task whose status is to be fetched.

    Returns:
        A dictionary containing task status information or raises ErrorResponse on failure.
    """
    db = request.state.db
    try:
        # Query only the necessary fields for status check
        query = select(
            Task.id, Task.name, Task.status, Task.error_message, Task.updated_at
        ).where(Task.id == task_id)
        result = await db.execute(query)
        task_data = result.first()

        if not task_data:
            # Fallback to common task
            common_query = select(
                CommonTask.id,
                CommonTask.name,
                CommonTask.status,
                CommonTask.error_message,
                CommonTask.updated_at,
            ).where(CommonTask.id == task_id)
            common_result = await db.execute(common_query)
            common_data = common_result.first()
            if common_data:
                return {
                    "id": common_data.id,
                    "name": common_data.name,
                    "status": common_data.status,
                    "error_message": common_data.error_message,
                    "updated_at": safe_isoformat(common_data.updated_at),
                }

            logger.warning("Status request for non-existent task ID: {}", task_id)
            raise ErrorResponse.not_found("Task not found")

        # Return lightweight status information
        status_dict = {
            "id": task_data.id,
            "name": task_data.name,
            "status": task_data.status,
            "error_message": task_data.error_message,
            "updated_at": safe_isoformat(task_data.updated_at),
        }
        return status_dict
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to retrieve task status {}: {}", task_id, e, exc_info=True)
        raise ErrorResponse.internal_server_error(
            "An internal error occurred while retrieving the task status."
        )


async def get_model_tasks_for_comparison_svc(request: Request):
    """
    Get available model tasks that can be used for performance comparison.
    Only returns tasks with status 'completed' or 'failed_requests' that have results.

    Args:
        request: The FastAPI request object.

    Returns:
        ModelTasksResponse: A response containing available model tasks.
    """
    try:
        db = request.state.db

        # Query for completed and failed_requests tasks that have results
        query = (
            select(
                Task.id,
                Task.name,
                Task.model,
                Task.concurrent_users,
                Task.created_at,
                Task.duration,
            )
            .where(Task.status.in_(["completed", "failed_requests"]))
            .join(TaskResult, Task.id == TaskResult.task_id)
            .distinct()
            .order_by(Task.created_at.desc(), Task.model, Task.concurrent_users)
        )

        result = await db.execute(query)
        tasks = result.all()

        if not tasks:
            return ModelTasksResponse(data=[], status="success", error=None)

        # Convert to response format
        model_tasks = [
            ModelTaskInfo(
                model_name=task.model,
                concurrent_users=task.concurrent_users,
                task_id=task.id,
                task_name=task.name or f"Task {task.id[:8]}",
                created_at=task.created_at.isoformat() if task.created_at else "",
                duration=task.duration or 0,
            )
            for task in tasks
        ]

        return ModelTasksResponse(data=model_tasks, status="success", error=None)

    except Exception as e:
        logger.error("Failed to get model tasks for comparison: {}", e, exc_info=True)
        raise ErrorResponse.internal_server_error(
            ErrorMessages.MODEL_TASKS_FETCH_FAILED
        )


async def compare_performance_svc(
    request: Request, comparison_request: ComparisonRequest
):
    """
    Compare performance metrics for selected tasks.

    Args:
        request: The FastAPI request object.
        comparison_request: Request containing task IDs to compare.

    Returns:
        ComparisonResponse: A response containing comparison metrics.
    """
    try:
        db = request.state.db
        task_ids = comparison_request.selected_tasks

        if len(task_ids) < 2:
            return ComparisonResponse(
                data=[],
                status="error",
                error="At least 2 tasks are required for comparison",
            )

        if len(task_ids) > 10:
            return ComparisonResponse(
                data=[],
                status="error",
                error="Maximum 10 tasks can be compared at once",
            )

        # Get task information
        task_query = select(Task).where(Task.id.in_(task_ids))
        task_result = await db.execute(task_query)
        tasks = {task.id: task for task in task_result.scalars().all()}

        # Check if all tasks exist and are completed
        missing_tasks = set(task_ids) - set(tasks.keys())
        if missing_tasks:
            return ComparisonResponse(
                data=[],
                status="error",
                error=f"Tasks not found: {', '.join(missing_tasks)}",
            )

        incomplete_tasks = [
            task_id
            for task_id, task in tasks.items()
            if task.status not in ["completed", "failed_requests"]
        ]
        if incomplete_tasks:
            return ComparisonResponse(
                data=[],
                status="error",
                error=f"Only completed tasks can be compared. Incomplete tasks: {', '.join(incomplete_tasks)}",
            )

        # Use the shared utility to extract metrics for all tasks
        metrics_data_list = await extract_multiple_task_metrics(db, task_ids)

        # Log metrics extraction results for debugging
        logger.info(
            "Extracted metrics for {} out of {} tasks",
            len(metrics_data_list),
            len(task_ids),
        )

        # Check if we have any valid metrics
        if not metrics_data_list:
            return ComparisonResponse(
                data=[],
                status="error",
                error="No valid metrics data found for the selected tasks. Please ensure the tasks have completed test results.",
            )

        # Convert to ComparisonMetrics objects
        comparison_metrics = []
        for metrics_data in metrics_data_list:
            if metrics_data:  # Only add valid metrics
                try:
                    metrics = ComparisonMetrics(
                        task_id=metrics_data["task_id"],
                        model_name=metrics_data["model_name"],
                        concurrent_users=metrics_data["concurrent_users"],
                        task_name=metrics_data["task_name"],
                        duration=metrics_data["duration"],
                        stream_mode=metrics_data["stream_mode"],
                        dataset_type=metrics_data["dataset_type"],
                        first_token_latency=metrics_data["first_token_latency"],
                        total_time=metrics_data["total_time"],
                        total_tps=metrics_data["total_tps"],
                        completion_tps=metrics_data["completion_tps"],
                        avg_total_tokens_per_req=metrics_data[
                            "avg_total_tokens_per_req"
                        ],
                        avg_completion_tokens_per_req=metrics_data[
                            "avg_completion_tokens_per_req"
                        ],
                        rps=metrics_data["rps"],
                    )
                    comparison_metrics.append(metrics)
                except Exception as e:
                    logger.error(
                        "Failed to create ComparisonMetrics for task {}: {}",
                        metrics_data.get("task_id", "unknown"),
                        e,
                    )
                    continue

        if not comparison_metrics:
            return ComparisonResponse(
                data=[],
                status="error",
                error="Failed to process metrics data for any of the selected tasks",
            )

        return ComparisonResponse(data=comparison_metrics, status="success", error=None)

    except Exception as e:
        logger.error("Failed to compare performance: {}", e, exc_info=True)
        return ComparisonResponse(
            data=[], status="error", error="Failed to perform performance comparison"
        )


def _prepare_cookies_from_headers(body: TaskCreateReq) -> Dict[str, str]:
    """Prepare cookies from both cookies field and headers for legacy support."""
    cookies = {}

    # Process cookies from the cookies field
    for cookie_item in body.cookies:
        if cookie_item.key and cookie_item.value:
            cookies[cookie_item.key] = cookie_item.value

    # Also check headers for legacy cookie support
    for header in body.headers:
        if header.key and header.value:
            # Check if this is actually a cookie (common patterns)
            if header.key.lower() in ["cookie", "cookies"]:
                # Try to parse as cookie string
                try:
                    if header.value.startswith("{"):
                        # JSON format
                        cookies.update(json.loads(header.value))
                    else:
                        # Cookie string format: "key1=value1; key2=value2"
                        for item in header.value.split(";"):
                            if "=" in item:
                                k, v = item.strip().split("=", 1)
                                cookies[k] = v
                except (json.JSONDecodeError, ValueError):
                    pass
            # Also check for token/auth in headers that should be cookies
            elif header.key.lower() in ["token", "uaa_token", "sso_uid", "ssouid"]:
                cookies[header.key] = header.value

    return cookies


def _prepare_request_payload(body: TaskCreateReq) -> Dict:
    """Prepare request payload based on API path and configuration."""

    # If request_payload is empty or None, generate default
    if not body.request_payload or not body.request_payload.strip():
        # Generate default payload for any API
        default_payload = {
            "model": body.model or "your-model-name",
            "stream": body.stream_mode,
            "messages": [
                {
                    "role": "user",
                    "content": "Hi",
                }
            ],
        }
        return default_payload

    # Use provided request_payload
    try:
        return json.loads(body.request_payload)
    except json.JSONDecodeError as e:
        raise ErrorResponse.bad_request(
            ErrorMessages.REQUEST_PAYLOAD_INVALID,
            details=f"Invalid JSON in request payload: {str(e)}",
            extra={"field": "request_payload"},
        )


def _validate_certificate_files(
    cert_file: str, key_file: Optional[str]
) -> Tuple[bool, str]:
    """
    Validate certificate files.
    """
    try:
        if not cert_file:
            return False, "No certificate file provided"

        def _exists(path: str) -> bool:
            return isinstance(path, str) and len(path) > 0 and os.path.exists(path)

        def _is_pkcs12(path: str) -> bool:
            lower = path.lower()
            return lower.endswith(".p12") or lower.endswith(".pfx")

        def _read(path: str) -> str:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception:
                return ""

        if not _exists(cert_file):
            return False, f"Certificate file does not exist: {cert_file}"
        if _is_pkcs12(cert_file):
            return (
                False,
                "P12/PFX certificates are not supported, please convert to a PEM file containing the private key",
            )

        cert_text = _read(cert_file)
        if "BEGIN CERTIFICATE" not in cert_text:
            return (
                False,
                "Certificate file is not a valid PEM format (missing BEGIN CERTIFICATE)",
            )

        if key_file:
            if not _exists(key_file):
                return False, f"Private key file does not exist: {key_file}"
            if _is_pkcs12(key_file):
                return (
                    False,
                    "Private key file cannot be P12/PFX, please provide a PEM private key",
                )
            key_text = _read(key_file)
            if (
                "BEGIN PRIVATE KEY" not in key_text
                and "BEGIN RSA PRIVATE KEY" not in key_text
                and "BEGIN EC PRIVATE KEY" not in key_text
            ):
                return False, "Private key file is not a valid PEM private key"
        else:
            # 仅提供了一个 cert_file，需同时包含证书+私钥
            if (
                "BEGIN PRIVATE KEY" not in cert_text
                and "BEGIN RSA PRIVATE KEY" not in cert_text
                and "BEGIN EC PRIVATE KEY" not in cert_text
            ):
                return (
                    False,
                    "Only a certificate file was provided, but it does not contain a private key, please upload the private key or provide a merged PEM file",
                )

        return True, ""
    except Exception as e:
        return False, f"Certificate validation error: {str(e)}"


def _prepare_client_cert(body: TaskCreateReq):
    """Prepare SSL certificate configuration for the HTTP client."""
    client_cert: Optional[Union[str, Tuple[str, str]]] = None

    # Get certificate configuration
    cert_file, key_file = _get_cert_config(body)

    # Use absolute paths directly from upload service
    if cert_file or key_file:
        try:
            is_valid, err_msg = _validate_certificate_files(cert_file, key_file or None)
            if not is_valid:
                logger.error("Invalid client certificate configuration: {}", err_msg)
                return None

            if cert_file and key_file:
                # Both cert and key files provided
                client_cert = (cert_file, key_file)
            elif cert_file:
                # Only cert file provided (combined cert+key file)
                client_cert = cert_file
        except Exception as e:
            logger.error("Error preparing certificate configuration: {}", e)
            return None

    return client_cert


async def _handle_non_streaming_response(response) -> Dict:
    """Handle non-streaming response from API endpoint."""
    # Try to parse response as JSON
    try:
        response_data = response.json()
    except Exception:
        response_data = response.text

    return {
        "status": "success" if response.status_code == 200 else "error",
        "response": {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "data": response_data,
            "is_stream": False,
        },
        "error": (
            None
            if response.status_code == 200
            else f"HTTP {response.status_code}. {response.text}"
        ),
    }


async def test_llm_api_svc(request: Request, body: TaskCreateReq):
    """
    Test a custom API endpoint with the provided configuration.

    Args:
        request: The FastAPI request object.
        body: The request body containing the test parameters.

    Returns:
        A dictionary containing the test result.
    """
    try:
        # Prepare headers
        headers = {
            header.key: header.value
            for header in body.headers
            if header.key and header.value
        }

        # Prepare cookies
        cookies = _prepare_cookies_from_headers(body)

        # Prepare request payload
        payload = _prepare_request_payload(body)

        # Build full URL
        full_url = f"{body.target_host.rstrip('/')}{body.api_path}"

        # Prepare certificate configuration
        client_cert = _prepare_client_cert(body)

        # Optimized timeout settings
        timeout_config = httpx.Timeout(
            connect=10.0,  # connect timeout: 10s
            read=30.0,  # read timeout: 30s (for testing purposes, not too long)
            write=10.0,  # write timeout: 10s
            pool=5.0,  # pool timeout: 5s
        )

        # Use connection limits for better performance
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)

        # Test with httpx client - optimized configuration
        async with httpx.AsyncClient(
            timeout=timeout_config, verify=False, cert=client_cert, limits=limits
        ) as client:
            if body.stream_mode:
                # Handle streaming response with early termination
                async with client.stream(
                    "POST", full_url, json=payload, headers=headers, cookies=cookies
                ) as response:
                    return await _handle_streaming_response(response, full_url)
            else:
                # Handle non-streaming response
                response = await client.post(
                    full_url, json=payload, headers=headers, cookies=cookies
                )
                return await _handle_non_streaming_response(response)

    except ssl.SSLError as e:
        msg = str(e)
        hint = ""
        if "PEM lib" in msg or "PEM routines" in msg:
            hint = "Client certificate/private key format error: only PEM is supported. Please upload a PEM file containing the private key, or provide both PEM certificate and PEM private key; P12/PFX is not supported."
        elif "no certificate or crl found" in msg:
            hint = (
                "No valid certificate content found, please confirm the file is correct"
            )
        logger.error("SSL error when testing API endpoint: {}", e)
        return {
            "status": "error",
            "error": f"SSL error: {msg}. {hint}",
            "response": None,
        }
    except httpx.TimeoutException as e:
        logger.error("Request timeout when testing API endpoint.")
        return {
            "status": "error",
            "error": f"Request timeout: {str(e)}",
            "response": None,
        }
    except httpx.ConnectError as e:
        logger.error("Connection error when testing API endpoint.")
        return {
            "status": "error",
            "error": f"Connection error: {str(e)}",
            "response": None,
        }
    except asyncio.TimeoutError:
        logger.error("Asyncio timeout when testing API endpoint")
        return {
            "status": "error",
            "error": "Operation timeout, please check network connection and target server status",
            "response": None,
        }
    except Exception as e:
        logger.error("Error testing API endpoint: {}", e, exc_info=True)
        return {
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "response": None,
        }


async def _handle_streaming_response(
    response,
    full_url: str,
    max_duration: int = MAX_DURATION_FOR_TESTING,
) -> Dict:
    """
    Handle streaming response from API endpoint with optimized performance.
    For testing purposes, we only need to verify connectivity and get initial response.

      Args:
        response: The response object from the API endpoint.
        full_url: The full URL of the API endpoint.
        max_duration: The maximum duration to wait for testing.
    Returns:
        A dictionary containing the streaming response.
    """
    stream_data: List[str] = []
    append_chunk = stream_data.append
    test_note = "Streaming connection test completed, only collected partial data for verification"

    def _build_stream_result(
        note: str, warning: Optional[str] = None
    ) -> Dict[str, Any]:
        test_successful = len(stream_data) > 0
        response_payload: Dict[str, Any] = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "data": stream_data,
            "is_stream": True,
            "test_note": note,
        }
        if warning:
            response_payload["warning"] = warning
        return {
            "status": "success" if test_successful else "error",
            "response": response_payload,
            "error": None if test_successful else "No streaming data received",
        }

    try:
        # If status code is not 200, return error response immediately
        if response.status_code != 200:
            try:
                error_text = await response.aread()
                error_content = error_text.decode("utf-8")
            except Exception:
                error_content = "Unable to read response content"

            try:
                error_data = json.loads(error_content)
            except (json.JSONDecodeError, ValueError):
                error_data = error_content

            return {
                "status": "error",
                "response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "data": error_data,
                    "is_stream": False,
                },
                "error": f"HTTP {response.status_code}. {error_content}",
            }

        # For testing purposes, we limit the time we spend collecting data
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_duration

        # Process streaming data with only time limit
        async for chunk in response.aiter_lines():
            if chunk:
                chunk_str = chunk.strip()
                if chunk_str:
                    append_chunk(chunk_str)

                    # Check if we've spent too much time
                    if loop.time() >= deadline:
                        test_note = (
                            "Streaming connection test completed after reaching the "
                            f"{max_duration}-second limit"
                        )
                        logger.info(
                            f"Stopped streaming test after {max_duration} seconds",
                        )
                        break

        return _build_stream_result(test_note)

    except asyncio.TimeoutError:
        logger.error("Stream processing timeout")
        raise ErrorResponse.internal_server_error(
            ErrorMessages.STREAM_PROCESSING_TIMEOUT
        )
    except Exception as stream_error:
        if stream_data:
            warning_text = str(stream_error).strip() or "Stream closed unexpectedly."
            logger.error(
                f"Stream test ended with error: {warning_text}",
            )
            return _build_stream_result(
                test_note, warning=f"Stream ended early: {warning_text}"
            )

        logger.error(f"Error processing stream: {stream_error}")
        raise ErrorResponse.internal_server_error(ErrorMessages.STREAM_PROCESSING_ERROR)
