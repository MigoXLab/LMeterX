"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Literal, Optional, cast

from fastapi import APIRouter, Request, Response

from model.auth import LoginRequest, LoginResponse, UserInfo
from service.auth_service import login_with_ldap
from utils.auth import get_current_user
from utils.auth_settings import get_auth_settings
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger

router = APIRouter()
settings = get_auth_settings()


def _resolve_samesite() -> Optional[Literal["lax", "strict", "none"]]:
    """
    Return a type-safe SameSite value compatible with FastAPI typing.
    """

    if not settings.JWT_COOKIE_SAMESITE:
        return None
    lowered = settings.JWT_COOKIE_SAMESITE.lower()
    if lowered in {"lax", "strict", "none"}:
        return cast(Literal["lax", "strict", "none"], lowered)
    return None


def _resolve_cookie_options() -> (
    tuple[Optional[Literal["lax", "strict", "none"]], bool]
):
    """
    Ensure SameSite=None is only used with secure cookies to avoid being dropped
    by modern browsers. When misconfigured, force secure=True to preserve the
    session cookie instead of silently losing it.
    """

    samesite = _resolve_samesite()
    secure = settings.JWT_COOKIE_SECURE
    if samesite == "none" and not secure:
        logger.warning(
            "SameSite=None requires secure cookies; overriding secure flag to True "
            "to prevent browsers from dropping the JWT cookie."
        )
        secure = True
    return samesite, secure


def _set_auth_cookies(response: Response, token: str) -> None:
    """
    Write HttpOnly auth cookie plus a non-sensitive presence cookie used
    by the frontend to detect session state without exposing the token.
    """

    max_age = settings.JWT_EXPIRE_MINUTES * 60
    samesite, secure = _resolve_cookie_options()
    response.set_cookie(
        key=settings.JWT_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=max_age,
        expires=max_age,
        domain=settings.JWT_COOKIE_DOMAIN or None,
        path=settings.JWT_COOKIE_PATH,
        samesite=samesite,
        secure=secure,
    )
    response.set_cookie(
        key=f"{settings.JWT_COOKIE_NAME}_present",
        value="1",
        httponly=False,
        max_age=max_age,
        expires=max_age,
        domain=settings.JWT_COOKIE_DOMAIN or None,
        path=settings.JWT_COOKIE_PATH,
        samesite=samesite,
        secure=secure,
    )


def _clear_auth_cookies(response: Response) -> None:
    """
    Expire authentication cookies on logout or when session is invalidated.
    """

    samesite, secure = _resolve_cookie_options()
    response.delete_cookie(
        key=settings.JWT_COOKIE_NAME,
        domain=settings.JWT_COOKIE_DOMAIN or None,
        path=settings.JWT_COOKIE_PATH,
        samesite=samesite,
        secure=secure,
    )
    response.delete_cookie(
        key=f"{settings.JWT_COOKIE_NAME}_present",
        domain=settings.JWT_COOKIE_DOMAIN or None,
        path=settings.JWT_COOKIE_PATH,
        samesite=samesite,
        secure=secure,
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, login_request: LoginRequest, response: Response):
    """
    Authenticate against LDAP/AD and issue JWT.
    """

    if not settings.LDAP_ENABLED:
        raise ErrorResponse.bad_request(
            ErrorMessages.LDAP_DISABLED,
            details="LDAP is disabled. Set LDAP_ENABLED=on to enable.",
        )

    payload = await login_with_ldap(request, login_request)
    _set_auth_cookies(response, payload.access_token)
    return payload


@router.post("/logout")
async def logout(response: Response):
    """
    Clear authentication cookies.
    """

    _clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.get("/profile", response_model=UserInfo)
async def get_profile(request: Request) -> UserInfo:
    """
    Return current authenticated user.
    """

    if not settings.LDAP_ENABLED:
        return UserInfo(username="anonymous", display_name="anonymous", email=None)

    user = get_current_user(request)
    return UserInfo(**user)
