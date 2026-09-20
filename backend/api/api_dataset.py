"""Reusable dataset HTTP API."""

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from model.dataset import DatasetUpdateRequest
from service.dataset_service import (
    create_dataset_svc,
    delete_dataset_svc,
    download_dataset_svc,
    get_dataset_svc,
    list_datasets_svc,
    update_dataset_svc,
)
from utils.error_handler import ErrorResponse

router = APIRouter()


@router.post("", response_model=Dict[str, Any])
async def create_dataset(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    is_public: bool = Form(False),
    dataset_types: str = Form(...),
    tags: str = Form("[]"),
    file: UploadFile = File(...),
):
    try:
        parsed_types = json.loads(dataset_types)
    except json.JSONDecodeError:
        parsed_types = [item.strip() for item in dataset_types.split(",")]
    if not isinstance(parsed_types, list):
        raise ErrorResponse.bad_request("dataset_types must be a JSON array")
    try:
        parsed_tags = json.loads(tags)
    except json.JSONDecodeError:
        parsed_tags = [item.strip() for item in tags.split(",")]
    if not isinstance(parsed_tags, list):
        raise ErrorResponse.bad_request("tags must be a JSON array")
    return await create_dataset_svc(
        request, name, description, is_public, parsed_types, parsed_tags, file
    )


@router.get("", response_model=Dict[str, Any])
async def list_datasets(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    dataset_type: Optional[str] = None,
):
    return await list_datasets_svc(request, page, page_size, search, dataset_type)


@router.get("/{dataset_id}", response_model=Dict[str, Any])
async def get_dataset(request: Request, dataset_id: str):
    return await get_dataset_svc(request, dataset_id)


@router.put("/{dataset_id}", response_model=Dict[str, Any])
async def update_dataset(
    request: Request, dataset_id: str, payload: DatasetUpdateRequest
):
    return await update_dataset_svc(request, dataset_id, payload)


@router.delete("/{dataset_id}", response_model=Dict[str, str])
async def delete_dataset(request: Request, dataset_id: str):
    return await delete_dataset_svc(request, dataset_id)


@router.get("/{dataset_id}/download", response_class=FileResponse)
async def download_dataset(request: Request, dataset_id: str):
    return await download_dataset_svc(request, dataset_id)
