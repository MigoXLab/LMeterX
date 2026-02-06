"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

# Resolve project directories so .env can be found regardless of cwd
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = BACKEND_DIR / ".env"


class AuthSettings(BaseSettings):
    """
    Settings for JWT issuance and LDAP/AD integration.
    """

    JWT_SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 7 * 24 * 60
    JWT_ISSUER: str = "lmeterx"

    # Cookie-based auth toggles (used to deliver tokens as HttpOnly cookies)
    JWT_COOKIE_NAME: str = "access_token"
    JWT_COOKIE_SECURE: bool = False
    JWT_COOKIE_SAMESITE: str = "lax"
    JWT_COOKIE_DOMAIN: Optional[str] = None
    JWT_COOKIE_PATH: str = "/"
    ALLOWED_ORIGINS: Optional[str] = None

    LDAP_SERVER: str = "ldap://localhost"
    LDAP_PORT: int = 389
    LDAP_USE_SSL: bool = False
    LDAP_ENABLED: bool = False
    LDAP_SEARCH_BASE: str = ""
    LDAP_USER_DN_TEMPLATE: str = ""
    LDAP_SEARCH_FILTER: str = "(sAMAccountName={username})"
    LDAP_BIND_DN: str = ""
    LDAP_BIND_PASSWORD: str = ""
    LDAP_TIMEOUT: int = 5

    class Config:
        env_file = str(ENV_FILE_PATH)
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_auth_settings() -> AuthSettings:
    """
    Return cached authentication settings.
    """

    return AuthSettings()
