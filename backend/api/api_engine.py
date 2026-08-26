"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Engine management API: registration, heartbeat, task claim, status/result reporting.
These endpoints are called by Engine instances (not by frontend users).
"""

from typing import List, Optional

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from service import engine_service
from utils.error_handler import ErrorResponse
from utils.logger import logger

router = APIRouter()


# --- Request/Response Models ---


class EngineCapabilities(BaseModel):
    cpu_cores: float = 2.0
    memory_gb: float = 4.0
    max_concurrent_tasks: int = 1


class RegisterReq(BaseModel):
    engine_id: str = Field(..., max_length=64)
    cluster_id: str = Field(..., max_length=64)
    capabilities: EngineCapabilities = Field(default_factory=EngineCapabilities)
    version: Optional[str] = None
    deployment_name: Optional[str] = Field(None, max_length=128)
    pod_name: Optional[str] = Field(None, max_length=253)


class HeartbeatReq(BaseModel):
    engine_id: str = Field(..., max_length=64)
    cluster_id: str = Field(..., max_length=64)
    running_tasks: List[str] = Field(default_factory=list)
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    available_slots: int = 1
    deployment_name: Optional[str] = Field(None, max_length=128)
    pod_name: Optional[str] = Field(None, max_length=253)


class ClaimReq(BaseModel):
    engine_id: str = Field(..., max_length=64)
    cluster_id: str = Field(..., max_length=64)
    task_types: List[str] = Field(default_factory=lambda: ["llm", "http"])


class TaskStatusReq(BaseModel):
    engine_id: str = Field(..., max_length=64)
    status: str = Field(..., max_length=32)
    progress: Optional[int] = None
    message: Optional[str] = None


class TaskResultReq(BaseModel):
    engine_id: str = Field(..., max_length=64)
    locust_results: Optional[dict] = None
    final_status: str = Field(..., max_length=32)
    error_message: Optional[str] = None


# --- Endpoints ---


@router.post("/register")
async def register(request: Request, body: RegisterReq):
    db = request.state.db
    result = await engine_service.register_engine(
        db=db,
        engine_id=body.engine_id,
        cluster_id=body.cluster_id,
        capabilities=body.capabilities.model_dump(),
        version=body.version,
        deployment_name=body.deployment_name,
        pod_name=body.pod_name,
    )
    return result


@router.post("/heartbeat")
async def heartbeat(request: Request, body: HeartbeatReq):
    db = request.state.db
    result = await engine_service.process_heartbeat(
        db=db,
        engine_id=body.engine_id,
        cluster_id=body.cluster_id,
        running_tasks=body.running_tasks,
        cpu_usage=body.cpu_usage,
        memory_usage=body.memory_usage,
        available_slots=body.available_slots,
        deployment_name=body.deployment_name,
        pod_name=body.pod_name,
    )
    return result


@router.post("/tasks/claim")
async def claim_task(request: Request, body: ClaimReq):
    db = request.state.db
    try:
        task = await engine_service.claim_task(
            db=db,
            engine_id=body.engine_id,
            cluster_id=body.cluster_id,
            task_types=body.task_types,
        )
    except Exception as exc:
        logger.exception(
            "Failed to claim task: engine_id={}, cluster_id={}, task_types={}",
            body.engine_id,
            body.cluster_id,
            body.task_types,
        )
        raise ErrorResponse(
            503,
            "Failed to claim task",
            details=str(exc),
            code="engine_claim_failed",
        )
    return {"task": task}


@router.put("/tasks/{task_id}/status")
async def update_status(request: Request, task_id: str, body: TaskStatusReq):
    db = request.state.db
    success = await engine_service.update_task_status(
        db=db,
        task_id=task_id,
        engine_id=body.engine_id,
        status=body.status,
        progress=body.progress,
        message=body.message,
    )
    if not success:
        return {"status": "error", "message": "Task not found or not owned by engine"}
    return {"status": "ok"}


@router.post("/tasks/{task_id}/results")
async def submit_results(request: Request, task_id: str, body: TaskResultReq):
    db = request.state.db
    success = await engine_service.submit_task_results(
        db=db,
        task_id=task_id,
        engine_id=body.engine_id,
        locust_results=body.locust_results or {},
        final_status=body.final_status,
        error_message=body.error_message,
    )
    if not success:
        return {"status": "error", "message": "Task not found or not owned by engine"}
    return {"status": "ok"}


@router.get("/tasks/stopping")
async def get_stopping_tasks(request: Request, engine_id: str, cluster_id: str):
    db = request.state.db
    task_ids = await engine_service.get_stopping_tasks(
        db=db, engine_id=engine_id, cluster_id=cluster_id
    )
    return {"task_ids": task_ids}


# --- Probe Endpoints ---


class ProbeResultReq(BaseModel):
    engine_id: str = Field(..., max_length=64)
    result: dict = Field(default_factory=dict)


@router.post("/probes/{probe_id}/result")
async def submit_probe_result(request: Request, probe_id: str, body: ProbeResultReq):
    from service import probe_service

    db = request.state.db
    success = await probe_service.submit_probe_result(
        db=db,
        probe_id=probe_id,
        engine_id=body.engine_id,
        result=body.result,
    )
    if not success:
        return {"status": "error", "message": "Probe not found or not owned by engine"}
    return {"status": "ok"}


# --- Admin Cleanup Endpoints ---


class UnregisterReq(BaseModel):
    engine_id: str = Field(..., max_length=64)
    cluster_id: str = Field(..., max_length=64)


@router.post("/unregister")
async def unregister(request: Request, body: UnregisterReq):
    db = request.state.db
    result = await engine_service.unregister_engine(
        db=db, engine_id=body.engine_id, cluster_id=body.cluster_id
    )
    return result


class CleanupReq(BaseModel):
    valid_engine_ids: Optional[List[str]] = Field(
        None,
        description="List of currently valid engine UIDs. All others will be marked offline.",
    )
    cluster_id: Optional[str] = Field(
        None,
        description="Only clean engines in this cluster. If omitted, cleans all clusters.",
    )


@router.post("/cleanup")
async def cleanup_engines(request: Request, body: CleanupReq):
    db = request.state.db
    count = await engine_service.cleanup_stale_engines(
        db=db,
        valid_engine_ids=body.valid_engine_ids,
        cluster_id=body.cluster_id,
    )
    return {"status": "ok", "cleaned": count}
