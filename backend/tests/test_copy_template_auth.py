"""Regression tests for authentication on task copy-template endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from starlette.responses import JSONResponse

from middleware.auth_middleware import AuthMiddleware


def _middleware() -> AuthMiddleware:
    return AuthMiddleware(
        app=MagicMock(),
        exempt_prefixes=["/api/llm-tasks", "/api/http-tasks"],
        auth_required_suffixes=["/copy-template"],
    )


def _request(path: str, token: str | None = None) -> Request:
    headers = []
    if token:
        headers.append((b"x-authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.LDAP_ENABLED = True
    settings.LMETERX_AUTH_TOKEN = ""
    settings.ENGINE_API_TOKEN = ""
    settings.JWT_COOKIE_NAME = "access_token"
    return settings


async def _user_response(request: Request) -> JSONResponse:
    return JSONResponse({"user": getattr(request.state, "user", None)})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/llm-tasks/llm-1/copy-template",
        "/api/http-tasks/http-1/copy-template",
    ],
)
async def test_copy_template_endpoints_reject_missing_auth(path):
    with patch("middleware.auth_middleware.settings", _settings()):
        response = await _middleware().dispatch(_request(path), _user_response)

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/llm-tasks/llm-1/copy-template",
        "/api/http-tasks/http-1/copy-template",
    ],
)
async def test_copy_template_endpoints_receive_authenticated_user(path):
    user = {"sub": "task-owner", "name": "Task Owner"}
    with (
        patch("middleware.auth_middleware.settings", _settings()),
        patch(
            "middleware.auth_middleware.decode_access_token", return_value=user
        ) as decode_token,
    ):
        request = _request(path, "valid-user-token")
        response = await _middleware().dispatch(request, _user_response)

    assert response.status_code == 200
    assert request.state.user == user
    decode_token.assert_called_once_with("valid-user-token")


@pytest.mark.asyncio
async def test_other_public_gets_below_exempt_prefix_remain_public():
    with patch("middleware.auth_middleware.settings", _settings()):
        request = _request("/api/llm-tasks/llm-1/results")
        response = await _middleware().dispatch(request, _user_response)

    assert response.status_code == 200
    assert not hasattr(request.state, "user")
