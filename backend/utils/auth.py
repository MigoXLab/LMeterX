"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt
from fastapi import Request

from utils.auth_settings import get_auth_settings
from utils.error_handler import ErrorMessages, ErrorResponse

settings = get_auth_settings()


def create_access_token(user_payload: Dict[str, Any]) -> str:
    """
    Create a signed JWT for the given user payload.
    """

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_payload.get("username") or user_payload.get("sub"),
        "name": user_payload.get("display_name") or user_payload.get("name"),
        "email": user_payload.get("email"),
        "iss": settings.JWT_ISSUER,
        "exp": expire,
    }

    return jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Validate and decode a JWT, raising standardized errors when invalid.
    """

    try:
        payload: Dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iss", "sub"]},
            issuer=settings.JWT_ISSUER,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise ErrorResponse.unauthorized(ErrorMessages.TOKEN_EXPIRED)
    except jwt.InvalidTokenError:
        raise ErrorResponse.unauthorized(ErrorMessages.UNAUTHORIZED)


def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Retrieve the authenticated user info from request state.
    """

    if not settings.LDAP_ENABLED:
        return {"username": "-", "display_name": "-", "email": None}

    user = getattr(request.state, "user", None)
    if not user:
        raise ErrorResponse.unauthorized(ErrorMessages.UNAUTHORIZED)
    return user
