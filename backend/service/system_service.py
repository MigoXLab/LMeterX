"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import uuid
from typing import Dict, List, Optional

from fastapi import HTTPException, Request
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
from utils.tools import mask_api_key, mask_config_value


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
        config_query = select(SystemConfig)
        config_result = await db.execute(config_query)
        configs = config_result.scalars().all()

        config_responses = []
        for config in configs:
            config_key = str(config.config_key) if config.config_key is not None else ""
            config_value = (
                str(config.config_value) if config.config_value is not None else ""
            )

            # Mask sensitive configuration values for System Configuration page
            masked_value = mask_config_value(config_key, config_value)

            config_responses.append(
                SystemConfigResponse(
                    config_key=config_key,
                    config_value=masked_value,
                    description=(
                        str(config.description)
                        if config.description is not None
                        else None
                    ),
                    created_at=(
                        config.created_at.isoformat() if config.created_at else ""
                    ),
                    updated_at=(
                        config.updated_at.isoformat() if config.updated_at else ""
                    ),
                )
            )

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
        config_query = select(SystemConfig)
        config_result = await db.execute(config_query)
        configs = config_result.scalars().all()

        config_responses = []
        for config in configs:
            config_key = str(config.config_key) if config.config_key is not None else ""
            config_value = (
                str(config.config_value) if config.config_value is not None else ""
            )

            # Return real values for internal use (no masking)
            config_responses.append(
                SystemConfigResponse(
                    config_key=config_key,
                    config_value=config_value,
                    description=(
                        str(config.description)
                        if config.description is not None
                        else None
                    ),
                    created_at=(
                        config.created_at.isoformat() if config.created_at else ""
                    ),
                    updated_at=(
                        config.updated_at.isoformat() if config.updated_at else ""
                    ),
                )
            )

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
        HTTPException: If the configuration already exists.
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
            raise HTTPException(
                status_code=400, detail=ErrorMessages.CONFIG_ALREADY_EXISTS
            )

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

        # Return masked value for response (for security)
        config_key_str = str(config.config_key) if config.config_key is not None else ""
        config_value_str = (
            str(config.config_value) if config.config_value is not None else ""
        )
        masked_value = mask_config_value(config_key_str, config_value_str)

        return SystemConfigResponse(
            config_key=config_key_str,
            config_value=masked_value,
            description=(
                str(config.description) if config.description is not None else None
            ),
            created_at=config.created_at.isoformat() if config.created_at else "",
            updated_at=config.updated_at.isoformat() if config.updated_at else "",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create system config: {}", e)
        raise HTTPException(status_code=500, detail=ErrorMessages.TASK_CREATION_FAILED)


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
        HTTPException: If the configuration doesn't exist.
    """
    db: AsyncSession = request.state.db

    try:
        # Find existing config
        config_query = select(SystemConfig).where(SystemConfig.config_key == config_key)
        config_result = await db.execute(config_query)
        config = config_result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")

        # Update config - store original payload without encryption
        setattr(
            config, "config_value", config_request.config_value
        )  # Store original value
        if config_request.description is not None:
            setattr(config, "description", config_request.description)

        await db.commit()
        await db.refresh(config)

        # Return masked value for response (for security)
        config_key_str = str(config.config_key) if config.config_key is not None else ""
        config_value_str = (
            str(config.config_value) if config.config_value is not None else ""
        )
        masked_value = mask_config_value(config_key_str, config_value_str)

        return SystemConfigResponse(
            config_key=config_key_str,
            config_value=masked_value,
            description=(
                str(config.description) if config.description is not None else None
            ),
            created_at=config.created_at.isoformat() if config.created_at else "",
            updated_at=config.updated_at.isoformat() if config.updated_at else "",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update system config: {}", e)
        raise HTTPException(status_code=500, detail=ErrorMessages.TASK_UPDATE_FAILED)


async def delete_system_config_svc(request: Request, config_key: str) -> Dict:
    """
    Delete a system configuration.

    Args:
        request: The incoming request.
        config_key: The configuration key to delete.

    Returns:
        Dict: Success response.

    Raises:
        HTTPException: If the configuration doesn't exist.
    """
    db: AsyncSession = request.state.db

    try:
        # Find existing config
        config_query = select(SystemConfig).where(SystemConfig.config_key == config_key)
        config_result = await db.execute(config_query)
        config = config_result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail=ErrorMessages.CONFIG_NOT_FOUND)

        # Delete config
        await db.delete(config)
        await db.commit()

        return {"status": "success", "message": "Configuration deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete system config: {}", e)
        raise HTTPException(status_code=500, detail=ErrorMessages.TASK_DELETION_FAILED)


async def get_ai_service_config_svc(request: Request) -> AIServiceConfig:
    """
    Get AI service configuration for API responses (with masked API key).

    Args:
        request: The incoming request.

    Returns:
        AIServiceConfig: The AI service configuration with masked API key.

    Raises:
        HTTPException: If the configuration is incomplete.
    """
    db: AsyncSession = request.state.db

    try:
        # Get AI service configs
        config_keys = ["ai_service_host", "ai_service_model", "ai_service_api_key"]
        configs = {}

        for key in config_keys:
            config_query = select(SystemConfig).where(SystemConfig.config_key == key)
            config_result = await db.execute(config_query)
            config = config_result.scalar_one_or_none()
            configs[key] = config.config_value if config else None

        # Check if all required configs exist
        missing_configs = [key for key, value in configs.items() if not value]
        if missing_configs:
            raise HTTPException(
                status_code=400,
                detail=f"{ErrorMessages.MISSING_AI_CONFIG}: {', '.join(missing_configs)}",
            )

        api_key_value = (
            str(configs["ai_service_api_key"])
            if configs["ai_service_api_key"] is not None
            else ""
        )

        return AIServiceConfig(
            host=(
                str(configs["ai_service_host"])
                if configs["ai_service_host"] is not None
                else ""
            ),
            model=(
                str(configs["ai_service_model"])
                if configs["ai_service_model"] is not None
                else ""
            ),
            api_key=mask_api_key(api_key_value),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get AI service config: {}", e)
        raise HTTPException(status_code=500, detail=ErrorMessages.DATABASE_ERROR)


async def get_ai_service_config_internal_svc(request: Request) -> AIServiceConfig:
    """
    Get AI service configuration for internal use (with real API key).

    Args:
        request: The incoming request.

    Returns:
        AIServiceConfig: The AI service configuration with real API key.

    Raises:
        HTTPException: If the configuration is incomplete.
    """
    db: AsyncSession = request.state.db

    try:
        # Get AI service configs
        config_keys = ["ai_service_host", "ai_service_model", "ai_service_api_key"]
        configs = {}

        for key in config_keys:
            config_query = select(SystemConfig).where(SystemConfig.config_key == key)
            config_result = await db.execute(config_query)
            config = config_result.scalar_one_or_none()
            configs[key] = config.config_value if config else None

        # Check if all required configs exist
        missing_configs = [key for key, value in configs.items() if not value]
        if missing_configs:
            raise HTTPException(
                status_code=400,
                detail=f"{ErrorMessages.MISSING_AI_CONFIG}: {', '.join(missing_configs)}",
            )

        api_key_value = (
            str(configs["ai_service_api_key"])
            if configs["ai_service_api_key"] is not None
            else ""
        )
        return AIServiceConfig(
            host=(
                str(configs["ai_service_host"])
                if configs["ai_service_host"] is not None
                else ""
            ),
            model=(
                str(configs["ai_service_model"])
                if configs["ai_service_model"] is not None
                else ""
            ),
            api_key=api_key_value,  # Return real API key for internal use
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get AI service config: {}", e)
        raise HTTPException(status_code=500, detail=ErrorMessages.DATABASE_ERROR)


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

                # Return masked value for response (for security)
                config_key_str = (
                    str(config.config_key) if config.config_key is not None else ""
                )
                config_value_str = (
                    str(config.config_value) if config.config_value is not None else ""
                )
                masked_value = mask_config_value(config_key_str, config_value_str)

                config_responses.append(
                    SystemConfigResponse(
                        config_key=config_key_str,
                        config_value=masked_value,
                        description=(
                            str(config.description)
                            if config.description is not None
                            else None
                        ),
                        created_at=(
                            config.created_at.isoformat() if config.created_at else ""
                        ),
                        updated_at=(
                            config.updated_at.isoformat() if config.updated_at else ""
                        ),
                    )
                )

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
