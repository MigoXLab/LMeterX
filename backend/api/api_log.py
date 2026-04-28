"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from model.log import LogContentResponse
from service.log_service import (
    download_task_log_svc,
    get_service_log_svc,
    get_task_log_svc,
)

# Create an API router for log-related endpoints
router = APIRouter()


@router.get("/{service_name}", response_model=LogContentResponse)
async def get_service_log(
    service_name: str,
    offset: int = Query(default=0, ge=0),
    tail: int = Query(default=0, ge=0),
):
    """
    Get the log content of a specified service.

    Args:
        service_name (str): The name of the service (e.g., "backend", "engine").
        offset (int): The offset in bytes from the beginning of the log file. Ineffective when tail > 0.
        tail (int): The number of lines to read from the end of the log file. When tail > 0, offset is ignored.

    Returns:
        LogContentResponse: An object containing the log content.
                            By default (offset=0, tail=0), the entire log file is read.
    """
    return await get_service_log_svc(service_name, offset, tail)


@router.get("/task/{task_id}", response_model=LogContentResponse)
async def get_task_log(
    task_id: str,
    offset: int = Query(default=0),
    tail: int = Query(default=0),
    source: str = Query(default="engine", description="Log source: engine or backend"),
):
    """
    Get the log content of a specified task.

    Args:
        task_id (str): The ID of the task.
        offset (int): The offset in bytes from the beginning of the log file. Ineffective when tail > 0.
        tail (int): The number of lines to read from the end of the log file. When tail > 0, offset is ignored.
        source (str): The source of the log ("engine" or "backend").

    Returns:
        LogContentResponse: An object containing the log content.
                            By default (offset=0, tail=0), the entire log file is read.
    """
    return await get_task_log_svc(task_id, offset, tail, source)


@router.get("/task/{task_id}/download", response_class=FileResponse)
async def download_task_log(
    task_id: str,
    source: str = Query(default="engine", description="Log source: engine or backend"),
):
    """
    Download the full output log for a given task.
    """
    return await download_task_log_svc(task_id, source)
