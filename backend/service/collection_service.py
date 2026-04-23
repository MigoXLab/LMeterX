"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import uuid
from typing import Any, Dict, Optional, cast

from fastapi import Request
from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from model.collection import (
    Collection,
    CollectionCreateRequest,
    CollectionTask,
    CollectionTaskAddRequest,
    CollectionUpdateRequest,
)
from model.http_task import HttpTask
from model.llm_task import Task as LlmTask
from utils.auth import get_current_user, is_admin_user
from utils.error_handler import ErrorResponse


def _resolve_username(request: Request) -> str:
    user_info = get_current_user(request)
    return (
        user_info.get("username")
        or user_info.get("sub")
        or user_info.get("name")
        or "system"
    )


def _check_collection_permission(username: str, collection: Collection) -> None:
    if not is_admin_user(username) and collection.created_by != username:
        raise ErrorResponse.forbidden(
            "You do not have permission to modify this collection"
        )


def _serialize_collection(
    collection: Collection,
    task_count: int = 0,
) -> Dict[str, Any]:
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "rich_content": collection.rich_content,
        "created_by": collection.created_by,
        "is_public": bool(collection.is_public),
        "created_at": str(collection.created_at),
        "updated_at": str(collection.updated_at),
        "task_count": task_count,
    }


async def _get_collection_or_404(db: AsyncSession, collection_id: str) -> Collection:
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()
    if not collection:
        raise ErrorResponse.not_found("Collection not found")
    return collection


async def create_collection_svc(
    request: Request, collection_create: CollectionCreateRequest
) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    username = _resolve_username(request)

    db_collection = Collection(
        id=str(uuid.uuid4()),
        name=collection_create.name.strip(),
        description=collection_create.description,
        rich_content=collection_create.rich_content,
        created_by=username,
        is_public=1 if collection_create.is_public else 0,
    )
    db.add(db_collection)
    await db.flush()
    await db.refresh(db_collection)
    return _serialize_collection(db_collection, task_count=0)


async def update_collection_svc(
    request: Request,
    collection_id: str,
    collection_update: CollectionUpdateRequest,
) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    username = _resolve_username(request)
    db_collection = await _get_collection_or_404(db, collection_id)
    _check_collection_permission(username, db_collection)
    db_collection_obj = cast(Any, db_collection)

    if collection_update.name is not None:
        db_collection_obj.name = collection_update.name.strip()
    if collection_update.description is not None:
        db_collection_obj.description = collection_update.description
    if collection_update.rich_content is not None:
        db_collection_obj.rich_content = collection_update.rich_content
    if collection_update.is_public is not None:
        db_collection_obj.is_public = 1 if collection_update.is_public else 0

    await db.flush()
    await db.refresh(db_collection)
    return await get_collection_svc(request, collection_id)


async def get_collection_svc(request: Request, collection_id: str) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    db_collection = await _get_collection_or_404(db, collection_id)

    task_count = await db.scalar(
        select(func.count(CollectionTask.id)).where(
            CollectionTask.collection_id == collection_id
        )
    )
    return _serialize_collection(db_collection, task_count=task_count or 0)


async def list_collections_svc(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    username = _resolve_username(request)

    base_query = select(Collection).where(
        or_(Collection.is_public == 1, Collection.created_by == username)
    )
    if search:
        search_filter = f"%{search.strip()}%"
        base_query = base_query.where(
            or_(
                Collection.name.ilike(search_filter),
                Collection.created_by.ilike(search_filter),
            )
        )

    total = await db.scalar(select(func.count()).select_from(base_query.subquery()))
    page_query = (
        base_query.order_by(desc(Collection.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(page_query)
    collections = result.scalars().all()

    collection_ids = [str(item.id) for item in collections]
    task_counts: Dict[str, int] = {}
    if collection_ids:
        count_result = await db.execute(
            select(
                CollectionTask.collection_id,
                func.count(CollectionTask.id).label("task_count"),
            )
            .where(CollectionTask.collection_id.in_(collection_ids))
            .group_by(CollectionTask.collection_id)
        )
        task_counts = {
            str(row.collection_id): int(row.task_count) for row in count_result.all()
        }

    return {
        "data": [
            _serialize_collection(item, task_count=task_counts.get(str(item.id), 0))
            for item in collections
        ],
        "pagination": {
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
            "total_pages": (
                ((int(total or 0) + page_size - 1) // page_size) if page_size > 0 else 0
            ),
        },
    }


async def delete_collection_svc(request: Request, collection_id: str) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    username = _resolve_username(request)
    db_collection = await _get_collection_or_404(db, collection_id)
    _check_collection_permission(username, db_collection)

    await db.execute(
        delete(CollectionTask).where(CollectionTask.collection_id == collection_id)
    )
    await db.execute(delete(Collection).where(Collection.id == collection_id))
    return {"message": "Collection deleted successfully"}


async def add_task_to_collection_svc(
    request: Request,
    collection_id: str,
    task_req: CollectionTaskAddRequest,
) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    username = _resolve_username(request)
    db_collection = await _get_collection_or_404(db, collection_id)
    _check_collection_permission(username, db_collection)

    task_type = (task_req.task_type or "").strip().lower()
    if task_type not in {"http", "llm"}:
        raise ErrorResponse.bad_request("task_type must be either 'http' or 'llm'")

    existing = await db.execute(
        select(CollectionTask).where(
            CollectionTask.collection_id == collection_id,
            CollectionTask.task_id == task_req.task_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Task already in collection"}

    if task_type == "http":
        task_exists = await db.scalar(
            select(HttpTask.id).where(HttpTask.id == task_req.task_id)
        )
    else:
        task_exists = await db.scalar(
            select(LlmTask.id).where(LlmTask.id == task_req.task_id)
        )
    if not task_exists:
        raise ErrorResponse.not_found("Task not found")

    db.add(
        CollectionTask(
            collection_id=collection_id,
            task_id=task_req.task_id,
            task_type=task_type,
        )
    )
    await db.flush()
    return {"message": "Task added to collection successfully"}


async def remove_task_from_collection_svc(
    request: Request,
    collection_id: str,
    task_id: str,
) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    username = _resolve_username(request)
    db_collection = await _get_collection_or_404(db, collection_id)
    _check_collection_permission(username, db_collection)

    result = await db.execute(
        delete(CollectionTask).where(
            CollectionTask.collection_id == collection_id,
            CollectionTask.task_id == task_id,
        )
    )
    if not result.rowcount:
        raise ErrorResponse.not_found("Task not found in collection")
    return {"message": "Task removed from collection successfully"}


async def list_collection_tasks_svc(
    request: Request, collection_id: str
) -> Dict[str, Any]:
    db: AsyncSession = request.state.db
    await _get_collection_or_404(db, collection_id)

    relation_result = await db.execute(
        select(CollectionTask).where(CollectionTask.collection_id == collection_id)
    )
    collection_tasks = relation_result.scalars().all()

    http_task_ids = [
        item.task_id for item in collection_tasks if item.task_type == "http"
    ]
    llm_task_ids = [
        item.task_id for item in collection_tasks if item.task_type == "llm"
    ]

    result_tasks: list[Dict[str, Any]] = []
    if http_task_ids:
        http_result = await db.execute(
            select(HttpTask).where(HttpTask.id.in_(http_task_ids))
        )
        for task in http_result.scalars().all():
            result_tasks.append(
                {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "task_type": "http",
                    "created_by": task.created_by,
                    "created_at": str(task.created_at),
                    "concurrent_users": task.concurrent_users,
                    "duration": task.duration,
                }
            )

    if llm_task_ids:
        llm_result = await db.execute(
            select(LlmTask).where(LlmTask.id.in_(llm_task_ids))
        )
        for task in llm_result.scalars().all():
            result_tasks.append(
                {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "task_type": "llm",
                    "created_by": task.created_by,
                    "created_at": str(task.created_at),
                    "concurrent_users": task.concurrent_users,
                    "duration": task.duration,
                    "model": task.model,
                    "api_type": task.api_type,
                }
            )

    result_tasks.sort(key=lambda item: str(item["created_at"]), reverse=True)
    return {"data": result_tasks}
