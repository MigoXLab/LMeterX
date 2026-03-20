"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, String, Text, func

from db.mysql import Base


class SystemConfig(Base):
    """
    SQLAlchemy model for storing system configuration in the 'system_config' table.
    """

    __tablename__ = "system_config"
    id = Column(String(40), primary_key=True, index=True)
    config_key = Column(String(100), nullable=False, unique=True)
    config_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SystemConfigRequest(BaseModel):
    """
    Request model for system configuration.

    Attributes:
        config_key: The configuration key.
        config_value: The configuration value.
        description: The configuration description.
    """

    config_key: str = Field(..., description="Configuration key")
    config_value: str = Field(..., description="Configuration value")
    description: Optional[str] = Field(None, description="Configuration description")


class SystemConfigResponse(BaseModel):
    """
    Response model for system configuration.

    Attributes:
        config_key: The configuration key.
        config_value: The configuration value.
        description: The configuration description.
        created_at: The creation timestamp.
        updated_at: The update timestamp.
    """

    config_key: str
    config_value: str
    description: Optional[str] = None
    created_at: str
    updated_at: str


class SystemConfigListResponse(BaseModel):
    """
    Response model for system configuration list.

    Attributes:
        data: List of system configurations.
        status: The status of the response.
        error: An error message if the request failed, otherwise None.
    """

    data: list[SystemConfigResponse]
    status: str
    error: Optional[str] = None


class BatchSystemConfigRequest(BaseModel):
    """
    Request model for batch system configuration operations.

    Attributes:
        configs: List of system configurations to create or update.
    """

    configs: List[SystemConfigRequest] = Field(
        ..., description="List of configurations"
    )


class BatchSystemConfigResponse(BaseModel):
    """
    Response model for batch system configuration operations.

    Attributes:
        data: List of system configurations that were created or updated.
        status: The status of the response.
        error: An error message if the request failed, otherwise None.
    """

    data: list[SystemConfigResponse]
    status: str
    error: Optional[str] = None


class AIServiceConfig(BaseModel):
    """
    AI service configuration model.

    Attributes:
        host: The AI service host URL.
        model: The AI model name.
        api_key: The API key for authentication.
        ssl_verify: Whether to verify SSL certificates when calling the AI service.
    """

    host: str = Field(..., description="AI service host URL")
    model: str = Field(..., description="AI model name")
    api_key: str = Field(..., description="API key for authentication")
    ssl_verify: bool = Field(
        default=True,
        description=(
            "Whether to verify SSL certificates when calling the AI service. "
            "Defaults to True for security. Set to False only for development "
            "or trusted internal environments with self-signed certificates."
        ),
    )
