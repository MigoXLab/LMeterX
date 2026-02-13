"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import asyncio
import json
import os
import ssl
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import urlsplit

import httpx

__all__ = [
    "get_common_tasks_svc",
    "get_common_tasks_status_svc",
    "create_common_task_svc",
    "update_common_task_svc",
    "delete_common_task_svc",
    "test_common_api_svc",
    "stop_common_task_svc",
    "get_common_task_result_svc",
    "get_common_task_svc",
    "get_common_task_status_svc",
    "get_common_tasks_for_comparison_svc",
    "compare_common_performance_svc",
    "get_common_task_realtime_metrics_svc",
]

from fastapi import Query, Request
from sqlalchemy import delete, func, or_, select, text

from model.common_task import (
    CommonComparisonMetrics,
    CommonComparisonRequest,
    CommonComparisonResponse,
    CommonComparisonTaskInfo,
    CommonComparisonTasksResponse,
    CommonTask,
    CommonTaskCreateReq,
    CommonTaskCreateRsp,
    CommonTaskPagination,
    CommonTaskRealtimeMetric,
    CommonTaskResponse,
    CommonTaskResult,
    CommonTaskResultRsp,
    CommonTaskStatusRsp,
)
from utils.auth import get_current_user
from utils.auth_settings import get_auth_settings
from utils.converters import kv_items_to_dict, safe_isoformat
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger

settings = get_auth_settings()


def _split_url(target_url: str) -> tuple[str, str]:
    """Split full URL into host and path components."""
    parts = urlsplit(target_url)
    host = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return host, path


def _build_task_summary(task: CommonTask) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "id": task.id,
        "name": task.name,
        "status": task.status,
        "created_by": _resolve_created_by(cast(Optional[str], task.created_by)),
        "method": task.method,
        "target_url": task.target_url,
        "concurrent_users": task.concurrent_users,
        "duration": task.duration,
        "spawn_rate": task.spawn_rate,
        "load_mode": getattr(task, "load_mode", "fixed") or "fixed",
        "created_at": safe_isoformat(task.created_at),
        "updated_at": safe_isoformat(task.updated_at),
    }
    # Include stepped config when in stepped mode
    if summary["load_mode"] == "stepped":
        summary.update(
            {
                "step_start_users": getattr(task, "step_start_users", None),
                "step_increment": getattr(task, "step_increment", None),
                "step_duration": getattr(task, "step_duration", None),
                "step_max_users": getattr(task, "step_max_users", None),
                "step_sustain_duration": getattr(task, "step_sustain_duration", None),
            }
        )
    return summary


def _build_task_detail(task: CommonTask) -> Dict[str, Any]:
    headers = json.loads(str(task.headers or "{}"))
    cookies = json.loads(str(task.cookies or "{}"))
    detail = {
        **_build_task_summary(task),
        "api_path": task.api_path,
        "target_host": task.target_host,
        "headers": [{"key": k, "value": v} for k, v in headers.items()],
        "cookies": [{"key": k, "value": v} for k, v in cookies.items()],
        "request_body": task.request_body or "",
        "dataset_file": task.dataset_file or "",
        "curl_command": task.curl_command or "",
        "error_message": task.error_message or "",
    }
    return detail


def _prepare_request_body(
    request_body: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Try to convert request_body string to JSON; fallback to raw text.

    Returns:
        (json_payload, text_payload)
    """
    if not request_body:
        return None, None
    body = request_body.strip()
    try:
        return json.loads(body), None
    except Exception:
        return None, body


def _get_username_from_request(request: Request) -> str:
    """Extract username from auth payload; returns empty string when unavailable."""
    user = get_current_user(request)
    if isinstance(user, dict):
        return str(user.get("username") or user.get("sub") or "").strip()
    return ""


def _resolve_created_by(value: Optional[str]) -> Optional[str]:
    if settings.LDAP_ENABLED:
        return value
    return value or "-"


async def _is_task_exist(request: Request, task_id: str) -> bool:
    try:
        db = request.state.db
        query = select(CommonTask.id).where(CommonTask.id == task_id)
        result = await db.execute(query)
        return result.scalar_one_or_none() is not None
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error("Failed to query common task existence {}: {}", task_id, e)
        return False


async def get_common_tasks_svc(
    request: Request,
    page: int = Query(1, ge=1, alias="page"),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    status: Optional[str] = None,
    search: Optional[str] = None,
    creator: Optional[str] = None,
) -> CommonTaskResponse:
    tasks_data: List[Dict[str, Any]] = []
    pagination = CommonTaskPagination()
    try:
        db = request.state.db
        # Base query excluding soft-deleted tasks
        query = select(CommonTask).where(CommonTask.is_deleted == 0)

        if status:
            status_list = [s.strip() for s in status.split(",") if s.strip()]
            if len(status_list) == 1:
                query = query.where(CommonTask.status == status_list[0])
            else:
                query = query.where(CommonTask.status.in_(status_list))

        if creator:
            query = query.where(CommonTask.created_by == creator)

        if search:
            query = query.where(
                or_(
                    CommonTask.name.ilike(f"%{search}%"),
                    CommonTask.id.ilike(f"%{search}%"),
                    CommonTask.target_url.ilike(f"%{search}%"),
                    CommonTask.created_by.ilike(f"%{search}%"),
                )
            )

        total_count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(total_count_query)

        query = query.order_by(CommonTask.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        tasks = result.scalars().all()

        pagination = CommonTaskPagination(
            total=total or 0,
            page=page,
            page_size=page_size,
            total_pages=((total or 0) + page_size - 1) // page_size,
        )
        tasks_data = [_build_task_summary(task) for task in tasks]
    except Exception as e:
        logger.error("Error getting common tasks: {}", e, exc_info=True)
        return CommonTaskResponse(
            data=[], pagination=CommonTaskPagination(), status="error"
        )

    return CommonTaskResponse(data=tasks_data, pagination=pagination, status="success")


async def get_common_tasks_status_svc(
    request: Request, page_size: int = Query(50, ge=1, le=100)
) -> CommonTaskStatusRsp:
    query = text(
        """
        SELECT id, status, UNIX_TIMESTAMP(updated_at) as updated_timestamp
        FROM common_tasks
        WHERE updated_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
        AND is_deleted = 0
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
        logger.error("Error getting common task statuses: {}", e, exc_info=True)

    return CommonTaskStatusRsp(
        data=status_list, timestamp=int(time.time()), status="success"
    )


async def create_common_task_svc(
    request: Request, body: CommonTaskCreateReq
) -> CommonTaskCreateRsp:
    task_id = str(uuid.uuid4())
    logger.info("Creating common task '{}' with ID: {}", body.name, task_id)

    target_host, api_path = _split_url(body.target_url)
    spawn_rate = body.spawn_rate or body.concurrent_users

    if body.request_body and len(body.request_body) > 100000:
        raise ErrorResponse.bad_request(
            "Request body exceeds 100000 characters. Please simplify payload or use dataset upload."
        )

    headers_json = json.dumps(kv_items_to_dict(body.headers)) if body.headers else "{}"
    cookies_json = json.dumps(kv_items_to_dict(body.cookies)) if body.cookies else "{}"

    db = request.state.db
    try:
        user = get_current_user(request)
        created_by: Optional[str] = None
        if isinstance(user, dict):
            username = str(user.get("username") or user.get("sub") or "").strip()
            if username:
                created_by = username[:100]
        if not settings.LDAP_ENABLED:
            created_by = created_by or "-"

        load_mode = body.load_mode or "fixed"
        new_task = CommonTask(
            id=task_id,
            name=body.name,
            status="created",
            created_by=created_by,
            method=body.method.upper(),
            target_url=body.target_url,
            target_host=target_host,
            api_path=api_path,
            headers=headers_json,
            cookies=cookies_json,
            request_body=body.request_body or "",
            dataset_file=body.dataset_file or "",
            curl_command=body.curl_command or "",
            concurrent_users=body.concurrent_users,
            spawn_rate=spawn_rate,
            duration=body.duration,
            load_mode=load_mode,
            step_start_users=body.step_start_users if load_mode == "stepped" else None,
            step_increment=body.step_increment if load_mode == "stepped" else None,
            step_duration=body.step_duration if load_mode == "stepped" else None,
            step_max_users=body.step_max_users if load_mode == "stepped" else None,
            step_sustain_duration=(
                body.step_sustain_duration if load_mode == "stepped" else None
            ),
            error_message="",
        )
        db.add(new_task)
        await db.flush()
        await db.commit()
        return CommonTaskCreateRsp(
            task_id=str(new_task.id),
            status="created",
            message="Common task created successfully",
        )
    except Exception as e:
        await db.rollback()
        logger.error("Failed to create common task: {}", e, exc_info=True)
        raise ErrorResponse.internal_server_error("Failed to create common task")


async def update_common_task_svc(
    request: Request, task_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Update mutable fields of a common task (currently supports renaming).
    Only the creator can perform this operation when recorded.
    """
    if not task_id:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_ID_MISSING)

    new_name = str(payload.get("name") or "").strip()
    if not new_name:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_NAME_REQUIRED)
    if len(new_name) > 100:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_NAME_LENGTH_INVALID)

    db = request.state.db
    try:
        task = await db.get(CommonTask, task_id)
        if not task or getattr(task, "is_deleted", 0) == 1:
            raise ErrorResponse.not_found(ErrorMessages.TASK_NOT_FOUND)

        if settings.LDAP_ENABLED:
            username = _get_username_from_request(request)
            # forbidden to update task without created_by
            if not task.created_by:
                raise ErrorResponse.forbidden(ErrorMessages.INSUFFICIENT_PERMISSIONS)
            if task.created_by != username:
                raise ErrorResponse.forbidden(ErrorMessages.INSUFFICIENT_PERMISSIONS)

        task.name = new_name
        await db.commit()
        await db.refresh(task)
        return {"status": "success", "task_id": task_id, "name": task.name}
    except ErrorResponse:
        await db.rollback()
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        await db.rollback()
        logger.error("Failed to update common task {}: {}", task_id, e, exc_info=True)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_UPDATE_FAILED)


async def delete_common_task_svc(request: Request, task_id: str) -> Dict[str, Any]:
    """
    Soft delete a common API task by marking it as deleted. Only the creator can delete.
    The task and its related results will be hidden from queries but remain in the database.
    """
    if not task_id:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_ID_MISSING)

    db = request.state.db
    try:
        task = await db.get(CommonTask, task_id)
        if not task:
            raise ErrorResponse.not_found(ErrorMessages.TASK_NOT_FOUND)

        # Check if task is already deleted
        if getattr(task, "is_deleted", 0) == 1:
            raise ErrorResponse.not_found(ErrorMessages.TASK_NOT_FOUND)

        if settings.LDAP_ENABLED:
            username = _get_username_from_request(request)
            # forbidden to delete task without created_by
            if not task.created_by:
                raise ErrorResponse.forbidden(ErrorMessages.INSUFFICIENT_PERMISSIONS)
            if task.created_by != username:
                raise ErrorResponse.forbidden(ErrorMessages.INSUFFICIENT_PERMISSIONS)

        # Soft delete: mark as deleted instead of physically removing
        task.is_deleted = 1
        await db.commit()
        return {"status": "success", "task_id": task_id, "message": "Task deleted"}
    except ErrorResponse:
        await db.rollback()
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        await db.rollback()
        logger.error("Failed to delete common task {}: {}", task_id, e, exc_info=True)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_DELETION_FAILED)


async def test_common_api_svc(
    request: Request, body: CommonTaskCreateReq
) -> Dict[str, Any]:
    """
    Test a common API endpoint with provided configuration (non-stream).
    """
    MAX_BODY_LENGTH = 100000

    if body.request_body and len(body.request_body) > MAX_BODY_LENGTH:
        return {
            "status": "error",
            "error": f"Request body length exceeds {MAX_BODY_LENGTH} characters. Please shorten payload or use dataset upload.",
            "response": None,
        }

    headers = kv_items_to_dict(body.headers)
    cookies = kv_items_to_dict(body.cookies)
    json_payload, text_payload = _prepare_request_body(body.request_body)
    method = body.method.upper()
    target_url = body.target_url

    timeout_config = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)

    # If dataset_file provided, pick the first non-empty record for testing
    dataset_path = body.dataset_file if isinstance(body.dataset_file, str) else None
    if dataset_path:
        try:
            with open(dataset_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json_payload = json.loads(line)
                        text_payload = None
                    except Exception:
                        json_payload = None
                        text_payload = line
                    break
        except Exception as e:
            logger.error("Failed to read dataset file for testing: {}", e)
            return {
                "status": "error",
                "error": f"Failed to read dataset file: {e}",
                "response": None,
            }

    try:
        async with httpx.AsyncClient(
            timeout=timeout_config, verify=False, limits=limits
        ) as client:
            response = await client.request(
                method,
                target_url,
                headers=headers,
                cookies=cookies,
                json=json_payload,
                content=text_payload,
            )
            return {
                "status": "success",
                "http_status": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
    except ssl.SSLError as e:
        msg = str(e)
        hint = ""
        if "PEM lib" in msg or "PEM routines" in msg:
            hint = (
                "Client certificate/private key format error: only PEM is supported. "
                "Please upload a PEM file containing the private key, or provide both "
                "PEM certificate and PEM private key; P12/PFX is not supported."
            )
        elif "no certificate or crl found" in msg:
            hint = (
                "No valid certificate content found, please confirm the file is correct"
            )
        logger.error("SSL error when testing common API: {}", e)
        return {
            "status": "error",
            "error": f"SSL error: {msg}. {hint}",
            "response": None,
        }
    except httpx.TimeoutException as e:
        logger.error("Request timeout when testing common API.")
        return {
            "status": "error",
            "error": f"Request timeout: {str(e)}",
            "response": None,
        }
    except httpx.ConnectError as e:
        logger.error("Connection error when testing common API.")
        return {
            "status": "error",
            "error": f"Connection error: {str(e)}",
            "response": None,
        }
    except asyncio.TimeoutError:
        logger.error("Asyncio timeout when testing common API")
        return {
            "status": "error",
            "error": "Operation timeout, please check network connection and target server status",
            "response": None,
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Error testing common API: {}", e, exc_info=True)
        return {
            "status": "error",
            "error": f"Unexpected error: {str(e)}",
            "response": None,
        }


async def stop_common_task_svc(request: Request, task_id: str) -> CommonTaskCreateRsp:
    try:
        db = request.state.db
        task = await db.get(CommonTask, task_id)
        if not task or getattr(task, "is_deleted", 0) == 1:
            return CommonTaskCreateRsp(
                status="unknown", task_id=task_id, message="Task not found"
            )

        if settings.LDAP_ENABLED:
            username = _get_username_from_request(request)
            # forbid stopping task without creator info or by non-creator
            if not task.created_by or task.created_by != username:
                raise ErrorResponse.forbidden(ErrorMessages.INSUFFICIENT_PERMISSIONS)

        if task.status != "running":
            return CommonTaskCreateRsp(
                status=task.status,
                task_id=task_id,
                message="Task is not currently running.",
            )

        task.status = "stopping"
        await db.commit()
        return CommonTaskCreateRsp(
            status="stopping", task_id=task_id, message="Task is being stopped."
        )
    except Exception as e:
        logger.error("Failed to stop common task {}: {}", task_id, e, exc_info=True)
        return CommonTaskCreateRsp(
            status="error", task_id=task_id, message="Failed to stop task."
        )


async def get_common_task_result_svc(
    request: Request, task_id: str
) -> CommonTaskResultRsp:
    if not task_id:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_ID_MISSING)
    if not await _is_task_exist(request, task_id):
        logger.warning(
            "Attempted to get common results for non-existent task: {}", task_id
        )
        return CommonTaskResultRsp(
            error="Task not found", status="not_found", results=[]
        )

    query_task_result = (
        select(CommonTaskResult)
        .where(CommonTaskResult.task_id == task_id)
        .order_by(CommonTaskResult.created_at.asc())
    )
    result = await request.state.db.execute(query_task_result)
    task_results = result.scalars().all()

    if not task_results:
        return CommonTaskResultRsp(
            error="No test results found for this task",
            status="not_found",
            results=[],
        )

    result_items = [task_result.to_task_result_item() for task_result in task_results]
    return CommonTaskResultRsp(results=result_items, status="success", error=None)


async def get_common_task_svc(request: Request, task_id: str) -> Dict[str, Any]:
    db = request.state.db
    try:
        task = await db.get(CommonTask, task_id)
        if not task or getattr(task, "is_deleted", 0) == 1:
            raise ErrorResponse.not_found("Task not found")
        return _build_task_detail(task)
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to retrieve common task {}: {}", task_id, e, exc_info=True)
        raise ErrorResponse.internal_server_error(
            "An internal error occurred while retrieving the common task."
        )


async def get_common_task_status_svc(request: Request, task_id: str) -> Dict[str, Any]:
    db = request.state.db
    try:
        query = (
            select(
                CommonTask.id,
                CommonTask.name,
                CommonTask.status,
                CommonTask.error_message,
                CommonTask.updated_at,
            )
            .where(CommonTask.id == task_id)
            .where(CommonTask.is_deleted == 0)
        )
        result = await db.execute(query)
        task_data = result.first()
        if not task_data:
            raise ErrorResponse.not_found("Task not found")
        return {
            "id": task_data.id,
            "name": task_data.name,
            "status": task_data.status,
            "error_message": task_data.error_message,
            "updated_at": safe_isoformat(task_data.updated_at),
        }
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error(
            "Failed to retrieve common task status {}: {}", task_id, e, exc_info=True
        )
        raise ErrorResponse.internal_server_error(
            "An internal error occurred while retrieving the task status."
        )


async def get_common_tasks_for_comparison_svc(
    request: Request,
) -> CommonComparisonTasksResponse:
    """
    Fetch completed common API tasks that have results for comparison.
    """
    try:
        db = request.state.db
        query = (
            select(
                CommonTask.id,
                CommonTask.name,
                CommonTask.method,
                CommonTask.target_url,
                CommonTask.concurrent_users,
                CommonTask.created_at,
                CommonTask.duration,
            )
            .where(CommonTask.status.in_(["completed", "failed_requests"]))
            .where(CommonTask.is_deleted == 0)
            .join(CommonTaskResult, CommonTask.id == CommonTaskResult.task_id)
            .distinct()
            .order_by(CommonTask.created_at.desc(), CommonTask.concurrent_users)
        )

        result = await db.execute(query)
        tasks = result.all()

        task_infos = [
            CommonComparisonTaskInfo(
                task_id=task.id,
                task_name=task.name or f"Task {task.id[:8]}",
                method=task.method,
                target_url=task.target_url,
                concurrent_users=task.concurrent_users,
                created_at=task.created_at.isoformat() if task.created_at else "",
                duration=task.duration or 0,
            )
            for task in tasks
        ]

        return CommonComparisonTasksResponse(
            data=task_infos, status="success", error=None
        )
    except Exception as e:
        logger.error("Failed to get common tasks for comparison: {}", e, exc_info=True)
        raise ErrorResponse.internal_server_error(
            "Failed to fetch common tasks for comparison"
        )


async def _extract_common_task_metrics(
    db, task_id: str, task: Optional[CommonTask] = None
) -> Optional[Dict[str, Any]]:
    """Extract aggregated metrics for a common API task."""
    try:
        if not task:
            task = await db.get(CommonTask, task_id)
        if not task or getattr(task, "is_deleted", 0) == 1:
            return None

        query = (
            select(CommonTaskResult)
            .where(CommonTaskResult.task_id == task_id)
            .order_by(CommonTaskResult.created_at.desc())
        )
        result = await db.execute(query)
        rows = result.scalars().all()
        if not rows:
            return None

        # Prefer the total row; fall back to the latest entry
        selected = next(
            (row for row in rows if str(row.metric_type).lower() == "total"), rows[0]
        )

        request_count = int(selected.num_requests or 0)
        failure_count = int(selected.num_failures or 0)
        success_rate = (
            ((request_count - failure_count) / request_count) * 100
            if request_count > 0
            else 0.0
        )

        return {
            "task_id": task_id,
            "task_name": getattr(task, "name", f"Task {task_id[:8]}"),
            "method": getattr(task, "method", ""),
            "target_url": getattr(task, "target_url", ""),
            "concurrent_users": getattr(task, "concurrent_users", 0),
            "duration": f"{getattr(task, 'duration', 0)}s",
            "request_count": request_count,
            "failure_count": failure_count,
            "success_rate": float(success_rate),
            "rps": float(selected.rps or 0.0),
            "avg_response_time": float(selected.avg_latency or 0.0) / 1000.0,
            "p95_response_time": float(selected.p95_latency or 0.0) / 1000.0,
            "min_response_time": float(selected.min_latency or 0.0) / 1000.0,
            "max_response_time": float(selected.max_latency or 0.0) / 1000.0,
            "avg_content_length": float(selected.avg_content_length or 0.0),
        }
    except Exception as e:
        logger.error("Failed to extract common metrics for task {}: {}", task_id, e)
        return None


def _read_jsonl_metrics(task_id: str, since: float) -> List[Dict[str, Any]]:
    """Read real-time metrics from the JSONL file (used for running tasks)."""
    metrics_path = os.path.join(
        tempfile.gettempdir(), "locust_result", task_id, "realtime_metrics.jsonl"
    )
    if not os.path.exists(metrics_path):
        return []

    data_points: List[Dict[str, Any]] = []
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    point = json.loads(line)
                    ts = point.get("timestamp", 0)
                    if ts > since:
                        data_points.append(point)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning("Failed to read realtime metrics JSONL for {}: {}", task_id, e)
    return data_points


async def _read_db_metrics(session, task_id: str, since: float) -> List[Dict[str, Any]]:
    """Read persisted real-time metrics from the database (used for completed tasks)."""
    try:
        stmt = (
            select(CommonTaskRealtimeMetric)
            .where(CommonTaskRealtimeMetric.task_id == task_id)
            .where(CommonTaskRealtimeMetric.timestamp > since)
            .order_by(CommonTaskRealtimeMetric.timestamp.asc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "timestamp": float(r.timestamp),
                "current_users": int(r.current_users),
                "current_rps": float(r.current_rps),
                "current_fail_per_sec": float(r.current_fail_per_sec),
                "avg_response_time": float(r.avg_response_time),
                "min_response_time": float(r.min_response_time),
                "max_response_time": float(r.max_response_time),
                "median_response_time": float(r.median_response_time),
                "p95_response_time": float(r.p95_response_time),
                "total_requests": int(r.total_requests),
                "total_failures": int(r.total_failures),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Failed to read realtime metrics from DB for {}: {}", task_id, e)
        return []


async def get_common_task_realtime_metrics_svc(
    request: Request, task_id: str, since: float = 0.0
) -> Dict[str, Any]:
    """
    Hybrid read strategy for real-time metrics:
    1. Try JSONL file first (available while the task is running)
    2. Fall back to database (persisted after task finishes)
    This ensures charts work both during and after the test.
    """
    if not task_id:
        return {"status": "error", "error": "task_id is required", "data": []}

    # Strategy: try JSONL first (faster, most up-to-date for running tasks)
    data_points = _read_jsonl_metrics(task_id, since)

    if data_points:
        return {"status": "ok", "data": data_points}

    # Fallback: read from database (for completed/stopped/failed tasks)
    session = request.state.db
    data_points = await _read_db_metrics(session, task_id, since)

    return {"status": "ok", "data": data_points}


async def compare_common_performance_svc(
    request: Request, comparison_request: CommonComparisonRequest
) -> CommonComparisonResponse:
    """
    Compare performance metrics for selected common API tasks.
    """
    try:
        db = request.state.db
        task_ids = comparison_request.selected_tasks

        if len(task_ids) < 2:
            return CommonComparisonResponse(
                data=[],
                status="error",
                error="At least 2 tasks are required for comparison",
            )

        if len(task_ids) > 10:
            return CommonComparisonResponse(
                data=[],
                status="error",
                error="Maximum 10 tasks can be compared at once",
            )

        task_query = (
            select(CommonTask)
            .where(CommonTask.id.in_(task_ids))
            .where(CommonTask.is_deleted == 0)
        )
        task_result = await db.execute(task_query)
        tasks = {task.id: task for task in task_result.scalars().all()}

        missing_tasks = set(task_ids) - set(tasks.keys())
        if missing_tasks:
            return CommonComparisonResponse(
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
            return CommonComparisonResponse(
                data=[],
                status="error",
                error="Only completed tasks can be compared. "
                f"Incomplete tasks: {', '.join(incomplete_tasks)}",
            )

        metrics_data_list = []
        for task_id in task_ids:
            task = tasks.get(task_id)
            metrics = await _extract_common_task_metrics(db, task_id, task)
            if metrics:
                metrics_data_list.append(metrics)

        if not metrics_data_list:
            return CommonComparisonResponse(
                data=[],
                status="error",
                error="No valid metrics data found for the selected tasks.",
            )

        comparison_metrics: List[CommonComparisonMetrics] = []
        for metrics_data in metrics_data_list:
            try:
                comparison_metrics.append(CommonComparisonMetrics(**metrics_data))
            except Exception as e:
                logger.error(
                    "Failed to build CommonComparisonMetrics for task {}: {}",
                    metrics_data.get("task_id", "unknown"),
                    e,
                )

        if not comparison_metrics:
            return CommonComparisonResponse(
                data=[],
                status="error",
                error="Failed to process metrics data for the selected tasks",
            )

        return CommonComparisonResponse(
            data=comparison_metrics, status="success", error=None
        )
    except Exception as e:
        logger.error("Failed to compare common task performance: {}", e, exc_info=True)
        return CommonComparisonResponse(
            data=[],
            status="error",
            error="Failed to perform common performance comparison",
        )
