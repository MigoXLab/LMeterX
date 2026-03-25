"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from model.http_task import (
    HttpComparisonRequest,
    HttpComparisonResponse,
    HttpComparisonTasksResponse,
    HttpTaskCreateReq,
    HttpTaskCreateRsp,
    HttpTaskResponse,
    HttpTaskResultRsp,
    HttpTaskStatusRsp,
    HttpTaskTestReq,
)
from service.http_task_service import test_http_api_svc  # type: ignore[attr-defined]
from service.http_task_service import (
    compare_http_performance_svc,
    create_http_task_svc,
    delete_http_task_svc,
    get_http_task_realtime_metrics_svc,
    get_http_task_result_svc,
    get_http_task_status_svc,
    get_http_task_svc,
    get_http_tasks_for_comparison_svc,
    get_http_tasks_status_svc,
    get_http_tasks_svc,
    stop_http_task_svc,
    update_http_task_svc,
)

router = APIRouter()


@router.get("", response_model=HttpTaskResponse)
async def get_http_tasks(
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    creator: Optional[str] = None,
):
    return await get_http_tasks_svc(request, page, pageSize, status, search, creator)


@router.get("/comparison/available", response_model=HttpComparisonTasksResponse)
async def get_http_tasks_for_comparison(request: Request):
    """List HTTP API tasks that can be used for comparison."""
    return await get_http_tasks_for_comparison_svc(request)


@router.post("/comparison", response_model=HttpComparisonResponse)
async def compare_http_performance(
    request: Request, comparison_request: HttpComparisonRequest
):
    """Compare performance metrics for selected HTTP API tasks."""
    return await compare_http_performance_svc(request, comparison_request)


@router.get("/status", response_model=HttpTaskStatusRsp)
async def get_http_tasks_status(
    request: Request, page_size: int = Query(50, ge=1, le=100)
):
    return await get_http_tasks_status_svc(request, page_size)


@router.post("", response_model=HttpTaskCreateRsp)
async def create_http_task(request: Request, task_create: HttpTaskCreateReq):
    return await create_http_task_svc(request, task_create)


@router.post("/test", response_model=Dict[str, Any])
async def test_http_api(request: Request, task_test: HttpTaskTestReq):
    return await test_http_api_svc(request, task_test)


@router.post("/stop/{task_id}", response_model=HttpTaskCreateRsp)
async def stop_http_task(request: Request, task_id: str):
    return await stop_http_task_svc(request, task_id)


@router.get("/{task_id}/results", response_model=HttpTaskResultRsp)
async def get_http_task_result(request: Request, task_id: str):
    return await get_http_task_result_svc(request, task_id)


@router.get("/{task_id}/realtime-metrics", response_model=Dict[str, Any])
async def get_http_task_realtime_metrics(
    request: Request,
    task_id: str,
    since: float = Query(
        0.0, description="Only return data points after this timestamp"
    ),
):
    """Get real-time performance metrics for a running task."""
    return await get_http_task_realtime_metrics_svc(request, task_id, since)


@router.put("/{task_id}")
async def update_http_task(request: Request, task_id: str, payload: Dict[str, Any]):
    """Update mutable fields of an HTTP task (e.g., rename). Only creator can update."""
    return await update_http_task_svc(request, task_id, payload)


@router.delete("/{task_id}")
async def delete_http_task(request: Request, task_id: str):
    """Delete an HTTP task. Only creator can delete."""
    return await delete_http_task_svc(request, task_id)


@router.get("/{task_id}", response_model=Dict[str, Any])
async def get_http_task(request: Request, task_id: str):
    return await get_http_task_svc(request, task_id)


@router.get("/{task_id}/status", response_model=Dict[str, Any])
async def get_http_task_status(request: Request, task_id: str):
    return await get_http_task_status_svc(request, task_id)
