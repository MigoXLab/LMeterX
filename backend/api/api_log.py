"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from model.log import LogContentResponse, SLSLogResponse
from service.log_service import (
    download_task_log_svc,
    get_engine_system_log_svc,
    get_service_log_svc,
    get_task_log_svc,
)
from service.sls_log_service import query_sls_logs_svc

# Create an API router for log-related endpoints
router = APIRouter()


@router.get("/sls/task/{task_id}", response_model=SLSLogResponse)
async def query_sls_task_log(
    task_id: str,
    start_time: int | None = Query(default=None),
    end_time: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    keyword: str | None = Query(default=None),
    level: str | None = Query(default=None),
    reverse: bool = Query(default=False),
):
    """Query task logs from Alibaba Cloud SLS."""
    return await query_sls_logs_svc(
        task_id=task_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
        keyword=keyword,
        level=level,
        reverse=reverse,
    )


@router.get("/sls/engine/{engine_id}", response_model=SLSLogResponse)
async def query_sls_engine_log(
    engine_id: str,
    cluster_id: str = Query(...),
    start_time: int | None = Query(default=None),
    end_time: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    keyword: str | None = Query(default=None),
    level: str | None = Query(default=None),
    reverse: bool = Query(default=False),
):
    """Query engine logs from Alibaba Cloud SLS."""
    response = await query_sls_logs_svc(
        service="engine",
        engine_id=engine_id,
        cluster_id=cluster_id,
        exclude_task_logs=True,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
        keyword=keyword,
        level=level,
        reverse=reverse,
    )
    if response.logs or cluster_id != "local":
        return response

    # Backward compatibility: older/local engine SLS records may have been
    # written without cluster_id before the engine sink had a local default.
    return await query_sls_logs_svc(
        service="engine",
        engine_id=engine_id,
        exclude_task_logs=True,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
        keyword=keyword,
        level=level,
        reverse=reverse,
    )


@router.get("/sls/{service_name}", response_model=SLSLogResponse)
async def query_sls_service_log(
    service_name: str,
    start_time: int | None = Query(default=None),
    end_time: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    keyword: str | None = Query(default=None),
    level: str | None = Query(default=None),
    reverse: bool = Query(default=False),
):
    """Query service logs from Alibaba Cloud SLS."""
    return await query_sls_logs_svc(
        service=service_name,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
        keyword=keyword,
        level=level,
        reverse=reverse,
    )


@router.get("/engine/{engine_id}", response_model=LogContentResponse)
async def get_engine_system_log(
    engine_id: str,
    cluster_id: str = Query(..., description="Cluster ID of the engine"),
    offset: int = Query(default=0, ge=0),
    tail: int = Query(default=0, ge=0),
):
    """Get the system log of a specific engine instance."""
    return await get_engine_system_log_svc(engine_id, cluster_id, offset, tail)


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
