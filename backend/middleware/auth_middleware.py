"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Callable, Iterable, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from utils.auth import decode_access_token
from utils.auth_settings import get_auth_settings
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger

settings = get_auth_settings()


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Validate Bearer tokens for protected endpoints.
    """

    def __init__(self, app, exempt_paths: Optional[Iterable[str]] = None):
        super().__init__(app)
        self.exempt_paths = set(exempt_paths or [])

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        try:
            if not settings.LDAP_ENABLED:
                return await call_next(request)

            # Skip auth for OPTIONS, public, and docs endpoints
            if (
                request.method == "OPTIONS"
                or path in self.exempt_paths
                or path.startswith("/docs")
                or path.startswith("/openapi")
            ):
                return await call_next(request)

            auth_header = (
                request.headers.get("Authorization")
                or request.headers.get("X-Forwarded-Authorization")
                or request.headers.get("X-Authorization")
            )
            token: Optional[str] = None
            token_source = "cookie"  # nosec B105 - label for token source, not a secret
            if auth_header and auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
                token_source = (
                    "header"  # nosec B105 - label for token source, not a secret
                )
            else:
                token = request.cookies.get(settings.JWT_COOKIE_NAME)

            if not token:
                raise ErrorResponse.unauthorized(ErrorMessages.UNAUTHORIZED)

            try:
                payload = decode_access_token(token)
                request.state.user = payload
            except ErrorResponse:
                # If header token is invalid, fall back to cookie token when present.
                if (
                    token_source
                    == "header"  # nosec B105 - label for token source, not a secret
                ):
                    cookie_token = request.cookies.get(settings.JWT_COOKIE_NAME)
                    if cookie_token and cookie_token != token:
                        payload = decode_access_token(cookie_token)
                        request.state.user = payload
                    else:
                        raise
                else:
                    raise

            return await call_next(request)

        except ErrorResponse as err:
            # Return a clean 4xx response instead of bubbling up as 500
            logger.info(
                "Auth failed for {} {} from {}: {}",
                request.method,
                path,
                request.client.host if request.client else "unknown",
                err.error,
            )
            return err.to_response()
        except Exception:  # pragma: no cover - defensive logging
            logger.exception(
                "Unexpected auth middleware error for {} {}",
                request.method,
                path,
            )
            return ErrorResponse.internal_server_error().to_response()
