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
        "/api/llm-tasks/test",
        "/api/llm-tasks",
    }
)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Validate Bearer tokens for protected endpoints.
    """

    def __init__(
        self,
        app,
        exempt_paths: Optional[Iterable[str]] = None,
        exempt_prefixes: Optional[Iterable[str]] = None,
    ):
        """Initialize the AuthMiddleware."""
        super().__init__(app)
        self.exempt_paths = set(exempt_paths or [])
        self.exempt_prefixes = tuple(exempt_prefixes or [])

    def _should_skip_auth(self, request: Request, path: str) -> bool:
        if not settings.LDAP_ENABLED:
            return True

        # Skip auth for OPTIONS, public, and docs endpoints
        if (
            request.method == "OPTIONS"
            or path in self.exempt_paths
            or path.startswith("/docs")
            or path.startswith("/openapi")
            or (
                request.method == "GET"
                and self.exempt_prefixes
                and path.startswith(self.exempt_prefixes)
            )
        ):
            return True
        return False

    def _extract_token(self, request: Request) -> tuple[Optional[str], str]:
        auth_header = (
            request.headers.get("Authorization")
            or request.headers.get("X-Forwarded-Authorization")
            or request.headers.get("X-Authorization")
        )
        token: Optional[str] = None
        token_source = "cookie"  # nosec B105
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            else:
                # Accept raw token without Bearer prefix (Service Token)
                token = auth_header.strip()
            token_source = "header"  # nosec B105
        else:
            token = request.cookies.get(settings.JWT_COOKIE_NAME)
        return token, token_source

    def _check_service_token(
        self, token: str, path: str, method: str
    ) -> Optional[dict]:
        svc_token = settings.LMETERX_AUTH_TOKEN
        if svc_token and svc_token.lower().startswith("bearer "):
            svc_token = svc_token[7:].strip()
        if svc_token and hmac.compare_digest(token, svc_token):
            if path not in _SERVICE_TOKEN_ALLOWED_PATHS:
                logger.warning(
                    "Service Token access denied for {} {} (path not in whitelist)",
                    method,
                    path,
                )
                raise ErrorResponse.forbidden("Service Token not allowed")
            return {
                "sub": "agent",
                "name": "Agent (Service Token)",
                "email": None,
                "iss": settings.JWT_ISSUER,
            }
        return None

    def _check_engine_token(self, token: str, path: str, method: str) -> Optional[dict]:
        engine_token = getattr(settings, "ENGINE_API_TOKEN", "")
        if not isinstance(engine_token, str):
            engine_token = ""  # nosec B105
        if engine_token and engine_token.lower().startswith("bearer "):
            engine_token = engine_token[7:].strip()
        if engine_token and hmac.compare_digest(token, engine_token):
            if not (
                path.startswith("/api/engine/") or path.startswith("/api/clusters/")
            ):
                logger.warning(
                    "Engine API Token access denied for {} {} (path not in allowed prefixes)",
                    method,
                    path,
                )
                raise ErrorResponse.forbidden("Engine API Token not allowed")
            return {
                "sub": "engine",
                "name": "Engine (API Token)",
                "email": None,
                "iss": settings.JWT_ISSUER,
            }
        return None

    async def dispatch(self, request: Request, call_next: Callable):
        """Dispatch the request and perform authentication checks."""
        path = request.url.path
        if self._should_skip_auth(request, path):
            return await call_next(request)

        try:
            token, token_source = self._extract_token(request)
            if not token:
                raise ErrorResponse.unauthorized(ErrorMessages.UNAUTHORIZED)

            # ── Service Token fast-path (skip JWT decode) ──────────────
            user_info = self._check_service_token(token, path, request.method)
            if user_info:
                request.state.user = user_info
            else:
                # ── Engine API Token fast-path (skip JWT decode) ───────────
                user_info = self._check_engine_token(token, path, request.method)
                if user_info:
                    request.state.user = user_info
                else:
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

        except ErrorResponse as err:
            # Preserve the original auth semantics:
            # - missing/invalid/expired JWT => 401
            # - valid service/engine token on a forbidden path => 403
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
                "Unexpected auth middleware error during token validation for {} {}",
                request.method,
                path,
            )
            return ErrorResponse.internal_server_error().to_response()

        return await call_next(request)
