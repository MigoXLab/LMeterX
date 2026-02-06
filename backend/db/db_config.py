"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve project directories so .env can be found regardless of cwd
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = BACKEND_DIR / ".env"


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
    DB_NAME: str = os.environ.get("DB_NAME", "lmeterx")

    # Connection pool settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    # Recycle connections every 4 minutes (240s) to avoid idle timeout issues
    # This is more aggressive than the previous 300s to handle:
    # - Firewall/load balancer TCP timeouts (typically 60-300s)
    # - Cloud database idle timeouts (e.g., Aliyun RDS)
    # - Network device connection tracking timeouts
    DB_POOL_RECYCLE: int = 240

    class Config:
        """
        Pydantic settings configuration.
        """

        env_file = str(ENV_FILE_PATH)
        case_sensitive = True
        extra = "ignore"


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
