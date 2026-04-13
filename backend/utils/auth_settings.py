"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

_startup_logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_KEYS = {"change-me", "secret", "your-secret-key", ""}

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

    # Service Token for agent/skill programmatic access.
    # When set and LDAP is enabled, requests bearing this token are
    # authenticated as the "agent" service user without JWT decode.
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
    LMETERX_AUTH_TOKEN: str = ""

    # Comma-separated list of admin usernames.
    # Admin users can manage (stop, rename, delete) ALL tasks regardless of ownership.
    # Example: ADMIN_USERNAMES=admin,superuser,john
    ADMIN_USERNAMES: str = ""

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
    Return cached authentication settings with security validation.
    """

    settings = AuthSettings()

    # Skip security checks in testing mode
    if not os.environ.get("TESTING"):
        # Warn if JWT secret key is using an insecure default value
        if settings.JWT_SECRET_KEY in _INSECURE_DEFAULT_KEYS:
            _startup_logger.warning(
                "JWT_SECRET_KEY is using an insecure default value! "
                "Set a strong, unique JWT_SECRET_KEY in your environment."
            )

        # Warn if cookie security settings are not suitable for production
        if settings.LDAP_ENABLED and not settings.JWT_COOKIE_SECURE:
            _startup_logger.warning(
                "JWT_COOKIE_SECURE is False while LDAP auth is enabled. "
                "Set JWT_COOKIE_SECURE=True in production to prevent "
                "cookies from being sent over insecure HTTP connections."
            )

    return settings
