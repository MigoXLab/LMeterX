"""Reusable dataset management with ownership and visibility enforcement."""

import asyncio
import json
import os
import shutil
import uuid
from typing import Any, Dict, List, Optional, cast

from fastapi import Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from model.dataset import (
    Dataset,
    DatasetUpdateRequest,
    normalize_dataset_tags,
    normalize_dataset_types,
)
from service.upload_service import process_dataset_files
from utils.auth import get_current_user
from utils.be_config import DATA_FOLDER, UPLOAD_FOLDER
from utils.error_handler import ErrorResponse
from utils.file_security import safe_join, validate_filename, validate_upload_path
from utils.logger import logger

SYSTEM_DATASET_OWNER = "system"
DEFAULT_SHAREGPT_DATASET_ID = "system-sharegpt-v3-partial"
DEFAULT_SHAREGPT_FILE_NAME = "ShareGPT_V3_partial.jsonl"
DEFAULT_SHAREGPT_RECORD_COUNT = 54987
DEFAULT_SHAREGPT_TAGS = ["文本", "shareGPT"]


def _username(request: Request) -> str:
    user = get_current_user(request)
    return str(user.get("username") or user.get("sub") or user.get("name") or "system")[
        :100
    ]


def _types_from_storage(value: str) -> List[str]:
    return [item for item in (value or "").split(",") if item]


def _tags_from_storage(value: Optional[str]) -> List[str]:
    try:
        tags = json.loads(value or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in tags] if isinstance(tags, list) else []


def _is_system_dataset(dataset: Dataset) -> bool:
    return str(dataset.id) == DEFAULT_SHAREGPT_DATASET_ID


def _serialize(dataset: Dataset, username: str) -> Dict[str, Any]:
    return {
        "id": dataset.id,
        "name": dataset.name,
        "description": dataset.description,
        "file_name": dataset.file_name,
        "file_size": int(dataset.file_size or 0),
        "record_count": int(dataset.record_count or 0),
        "dataset_types": _types_from_storage(dataset.dataset_types),
        "tags": _tags_from_storage(dataset.tags),
        "created_by": "-" if _is_system_dataset(dataset) else dataset.created_by,
        "is_public": bool(dataset.is_public),
        "is_system": _is_system_dataset(dataset),
        "can_download": dataset.created_by == username
        and not _is_system_dataset(dataset),
        "can_manage": dataset.created_by == username
        and not _is_system_dataset(dataset),
        "created_at": str(dataset.created_at),
        "updated_at": str(dataset.updated_at),
    }


async def _get_dataset(db: AsyncSession, dataset_id: str) -> Dataset:
    result = await db.execute(select(Dataset).where(Dataset.id == dataset_id))
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise ErrorResponse.not_found("Dataset not found")
    return dataset


def _require_visible(dataset: Dataset, username: str) -> None:
    if dataset.created_by != username and not bool(dataset.is_public):
        # Do not reveal the existence of another user's private dataset.
        raise ErrorResponse.not_found("Dataset not found")


def _require_owner(dataset: Dataset, username: str) -> None:
    if _is_system_dataset(dataset):
        raise ErrorResponse.forbidden("System datasets cannot be modified or deleted")
    if dataset.created_by != username:
        raise ErrorResponse.forbidden(
            "Only the dataset creator can perform this action"
        )


def _validate_jsonl(file_path: str) -> int:
    count = 0
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ErrorResponse.bad_request(
                        f"Invalid JSONL at line {line_number}: {exc.msg}"
                    ) from exc
                if not isinstance(row, dict):
                    raise ErrorResponse.bad_request(
                        f"Invalid JSONL at line {line_number}: each row must be an object"
                    )
                count += 1
    except UnicodeDecodeError as exc:
        raise ErrorResponse.bad_request("Dataset must be UTF-8 encoded JSONL") from exc
    if count == 0:
        raise ErrorResponse.bad_request(
            "Dataset must contain at least one JSONL record"
        )
    return count


async def ensure_default_datasets(db: AsyncSession) -> None:
    """Idempotently mount the bundled ShareGPT dataset into the dataset library."""
    source_path = os.path.realpath(
        os.getenv(
            "DEFAULT_SHAREGPT_DATASET_PATH",
            os.path.join(DATA_FOLDER, DEFAULT_SHAREGPT_FILE_NAME),
        )
    )
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Default dataset file not found: {source_path}")

    dataset_dir = safe_join(UPLOAD_FOLDER, DEFAULT_SHAREGPT_DATASET_ID)
    destination = safe_join(dataset_dir, DEFAULT_SHAREGPT_FILE_NAME)
    validate_upload_path(destination, UPLOAD_FOLDER)
    os.makedirs(dataset_dir, exist_ok=True)
    source_size = os.path.getsize(source_path)
    if not os.path.isfile(destination) or os.path.getsize(destination) != source_size:
        temporary = f"{destination}.{os.getpid()}.tmp"
        try:
            shutil.copy2(source_path, temporary)
            os.replace(temporary, destination)
        finally:
            if os.path.isfile(temporary):
                os.remove(temporary)

    values = {
        "id": DEFAULT_SHAREGPT_DATASET_ID,
        "name": "ShareGPT V3 Partial",
        "description": "系统预置的公开 ShareGPT 文本数据集",
        "file_name": DEFAULT_SHAREGPT_FILE_NAME,
        "file_path": destination,
        "file_size": source_size,
        "record_count": DEFAULT_SHAREGPT_RECORD_COUNT,
        "dataset_types": "llm",
        "tags": json.dumps(DEFAULT_SHAREGPT_TAGS, ensure_ascii=False),
        "created_by": SYSTEM_DATASET_OWNER,
        "is_public": 1,
    }
    statement = mysql_insert(Dataset).values(**values)
    statement = statement.on_duplicate_key_update(
        name=values["name"],
        description=values["description"],
        file_name=values["file_name"],
        file_path=values["file_path"],
        file_size=values["file_size"],
        record_count=values["record_count"],
        dataset_types=values["dataset_types"],
        tags=values["tags"],
        created_by=values["created_by"],
        is_public=values["is_public"],
    )
    await db.execute(statement)
    await db.commit()
    logger.info("Default dataset mounted: {}", destination)


async def create_dataset_svc(
    request: Request,
    name: str,
    description: Optional[str],
    is_public: bool,
    dataset_types: List[str],
    tags: List[str],
    file: UploadFile,
) -> Dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise ErrorResponse.bad_request("Dataset name is required")
    if len(clean_name) > 255:
        raise ErrorResponse.bad_request("Dataset name must not exceed 255 characters")
    try:
        types = normalize_dataset_types(dataset_types)
    except ValueError as exc:
        raise ErrorResponse.bad_request(str(exc)) from exc
    try:
        normalized_tags = normalize_dataset_tags(tags)
    except ValueError as exc:
        raise ErrorResponse.bad_request(str(exc)) from exc
    clean_description = description.strip() if description else None
    if clean_description and len(clean_description) > 2000:
        raise ErrorResponse.bad_request(
            "Dataset description must not exceed 2000 characters"
        )
    filename = str(file.filename or "")
    extension = os.path.splitext(filename)[1].lower()
    if extension != ".jsonl":
        raise ErrorResponse.bad_request("Only .jsonl dataset files are supported")
    try:
        original_file_name = validate_filename(filename)
    except ValueError as exc:
        raise ErrorResponse.bad_request(str(exc)) from exc

    dataset_id = str(uuid.uuid4())
    # Keep the original name as metadata while guaranteeing an ASCII execution
    # path (secure_filename may strip a non-ASCII basename entirely).
    file.filename = f"{dataset_id}{extension}"
    uploaded_files, file_path = await process_dataset_files(dataset_id, [file])
    if not file_path or not uploaded_files:
        raise ErrorResponse.internal_server_error("Dataset upload failed")

    try:
        record_count = await asyncio.to_thread(_validate_jsonl, file_path)
        dataset = Dataset(
            id=dataset_id,
            name=clean_name,
            description=clean_description,
            file_name=original_file_name,
            file_path=file_path,
            file_size=uploaded_files[0]["size"],
            record_count=record_count,
            dataset_types=",".join(types),
            tags=json.dumps(normalized_tags, ensure_ascii=False),
            created_by=_username(request),
            is_public=1 if is_public else 0,
        )
        db: AsyncSession = request.state.db
        db.add(dataset)
        await db.flush()
        await db.refresh(dataset)
        return _serialize(dataset, _username(request))
    except Exception:
        if os.path.isfile(file_path):
            os.remove(file_path)
        try:
            os.rmdir(os.path.dirname(file_path))
        except OSError:
            pass
        raise


async def list_datasets_svc(
    request: Request,
    page: int,
    page_size: int,
    search: Optional[str] = None,
    dataset_type: Optional[str] = None,
) -> Dict[str, Any]:
    username = _username(request)
    db: AsyncSession = request.state.db
    query = select(Dataset).where(
        or_(Dataset.is_public == 1, Dataset.created_by == username)
    )
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Dataset.name.ilike(term),
                Dataset.created_by.ilike(term),
                Dataset.tags.ilike(term),
            )
        )
    if dataset_type:
        try:
            normalized = normalize_dataset_types([dataset_type])[0]
        except ValueError as exc:
            raise ErrorResponse.bad_request(str(exc)) from exc
        # Comma boundaries prevent "llm" from matching unrelated future labels.
        query = query.where(func.find_in_set(normalized, Dataset.dataset_types) > 0)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(desc(Dataset.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "data": [_serialize(item, username) for item in result.scalars().all()],
        "pagination": {
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
            "total_pages": (int(total or 0) + page_size - 1) // page_size,
        },
    }


async def get_dataset_svc(request: Request, dataset_id: str) -> Dict[str, Any]:
    username = _username(request)
    dataset = await _get_dataset(request.state.db, dataset_id)
    _require_visible(dataset, username)
    return _serialize(dataset, username)


async def update_dataset_svc(
    request: Request, dataset_id: str, payload: DatasetUpdateRequest
) -> Dict[str, Any]:
    username = _username(request)
    dataset = await _get_dataset(request.state.db, dataset_id)
    _require_owner(dataset, username)
    target = cast(Any, dataset)
    if payload.name is not None:
        target.name = payload.name
    if payload.description is not None:
        target.description = payload.description.strip() or None
    if payload.is_public is not None:
        target.is_public = 1 if payload.is_public else 0
    if payload.dataset_types is not None:
        target.dataset_types = ",".join(payload.dataset_types)
    if payload.tags is not None:
        target.tags = json.dumps(payload.tags, ensure_ascii=False)
    await request.state.db.flush()
    await request.state.db.refresh(dataset)
    return _serialize(dataset, username)


async def delete_dataset_svc(request: Request, dataset_id: str) -> Dict[str, str]:
    username = _username(request)
    db: AsyncSession = request.state.db
    dataset = await _get_dataset(db, dataset_id)
    _require_owner(dataset, username)
    file_path = os.path.realpath(str(dataset.file_path))
    validate_upload_path(file_path, UPLOAD_FOLDER)
    await db.delete(dataset)
    await db.flush()
    if os.path.isfile(file_path):
        os.remove(file_path)
    try:
        os.rmdir(os.path.dirname(file_path))
    except OSError:
        pass
    return {"message": "Dataset deleted successfully"}


async def download_dataset_svc(request: Request, dataset_id: str) -> FileResponse:
    username = _username(request)
    dataset = await _get_dataset(request.state.db, dataset_id)
    if _is_system_dataset(dataset):
        raise ErrorResponse.forbidden("System datasets cannot be downloaded")
    _require_owner(dataset, username)
    file_path = os.path.realpath(str(dataset.file_path))
    validate_upload_path(file_path, UPLOAD_FOLDER)
    if not os.path.isfile(file_path):
        raise ErrorResponse.not_found("Dataset file not found")
    return FileResponse(
        file_path,
        media_type="application/x-ndjson",
        filename=str(dataset.file_name),
    )


async def resolve_dataset_for_task(
    request: Request,
    dataset_id: Optional[str],
    required_type: str,
    task_id: str,
) -> Optional[str]:
    """Authorize a dataset and create a task-owned execution copy."""
    if not dataset_id:
        return None
    username = _username(request)
    dataset = await _get_dataset(request.state.db, dataset_id)
    _require_visible(dataset, username)
    if required_type not in _types_from_storage(str(dataset.dataset_types)):
        raise ErrorResponse.bad_request(
            f"Dataset is not marked for {required_type} tasks"
        )
    file_path = os.path.realpath(str(dataset.file_path))
    validate_upload_path(file_path, UPLOAD_FOLDER)
    if not os.path.isfile(file_path):
        raise ErrorResponse.not_found("Dataset file not found")
    return await _copy_dataset_for_task(dataset, file_path, task_id)


async def _copy_dataset_for_task(
    dataset: Dataset, source_path: str, task_id: str
) -> str:
    task_dir = safe_join(UPLOAD_FOLDER, task_id)
    validate_upload_path(task_dir, UPLOAD_FOLDER)
    os.makedirs(task_dir, exist_ok=True)
    destination = safe_join(task_dir, str(dataset.file_name))
    validate_upload_path(destination, UPLOAD_FOLDER)
    try:
        shutil.copy2(source_path, destination)

        # Multi-cluster execution retrieves uploaded files by upload_files key.
        from service.oss_service import OSS_ENABLED, upload_file_to_oss

        if OSS_ENABLED:
            relative_path = os.path.relpath(destination, UPLOAD_FOLDER)
            uploaded = await upload_file_to_oss(
                destination, f"upload_files/{relative_path}"
            )
            if not uploaded:
                raise ErrorResponse.internal_server_error(
                    "Failed to prepare dataset for remote execution"
                )
    except Exception:
        if os.path.isfile(destination):
            os.remove(destination)
        try:
            os.rmdir(task_dir)
        except OSError:
            pass
        raise
    return destination


async def authorize_managed_dataset_path(
    request: Request,
    candidate_path: Optional[str],
    required_type: str,
    task_id: str,
) -> Optional[str]:
    """Protect managed files even if a client submits a guessed storage path."""
    if not candidate_path or not candidate_path.lower().endswith(".jsonl"):
        return None
    real_path = os.path.realpath(candidate_path)
    try:
        validate_upload_path(real_path, UPLOAD_FOLDER)
    except ValueError:
        return None  # Existing task APIs validate legacy inputs separately.
    result = await request.state.db.execute(
        select(Dataset).where(Dataset.file_path == real_path)
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        return None
    username = _username(request)
    _require_visible(dataset, username)
    if required_type not in _types_from_storage(str(dataset.dataset_types)):
        raise ErrorResponse.bad_request(
            f"Dataset is not marked for {required_type} tasks"
        )
    if not os.path.isfile(real_path):
        raise ErrorResponse.not_found("Dataset file not found")
    return await _copy_dataset_for_task(dataset, real_path, task_id)
