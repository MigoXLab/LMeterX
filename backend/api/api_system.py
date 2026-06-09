"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from fastapi import APIRouter, Request

from model.system import (
    AIServiceConfig,
    BatchSystemConfigRequest,
    BatchSystemConfigResponse,
    SystemConfigListResponse,
    SystemConfigRequest,
    SystemConfigResponse,
)
from service.system_service import (
    batch_upsert_system_configs_svc,
    create_system_config_svc,
    delete_system_config_svc,
    get_ai_service_config_svc,
    get_dashboard_stats_svc,
    get_system_configs_internal_svc,
    get_system_configs_svc,
    update_system_config_svc,
)

# Create an API router for system configuration endpoints
router = APIRouter()


@router.get("", response_model=SystemConfigListResponse)
async def get_system_configs(request: Request):
    """
    Get all system configurations for System Configuration page (with masked sensitive values).

    Args:
        request: The incoming request.

    Returns:
        SystemConfigListResponse: The system configurations with masked sensitive values.
    """
    return await get_system_configs_svc(request)


@router.get("/internal", response_model=SystemConfigListResponse)
async def get_system_configs_internal(request: Request):
    """
    Get all system configurations for internal use (with real values, no masking).
    This endpoint is used by analyze_task_svc and _call_ai_service.

    Args:
        request: The incoming request.

    Returns:
        SystemConfigListResponse: The system configurations with real values.
    """
    return await get_system_configs_internal_svc(request)


@router.post("", response_model=SystemConfigResponse)
async def create_system_config(request: Request, config_request: SystemConfigRequest):
    """
    Create a new system configuration.

    Args:
        request: The incoming request.
        config_request: The configuration request.

    Returns:
        SystemConfigResponse: The created configuration.
    """
    return await create_system_config_svc(request, config_request)


@router.put("/{config_key}", response_model=SystemConfigResponse)
async def update_system_config(
    request: Request, config_key: str, config_request: SystemConfigRequest
):
    """
    Update an existing system configuration.

    Args:
        request: The incoming request.
        config_key: The configuration key to update.
        config_request: The configuration request.

    Returns:
        SystemConfigResponse: The updated configuration.
    """
    return await update_system_config_svc(request, config_key, config_request)


@router.post("/batch", response_model=BatchSystemConfigResponse)
async def batch_upsert_system_configs(
    request: Request, batch_request: BatchSystemConfigRequest
):
    """
    Batch create or update system configurations in a single transaction.

    Args:
        request: The incoming request.
        batch_request: The batch configuration request.

    Returns:
        BatchSystemConfigResponse: The batch operation result.
    """
    return await batch_upsert_system_configs_svc(request, batch_request)


@router.delete("/{config_key}")
async def delete_system_config(request: Request, config_key: str):
    """
    Delete a system configuration.

    Args:
        request: The incoming request.
        config_key: The configuration key to delete.

    Returns:
        Dict: Success response.
    """
    return await delete_system_config_svc(request, config_key)


@router.get("/ai-service", response_model=AIServiceConfig)
async def get_ai_service_config(request: Request):
    """
    Get AI service configuration.

    Args:
        request: The incoming request.

    Returns:
        AIServiceConfig: The AI service configuration.
    """
    return await get_ai_service_config_svc(request)


@router.get("/dashboard-stats")
async def get_dashboard_stats(request: Request):
    """
    Get statistics and charts for dashboard.
    """
    return await get_dashboard_stats_svc(request)
