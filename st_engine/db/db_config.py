"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


def get_env_int(key: str, default: int) -> int:
    """
    Get an integer value from environment variable with fallback to default.

    Args:
        key (str): Environment variable key
        default (int): Default value to use if env var is empty or invalid

    Returns:
        int: The environment variable value as integer or default value
    """
    value = os.environ.get(key, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_env_str(key: str, default: str) -> str:
    """
    Get a string value from environment variable with fallback to default.

    Args:
        key (str): Environment variable key
        default (str): Default value to use if env var is empty

    Returns:
        str: The environment variable value or default value
    """
    value = os.environ.get(key, "").strip()
    return value if value else default


ENGINE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = ENGINE_DIR / ".env"


class MySqlSettings(BaseSettings):
    """
    Pydantic model for MySQL database settings.

    Attributes:
        DB_USER (str): The username for the database connection.
        DB_PASSWORD (str): The password for the database connection.
        DB_HOST (str): The host of the database server.
        DB_PORT (int): The port number of the database server.
        DB_NAME (str): The name of the database.
        DB_POOL_SIZE (int): The initial number of connections to keep in the pool.
        DB_MAX_OVERFLOW (int): The maximum number of connections allowed beyond the pool size.
        DB_POOL_TIMEOUT (int): The timeout in seconds for getting a connection from the pool.
        DB_POOL_RECYCLE (int): The time in seconds after which a connection is recycled.
    """

    # --- Database Connection Settings ---
    DB_USER: str = Field(default="lmeterx_user")
    DB_PASSWORD: str = Field(default="lmeterx_password")
    DB_HOST: str = Field(default="lmeterx_url")
    DB_PORT: int = Field(default=3306)
    DB_NAME: str = Field(default="lmeterx")

    # --- Connection Pool Settings ---
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # Recycle connections after 30 minutes

    @model_validator(mode="before")
    @classmethod
    def validate_env_vars(cls, values: Any) -> Dict[str, Any]:
        """
        Validate environment variables and provide defaults for empty or invalid values.

        Args:
            values: The input values from environment variables

        Returns:
            Dict[str, Any]: The validated values with defaults applied
        """
        if not isinstance(values, dict):
            values = {}

        # Define default values
        defaults = {
            "DB_USER": "lmeterx_user",
            "DB_PASSWORD": "lmeterx_password",
            "DB_HOST": "lmeterx_url",
            "DB_PORT": 3306,
            "DB_NAME": "lmeterx",
        }

        # Process each field
        for field_name, default_value in defaults.items():
            env_value = values.get(field_name)

            # Handle string fields
            if field_name in ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_NAME"]:
                if env_value is None or (
                    isinstance(env_value, str) and not env_value.strip()
                ):
                    values[field_name] = default_value
                else:
                    values[field_name] = str(env_value).strip()

            # Handle DB_PORT field
            elif field_name == "DB_PORT":
                if env_value is None or (
                    isinstance(env_value, str) and not env_value.strip()
                ):
                    values[field_name] = default_value
                else:
                    try:
                        port = int(env_value)
                        if 1 <= port <= 65535:
                            values[field_name] = port
                        else:
                            values[field_name] = default_value
                    except (ValueError, TypeError):
                        values[field_name] = default_value

        return values

    class Config:
        """Pydantic configuration options."""

        env_file = str(ENV_FILE_PATH)
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> MySqlSettings:
    """
    Returns a cached instance of the MySqlSettings.

    The `lru_cache` decorator ensures that the settings are loaded only once,
    improving performance by avoiding repeated file I/O and environment variable reads.
    """
    return MySqlSettings()
