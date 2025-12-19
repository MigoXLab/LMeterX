"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import uuid
from typing import Any, Dict, List, Optional, Sequence

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from model.system import (
    AIServiceConfig,
    BatchSystemConfigRequest,
    BatchSystemConfigResponse,
    SystemConfig,
    SystemConfigListResponse,
    SystemConfigRequest,
    SystemConfigResponse,
)
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger
from utils.masking import mask_api_key, mask_config_value

AI_CONFIG_KEYS = ("ai_service_host", "ai_service_model", "ai_service_api_key")


def _to_string(value: Optional[Any]) -> str:
    return str(value) if value is not None else ""


def _build_config_response(
    config: SystemConfig, *, mask_sensitive: bool = True
) -> SystemConfigResponse:
    config_key = _to_string(config.config_key)
    raw_value = _to_string(config.config_value)
    config_value = (
        mask_config_value(config_key, raw_value) if mask_sensitive else raw_value
    )

    return SystemConfigResponse(
        config_key=config_key,
        config_value=config_value,
        description=(
            _to_string(config.description) if config.description is not None else None
        ),
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else "",
    )


async def _fetch_all_configs(db: AsyncSession) -> List[SystemConfig]:
    config_query = select(SystemConfig)
    config_result = await db.execute(config_query)
    configs = config_result.scalars().all()
    return list(configs)


async def _fetch_configs_by_keys(
    db: AsyncSession, keys: Sequence[str]
) -> Dict[str, SystemConfig]:
    config_query = select(SystemConfig).where(SystemConfig.config_key.in_(keys))
    config_result = await db.execute(config_query)
    config_objects = config_result.scalars().all()
    return {_to_string(config.config_key): config for config in config_objects}


async def _resolve_ai_service_configs(db: AsyncSession) -> Dict[str, str]:
    configs = await _fetch_configs_by_keys(db, AI_CONFIG_KEYS)

    resolved: Dict[str, str] = {}
    missing_configs = []

    for key in AI_CONFIG_KEYS:
        config = configs.get(key)
        value = (
            _to_string(config.config_value) if config and config.config_value else ""
        )
        if not value:
            missing_configs.append(key)
        else:
            resolved[key] = value

    if missing_configs:
        raise ErrorResponse.bad_request(
            f"{ErrorMessages.MISSING_AI_CONFIG}: {', '.join(missing_configs)}"
        )

    return resolved


async def get_system_configs_svc(request: Request) -> SystemConfigListResponse:
    """
    Get all system configurations for System Configuration page (with masked API keys).

    Args:
        request: The incoming request.

    Returns:
        SystemConfigListResponse: The system configurations with masked sensitive values.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _fetch_all_configs(db)
        config_responses = [
            _build_config_response(config, mask_sensitive=True) for config in configs
        ]

        return SystemConfigListResponse(
            data=config_responses,
            status="success",
            error=None,
        )

    except Exception as e:
        logger.warning("Failed to get system configs: {}", e)
        return SystemConfigListResponse(
            data=[],
            status="success",
            error=ErrorMessages.DATABASE_ERROR,
        )


async def get_system_configs_internal_svc(request: Request) -> SystemConfigListResponse:
    """
    Get all system configurations for internal use (with real values, no masking).

    Args:
        request: The incoming request.

    Returns:
        SystemConfigListResponse: The system configurations with real values.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _fetch_all_configs(db)
        config_responses = [
            _build_config_response(config, mask_sensitive=False) for config in configs
        ]

        return SystemConfigListResponse(
            data=config_responses,
            status="success",
            error=None,
        )

    except Exception as e:
        logger.error("Failed to get system configs: {}", e)
        return SystemConfigListResponse(
            data=[],
            status="error",
            error=ErrorMessages.DATABASE_ERROR,
        )


async def create_system_config_svc(
    request: Request, config_request: SystemConfigRequest
) -> SystemConfigResponse:
    """
    Create a new system configuration.

    Args:
        request: The incoming request.
        config_request: The configuration request.

    Returns:
        SystemConfigResponse: The created configuration.

    Raises:
        ErrorResponse: If the configuration already exists or persistence fails.
    """
    db: AsyncSession = request.state.db

    try:
        # Check if config already exists
        existing_query = select(SystemConfig).where(
            SystemConfig.config_key == config_request.config_key
        )
        existing_result = await db.execute(existing_query)
        existing_config = existing_result.scalar_one_or_none()

        if existing_config:
            raise ErrorResponse.bad_request(ErrorMessages.CONFIG_ALREADY_EXISTS)

        # Create new config - store original payload without encryption
        config_id = str(uuid.uuid4())
        config = SystemConfig(
            id=config_id,
            config_key=config_request.config_key,
            config_value=config_request.config_value,  # Store original value
            description=config_request.description,
        )

        db.add(config)
        await db.commit()
        await db.refresh(config)

        return _build_config_response(config)

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to create system config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_CREATION_FAILED)


async def update_system_config_svc(
    request: Request, config_key: str, config_request: SystemConfigRequest
) -> SystemConfigResponse:
    """
    Update an existing system configuration.

    Args:
        request: The incoming request.
        config_key: The configuration key to update.
        config_request: The configuration request.

    Returns:
        SystemConfigResponse: The updated configuration.

    Raises:
        ErrorResponse: If the configuration doesn't exist or persistence fails.
    """
    db: AsyncSession = request.state.db

    try:
        # Find existing config
        config_query = select(SystemConfig).where(SystemConfig.config_key == config_key)
        config_result = await db.execute(config_query)
        config = config_result.scalar_one_or_none()

        if not config:
            raise ErrorResponse.not_found("Configuration not found")

        # Update config - store original payload without encryption
        setattr(
            config, "config_value", config_request.config_value
        )  # Store original value
        if config_request.description is not None:
            setattr(config, "description", config_request.description)

        await db.commit()
        await db.refresh(config)

        return _build_config_response(config)

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to update system config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_UPDATE_FAILED)


async def delete_system_config_svc(request: Request, config_key: str) -> Dict:
    """
    Delete a system configuration.

    Args:
        request: The incoming request.
        config_key: The configuration key to delete.

    Returns:
        Dict: Success response.

    Raises:
        ErrorResponse: If the configuration doesn't exist or deletion fails.
    """
    db: AsyncSession = request.state.db

    try:
        # Find existing config
        config_query = select(SystemConfig).where(SystemConfig.config_key == config_key)
        config_result = await db.execute(config_query)
        config = config_result.scalar_one_or_none()

        if not config:
            raise ErrorResponse.not_found(ErrorMessages.CONFIG_NOT_FOUND)

        # Delete config
        await db.delete(config)
        await db.commit()

        return {"status": "success", "message": "Configuration deleted successfully"}

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to delete system config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_DELETION_FAILED)


async def get_ai_service_config_svc(request: Request) -> AIServiceConfig:
    """
    Get AI service configuration for API responses (with masked API key).

    Args:
        request: The incoming request.

    Returns:
        AIServiceConfig: The AI service configuration with masked API key.

    Raises:
        ErrorResponse: If the configuration is incomplete or query fails.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _resolve_ai_service_configs(db)
        return AIServiceConfig(
            host=configs["ai_service_host"],
            model=configs["ai_service_model"],
            api_key=mask_api_key(configs["ai_service_api_key"]),
        )

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to get AI service config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.DATABASE_ERROR)


async def get_ai_service_config_internal_svc(request: Request) -> AIServiceConfig:
    """
    Get AI service configuration for internal use (with real API key).

    Args:
        request: The incoming request.

    Returns:
        AIServiceConfig: The AI service configuration with real API key.

    Raises:
        ErrorResponse: If the configuration is incomplete or query fails.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _resolve_ai_service_configs(db)
        return AIServiceConfig(
            host=configs["ai_service_host"],
            model=configs["ai_service_model"],
            api_key=configs["ai_service_api_key"],
        )

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to get AI service config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.DATABASE_ERROR)


async def batch_upsert_system_configs_svc(
    request: Request, batch_request: BatchSystemConfigRequest
) -> BatchSystemConfigResponse:
    """
    Batch create or update system configurations in a single transaction.

    Args:
        request: The incoming request.
        batch_request: The batch configuration request.

    Returns:
        BatchSystemConfigResponse: The batch operation result.
    """
    db: AsyncSession = request.state.db

    try:
        config_responses = []

        # Start transaction
        async with db.begin():
            for config_request in batch_request.configs:
                # Check if config already exists
                existing_query = select(SystemConfig).where(
                    SystemConfig.config_key == config_request.config_key
                )
                existing_result = await db.execute(existing_query)
                existing_config = existing_result.scalar_one_or_none()

                if existing_config:
                    # Update existing config
                    setattr(
                        existing_config, "config_value", config_request.config_value
                    )
                    if config_request.description is not None:
                        setattr(
                            existing_config, "description", config_request.description
                        )

                    config = existing_config
                else:
                    # Create new config
                    config_id = str(uuid.uuid4())
                    config = SystemConfig(
                        id=config_id,
                        config_key=config_request.config_key,
                        config_value=config_request.config_value,
                        description=config_request.description,
                    )
                    db.add(config)

                # Refresh to get updated data
                await db.flush()
                await db.refresh(config)

                config_responses.append(_build_config_response(config))

        return BatchSystemConfigResponse(
            data=config_responses,
            status="success",
            error=None,
        )

    except Exception as e:
        logger.error("Failed to batch upsert system configs: {}", e)
        return BatchSystemConfigResponse(
            data=[],
            status="error",
            error=ErrorMessages.DATABASE_ERROR,
        )
