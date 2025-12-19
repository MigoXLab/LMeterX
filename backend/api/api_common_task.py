"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from model.common_task import (
    CommonComparisonRequest,
    CommonComparisonResponse,
    CommonComparisonTasksResponse,
    CommonTaskCreateReq,
    CommonTaskCreateRsp,
    CommonTaskResponse,
    CommonTaskResultRsp,
    CommonTaskStatusRsp,
)
from service.common_task_service import (
    test_common_api_svc,  # type: ignore[attr-defined]
)
from service.common_task_service import (
    compare_common_performance_svc,
    create_common_task_svc,
    get_common_task_result_svc,
    get_common_task_status_svc,
    get_common_task_svc,
    get_common_tasks_for_comparison_svc,
    get_common_tasks_status_svc,
    get_common_tasks_svc,
    stop_common_task_svc,
)

router = APIRouter()


@router.get("", response_model=CommonTaskResponse)
async def get_common_tasks(
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    return await get_common_tasks_svc(request, page, pageSize, status, search)


@router.get("/comparison/available", response_model=CommonComparisonTasksResponse)
async def get_common_tasks_for_comparison(request: Request):
    """List common API tasks that can be used for comparison."""
    return await get_common_tasks_for_comparison_svc(request)


@router.post("/comparison", response_model=CommonComparisonResponse)
async def compare_common_performance(
    request: Request, comparison_request: CommonComparisonRequest
):
    """Compare performance metrics for selected common API tasks."""
    return await compare_common_performance_svc(request, comparison_request)


@router.get("/status", response_model=CommonTaskStatusRsp)
async def get_common_tasks_status(
    request: Request, page_size: int = Query(50, ge=1, le=100)
):
    return await get_common_tasks_status_svc(request, page_size)


@router.post("", response_model=CommonTaskCreateRsp)
async def create_common_task(request: Request, task_create: CommonTaskCreateReq):
    return await create_common_task_svc(request, task_create)


@router.post("/test", response_model=Dict[str, Any])
async def test_common_api(request: Request, task_create: CommonTaskCreateReq):
    return await test_common_api_svc(request, task_create)


@router.post("/stop/{task_id}", response_model=CommonTaskCreateRsp)
async def stop_common_task(request: Request, task_id: str):
    return await stop_common_task_svc(request, task_id)


@router.get("/{task_id}/results", response_model=CommonTaskResultRsp)
async def get_common_task_result(request: Request, task_id: str):
    return await get_common_task_result_svc(request, task_id)


@router.get("/{task_id}", response_model=Dict[str, Any])
async def get_common_task(request: Request, task_id: str):
    return await get_common_task_svc(request, task_id)


@router.get("/{task_id}/status", response_model=Dict[str, Any])
async def get_common_task_status(request: Request, task_id: str):
    return await get_common_task_status_svc(request, task_id)
