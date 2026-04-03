"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import hmac
from typing import Callable, Iterable, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from utils.auth import decode_access_token
from utils.auth_settings import get_auth_settings
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger

settings = get_auth_settings()

# ── Service Token path whitelist ────────────────────────────────────────
# Requests authenticated via LMETERX_AUTH_TOKEN (Service Token) are
# restricted to ONLY these API paths.  This is the authoritative
# server-side enforcement; the Skill client-side whitelist serves as
# defense-in-depth only.
# Hardcoded (not env-configurable) to prevent tampering.
_SERVICE_TOKEN_ALLOWED_PATHS: frozenset[str] = frozenset(
    {
        "/api/skills/analyze-url",
        "/api/http-tasks/test",
        "/api/http-tasks",
    }
)


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
            if auth_header:
                if auth_header.lower().startswith("bearer "):
                    token = auth_header.split(" ", 1)[1].strip()
                else:
                    # Accept raw token without Bearer prefix (Service Token)
                    token = auth_header.strip()
                token_source = (
                    "header"  # nosec B105 - label for token source, not a secret
                )
            else:
                token = request.cookies.get(settings.JWT_COOKIE_NAME)

            if not token:
                raise ErrorResponse.unauthorized(ErrorMessages.UNAUTHORIZED)

            # ── Service Token fast-path (skip JWT decode) ──────────────
            # When LMETERX_AUTH_TOKEN is configured and the incoming token
            # matches, authenticate as the "agent" service user immediately.
            # Additionally enforce path whitelist: Service Token may ONLY
            # access the endpoints listed in _SERVICE_TOKEN_ALLOWED_PATHS.
            # NOTE: Service Token does NOT use Bearer prefix.  We normalise
            # the stored setting (strip accidental "Bearer " prefix) so that
            # the comparison works regardless of how the admin configured it.
            svc_token = settings.LMETERX_AUTH_TOKEN
            if svc_token and svc_token.lower().startswith("bearer "):
                svc_token = svc_token[7:].strip()
            if svc_token and hmac.compare_digest(token, svc_token):
                if path not in _SERVICE_TOKEN_ALLOWED_PATHS:
                    logger.warning(
                        "Service Token access denied for {} {} "
                        "(path not in whitelist)",
                        request.method,
                        path,
                    )
                    raise ErrorResponse.forbidden("Service Token not allowed")
                request.state.user = {
                    "sub": "agent",
                    "name": "Agent (Service Token)",
                    "email": None,
                    "iss": settings.JWT_ISSUER,
                }
                return await call_next(request)

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
            # Non-whitelist paths: upgrade to 403 when any auth fails.
            # These paths are never accessible via Service Token, so
            # returning "Forbidden" gives callers a clear signal that
            # no token type can unlock these endpoints except a valid JWT.
            if path not in _SERVICE_TOKEN_ALLOWED_PATHS:
                err = ErrorResponse.forbidden("Service Token not allowed")

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
