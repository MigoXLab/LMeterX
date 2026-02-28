"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from service.monitoring_service import (
    get_available_engines,
    get_engine_resource_metrics,
    get_task_perf_metrics_from_vm,
)
from utils.logger import logger

router = APIRouter()


@router.get("/engines", response_model=Dict[str, Any])
async def list_engines():
    """Get a list of Engine instances that have reported metrics recently."""
    try:
        engines = await get_available_engines()
        return {"status": "success", "data": engines}
    except Exception as e:
        logger.error("Failed to list engines: {}", e, exc_info=True)
        return {"status": "error", "data": [], "error": str(e)}


@router.get("/engine-resources", response_model=Dict[str, Any])
async def get_engine_resources(
    engine_id: Optional[str] = Query(None, description="Filter by engine ID"),
    start: Optional[float] = Query(None, description="Start timestamp (Unix seconds)"),
    end: Optional[float] = Query(None, description="End timestamp (Unix seconds)"),
    max_points: int = Query(
        1200, ge=100, le=5000, description="Max data points per series"
    ),
):
    """Get Engine system resource metrics (CPU, Memory, Network).

    Supports time range queries with automatic downsampling (LTTB) for
    efficient frontend rendering.
    """
    try:
        data = await get_engine_resource_metrics(
            engine_id=engine_id,
            start=start,
            end=end,
            max_points=max_points,
        )
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error("Failed to get engine resources: {}", e, exc_info=True)
        return {"status": "error", "data": {}, "error": str(e)}


@router.get("/task-metrics/{task_id}", response_model=Dict[str, Any])
async def get_task_metrics(
    task_id: str,
    since: float = Query(0.0, description="Only return data after this timestamp"),
    max_points: int = Query(1200, ge=100, le=5000, description="Max data points"),
):
    """Get real-time performance metrics for a task from VictoriaMetrics.

    This endpoint provides the same data format as the legacy JSONL-based
    ``/tasks/{task_id}/realtime-metrics`` endpoint, but reads from
    VictoriaMetrics for better scalability and historical retention.
    """
    try:
        data_points = await get_task_perf_metrics_from_vm(
            task_id=task_id,
            since=since,
            max_points=max_points,
        )
        return {"status": "success", "data": data_points}
    except Exception as e:
        logger.error("Failed to get task metrics from VM: {}", e, exc_info=True)
        return {"status": "error", "data": [], "error": str(e)}
