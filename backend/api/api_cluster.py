"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Cluster management API: list clusters, desired state, actual state, scaling.
"""

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from service import cluster_service
from utils.error_handler import ErrorResponse

router = APIRouter()


# --- Request/Response Models ---


class ScaleReq(BaseModel):
    desired_replicas: int = Field(..., ge=0, le=100)


class ActualStateReq(BaseModel):
    current_replicas: int = Field(..., ge=0)
    ready_replicas: int = Field(..., ge=0)
    available_replicas: int = Field(..., ge=0)


class CreateClusterReq(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    min_replicas: int = Field(default=1, ge=0, le=100)
    max_replicas: int = Field(default=10, ge=1, le=100)


# --- Endpoints ---


@router.get("")
async def list_clusters(request: Request):
    db = request.state.db
    clusters = await cluster_service.list_clusters(db)
    return {"clusters": clusters}


@router.post("")
async def create_cluster(request: Request, body: CreateClusterReq):
    db = request.state.db
    existing = await cluster_service.get_cluster(db, body.id)
    if existing:
        raise ErrorResponse.bad_request(f"Cluster '{body.id}' already exists")
    result = await cluster_service.create_cluster(
        db=db,
        cluster_id=body.id,
        name=body.name,
        description=body.description,
        min_replicas=body.min_replicas,
        max_replicas=body.max_replicas,
    )
    return result


@router.get("/{cluster_id}")
async def get_cluster(request: Request, cluster_id: str):
    db = request.state.db
    cluster = await cluster_service.get_cluster(db, cluster_id)
    if not cluster:
        raise ErrorResponse.not_found(f"Cluster '{cluster_id}' not found")
    return cluster


@router.get("/{cluster_id}/desired-state")
async def get_desired_state(request: Request, cluster_id: str):
    db = request.state.db
    state = await cluster_service.get_desired_state(db, cluster_id)
    if not state:
        raise ErrorResponse.not_found(f"Cluster '{cluster_id}' not found")
    return state


@router.post("/{cluster_id}/actual-state")
async def update_actual_state(request: Request, cluster_id: str, body: ActualStateReq):
    db = request.state.db
    success = await cluster_service.update_actual_state(
        db=db,
        cluster_id=cluster_id,
        current_replicas=body.current_replicas,
        ready_replicas=body.ready_replicas,
        available_replicas=body.available_replicas,
    )
    if not success:
        raise ErrorResponse.not_found(f"Cluster '{cluster_id}' not found")
    return {"status": "ok"}


@router.put("/{cluster_id}/scale")
async def scale_cluster(request: Request, cluster_id: str, body: ScaleReq):
    db = request.state.db
    result = await cluster_service.scale_cluster(
        db=db, cluster_id=cluster_id, desired_replicas=body.desired_replicas
    )
    if not result:
        raise ErrorResponse.not_found(f"Cluster '{cluster_id}' not found")
    return result
