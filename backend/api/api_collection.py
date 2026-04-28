"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request

from model.collection import (
    CollectionCreateRequest,
    CollectionTaskAddRequest,
    CollectionUpdateRequest,
)
from service.collection_service import (
    add_task_to_collection_svc,
    create_collection_svc,
    delete_collection_svc,
    get_collection_svc,
    list_collection_tasks_svc,
    list_collections_svc,
    remove_task_from_collection_svc,
    update_collection_svc,
)

router = APIRouter()


@router.post("", response_model=Dict[str, Any])
async def create_collection(
    request: Request, collection_create: CollectionCreateRequest
):
    return await create_collection_svc(request, collection_create)


@router.get("", response_model=Dict[str, Any])
async def list_collections(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
):
    return await list_collections_svc(request, page, page_size, search)


@router.get("/{collection_id}", response_model=Dict[str, Any])
async def get_collection(request: Request, collection_id: str):
    return await get_collection_svc(request, collection_id)


@router.put("/{collection_id}", response_model=Dict[str, Any])
async def update_collection(
    request: Request, collection_id: str, collection_update: CollectionUpdateRequest
):
    return await update_collection_svc(request, collection_id, collection_update)


@router.delete("/{collection_id}", response_model=Dict[str, Any])
async def delete_collection(request: Request, collection_id: str):
    return await delete_collection_svc(request, collection_id)


@router.post("/{collection_id}/tasks", response_model=Dict[str, Any])
async def add_task_to_collection(
    request: Request, collection_id: str, task_req: CollectionTaskAddRequest
):
    return await add_task_to_collection_svc(request, collection_id, task_req)


@router.delete("/{collection_id}/tasks/{task_id}", response_model=Dict[str, Any])
async def remove_task_from_collection(
    request: Request, collection_id: str, task_id: str
):
    return await remove_task_from_collection_svc(request, collection_id, task_id)


@router.get("/{collection_id}/tasks", response_model=Dict[str, Any])
async def list_collection_tasks(request: Request, collection_id: str):
    return await list_collection_tasks_svc(request, collection_id)
