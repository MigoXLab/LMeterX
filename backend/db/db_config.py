"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class MySqlSettings(BaseSettings):
    """
    Defines MySQL database connection settings.
    It reads configuration from environment variables or a .env file.
    """

    # Database credentials and connection details
    DB_USER: str = os.environ.get("DB_USER", "lmeterx_user")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "lmeterx_password")
    DB_HOST: str = os.environ.get("DB_HOST", "lmeterx_url")
    DB_PORT: int = int(os.environ.get("DB_PORT", 3306))
    DB_NAME: str = os.environ.get("DB_NAME", "lmeterx_db")

    # Connection pool settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    class Config:
        """
        Pydantic settings configuration.
        """

        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> MySqlSettings:
    """
    Get the application's MySQL settings.

    This function is decorated with @lru_cache to ensure that the settings
    are loaded only once and subsequent calls return the cached instance.

    Returns:
        MySqlSettings: An instance of the MySqlSettings class.
    """
    return MySqlSettings()
