"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Optional

from fastapi import Request
from ldap3 import ALL, BASE, Connection, Server  # type: ignore[import-untyped]
from ldap3.core.exceptions import LDAPSocketOpenError  # type: ignore[import-untyped]

from model.auth import LoginRequest, LoginResponse, UserInfo
from utils.auth import create_access_token
from utils.auth_settings import get_auth_settings
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger

settings = get_auth_settings()


def _ensure_ldap_ready() -> None:
    if not settings.LDAP_ENABLED:
        raise ErrorResponse.bad_request(
            ErrorMessages.LDAP_DISABLED,
            details="Set LDAP_ENABLED=on to enable LDAP authentication.",
        )

    missing = []
    if not settings.LDAP_SERVER:
        missing.append("LDAP_SERVER")
    if not settings.LDAP_USER_DN_TEMPLATE and not settings.LDAP_BIND_DN:
        missing.append("LDAP_USER_DN_TEMPLATE or LDAP_BIND_DN")
    if settings.LDAP_BIND_DN:
        if not settings.LDAP_BIND_PASSWORD:
            missing.append("LDAP_BIND_PASSWORD")
        if not settings.LDAP_SEARCH_BASE and not settings.LDAP_USER_DN_TEMPLATE:
            missing.append("LDAP_SEARCH_BASE")
    if missing:
        raise ErrorResponse.bad_request(
            ErrorMessages.LDAP_CONFIG_INCOMPLETE,
            details={"missing": missing},
        )


def _build_server() -> Server:
    return Server(
        settings.LDAP_SERVER,
        port=settings.LDAP_PORT,
        use_ssl=settings.LDAP_USE_SSL,
        get_info=ALL,
        connect_timeout=settings.LDAP_TIMEOUT,
    )


def _search_user_dn(
    conn: Connection, username: str, search_base: str, search_filter: str
) -> Optional[str]:
    """
    Search user DN using a service bind.
    """

    if not search_base:
        return None

    resolved_filter = search_filter.format(username=username)
    conn.search(
        search_base=search_base,
        search_filter=resolved_filter,
        attributes=["cn", "displayName", "mail", "sAMAccountName"],
        size_limit=1,
    )
    if not conn.entries:
        return None
    return conn.entries[0].entry_dn


def _extract_user_info(entry: Optional[object], username: str) -> UserInfo:
    """
    Safely build user info from LDAP entry.
    """

    if entry is None:
        return UserInfo(username=username, display_name=username, email=None)

    def _get_attr(attr_name: str) -> Optional[str]:
        return (
            str(getattr(entry, attr_name))
            if hasattr(entry, attr_name) and getattr(entry, attr_name)
            else None
        )

    return UserInfo(
        username=username,
        display_name=_get_attr("displayName") or _get_attr("cn") or username,
        email=_get_attr("mail"),
    )


async def login_with_ldap(_: Request, login_request: LoginRequest) -> LoginResponse:
    """
    Authenticate user against LDAP/AD and issue JWT.
    """

    _ensure_ldap_ready()

    username = login_request.username.strip()
    password = login_request.password

    if not username or not password:
        raise ErrorResponse.bad_request(ErrorMessages.INVALID_CREDENTIALS)

    server = _build_server()

    try:
        user_entry: Optional[object] = None
        user_dn = None
        attributes = ["cn", "displayName", "mail", "sAMAccountName"]

        # If we have a bind user, search DN first
        if settings.LDAP_BIND_DN:
            with Connection(
                server,
                user=settings.LDAP_BIND_DN,
                password=settings.LDAP_BIND_PASSWORD,
                auto_bind=True,
            ) as bind_conn:
                user_dn = _search_user_dn(
                    bind_conn,
                    username,
                    settings.LDAP_SEARCH_BASE,
                    settings.LDAP_SEARCH_FILTER,
                )
                if not user_dn:
                    raise ErrorResponse.unauthorized(ErrorMessages.INVALID_CREDENTIALS)
        elif settings.LDAP_USER_DN_TEMPLATE:
            user_dn = settings.LDAP_USER_DN_TEMPLATE.format(username=username)
        else:
            raise ErrorResponse.bad_request(
                ErrorMessages.LDAP_CONFIG_INCOMPLETE,
                details="Set LDAP_USER_DN_TEMPLATE or LDAP_BIND_DN/LDAP_SEARCH_BASE.",
            )

        # Bind as the user to validate password
        with Connection(
            server, user=user_dn, password=password, auto_bind=True
        ) as conn:
            # Re-query using the bound user DN to avoid stale entries from the service bind
            conn.search(
                search_base=user_dn,
                search_scope=BASE,
                search_filter="(objectClass=*)",
                attributes=attributes,
                size_limit=1,
            )
            if conn.entries:
                user_entry = conn.entries[0]
            elif settings.LDAP_SEARCH_BASE:
                # Fallback to configured search base if the direct DN lookup fails
                resolved_filter = settings.LDAP_SEARCH_FILTER.format(username=username)
                conn.search(
                    search_base=settings.LDAP_SEARCH_BASE,
                    search_filter=resolved_filter,
                    attributes=attributes,
                    size_limit=1,
                )
                if conn.entries:
                    user_entry = conn.entries[0]

            user_info = _extract_user_info(user_entry, username)

        token = create_access_token(user_info.model_dump())
        return LoginResponse(access_token=token, user=user_info)

    except LDAPSocketOpenError as exc:
        logger.error("LDAP connection failed: {}", exc)
        raise ErrorResponse.internal_server_error(
            ErrorMessages.LDAP_CONNECTION_FAILED,
            details=f"LDAP connection error: {exc}",
        )
    except ErrorResponse:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("LDAP authentication failed: {}", exc)
        raise ErrorResponse.unauthorized(ErrorMessages.INVALID_CREDENTIALS)
