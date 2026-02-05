"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from model.task import (
    ComparisonRequest,
    ComparisonResponse,
    ModelListResponse,
    ModelTasksResponse,
    TaskCreateReq,
    TaskCreateRsp,
    TaskResponse,
    TaskResultRsp,
    TaskStatusRsp,
)
from service.task_service import (
    compare_performance_svc,
    create_task_svc,
    delete_task_svc,
    get_all_models_svc,
    get_model_tasks_for_comparison_svc,
    get_task_result_svc,
    get_task_status_svc,
    get_task_svc,
    get_tasks_status_svc,
    get_tasks_svc,
    stop_task_svc,
    test_llm_api_svc,
    update_task_svc,
)

# Create an API router for task-related endpoints
router = APIRouter()


@router.get("", response_model=TaskResponse)
async def get_tasks(
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    creator: Optional[str] = None,
    model: Optional[str] = None,
):
    """
    Get a paginated and filtered list of tasks.

    Args:
        request (Request): The incoming request.
        page (int): The page number to retrieve.
        pageSize (int): The number of tasks per page.
        status (Optional[str]): Filter tasks by status.
        search (Optional[str]): Search tasks by a keyword.
        creator (Optional[str]): Filter tasks by creator username.
        model (Optional[str]): Filter tasks by model name.

    Returns:
        TaskResponse: A response object containing the list of tasks.
    """
    return await get_tasks_svc(request, page, pageSize, status, search, creator, model)


@router.get("/status", response_model=TaskStatusRsp)
async def get_tasks_status(request: Request, page_size: int = Query(50, ge=1, le=100)):
    """
    Get a list of task statuses.

    Args:
        request (Request): The incoming request.
        page_size (int): The number of task statuses to retrieve.

    Returns:
        TaskStatusRsp: A response object containing the list of task statuses.
    """
    return await get_tasks_status_svc(request, page_size)


@router.get("/models", response_model=ModelListResponse)
async def get_all_models(request: Request):
    """
    Get all unique model names used in tasks.

    Args:
        request (Request): The incoming request.

    Returns:
        Dict[str, Any]: A response containing the list of unique model names.
    """
    return await get_all_models_svc(request)


@router.post("", response_model=TaskCreateRsp)
async def create_task(request: Request, task_create: TaskCreateReq):
    """
    Create a new task.

    Args:
        request (Request): The incoming request.
        task_create (TaskCreateReq): The data for creating the new task.

    Returns:
        TaskCreateRsp: A response object confirming the task creation.
    """
    return await create_task_svc(request, task_create)


@router.post("/stop/{task_id}", response_model=TaskCreateRsp)
async def stop_task(request: Request, task_id: str):
    """
    Stop a running task.

    Args:
        request (Request): The incoming request.
        task_id (str): The ID of the task to stop.

    Returns:
        TaskCreateRsp: A response object confirming that the stop request was sent.
    """
    return await stop_task_svc(request, task_id)


@router.get("/{task_id}/results", response_model=TaskResultRsp)
async def get_task_result(request: Request, task_id: str):
    """
    Get the results of a specific task.

    Args:
        request (Request): The incoming request.
        task_id (str): The ID of the task.

    Returns:
        TaskResultRsp: A response object containing the task results.
    """
    return await get_task_result_svc(request, task_id)


@router.put("/{task_id}")
async def update_task(request: Request, task_id: str, payload: Dict[str, Any]):
    """
    Update mutable fields for a task (e.g., rename). Only creator can update.
    """
    return await update_task_svc(request, task_id, payload)


@router.delete("/{task_id}")
async def delete_task(request: Request, task_id: str):
    """
    Delete a task. Only creator can delete.
    """
    return await delete_task_svc(request, task_id)


@router.get("/{task_id}", response_model=Dict[str, Any])
async def get_task(request: Request, task_id: str):
    """
    Get a specific task by its ID.

    Args:
        request (Request): The incoming request.
        task_id (str): The ID of the task to retrieve.

    Returns:
        Dict[str, Any]: A dictionary containing the details of the task.
    """
    return await get_task_svc(request, task_id)


@router.get("/{task_id}/status", response_model=Dict[str, Any])
async def get_task_status(request: Request, task_id: str):
    """
    Get the status of a specific task by its ID (lightweight query).

    Args:
        request (Request): The incoming request.
        task_id (str): The ID of the task whose status to retrieve.

    Returns:
        Dict[str, Any]: A dictionary containing the task status information.
    """
    return await get_task_status_svc(request, task_id)


@router.get("/comparison/available", response_model=ModelTasksResponse)
async def get_model_tasks_for_comparison(request: Request):
    """
    Get available model tasks that can be used for performance comparison.
    Only returns completed tasks that have results.

    Args:
        request (Request): The incoming request.

    Returns:
        ModelTasksResponse: A response object containing available model tasks.
    """
    return await get_model_tasks_for_comparison_svc(request)


@router.post("/comparison", response_model=ComparisonResponse)
async def compare_performance(request: Request, comparison_request: ComparisonRequest):
    """
    Compare performance metrics for selected tasks.

    Args:
        request (Request): The incoming request.
        comparison_request (ComparisonRequest): Request containing task IDs to compare.

    Returns:
        ComparisonResponse: A response object containing comparison metrics.
    """
    return await compare_performance_svc(request, comparison_request)


@router.post("/test", response_model=Dict[str, Any])
async def test_llm_api(request: Request, task_create: TaskCreateReq):
    """
    Test the API endpoint with the provided configuration.

    Args:
        request (Request): The incoming request.
        task_create (TaskCreateReq): The data for testing the API endpoint.

    Returns:
        Dict[str, Any]: A response containing the test result.
    """
    return await test_llm_api_svc(request, task_create)
