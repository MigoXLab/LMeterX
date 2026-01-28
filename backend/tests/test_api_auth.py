"""
Auth API tests.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import api.api_auth as api_auth
from app import app
from model.auth import LoginResponse, UserInfo

client = TestClient(app)


class TestAuthAPI:
    """Auth API tests."""

    def test_login_ldap_disabled(self):
        response = client.post(
            "/api/auth/login", json={"username": "user", "password": "pass"}
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "LDAP authentication is disabled"

    def test_login_success_sets_cookies(self, monkeypatch):
        monkeypatch.setattr(api_auth.settings, "LDAP_ENABLED", True)
        payload = LoginResponse(
            access_token="token-123",
            user=UserInfo(username="tester", display_name="Tester", email="t@x.com"),
        )

        with patch("api.api_auth.login_with_ldap", new=AsyncMock(return_value=payload)):
            response = client.post(
                "/api/auth/login", json={"username": "tester", "password": "pass"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "token-123"
            assert (
                response.cookies.get(api_auth.settings.JWT_COOKIE_NAME) == "token-123"
            )
            assert (
                response.cookies.get(f"{api_auth.settings.JWT_COOKIE_NAME}_present")
                == "1"
            )

    def test_logout(self):
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out"

    def test_get_profile_ldap_disabled(self):
        response = client.get("/api/auth/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "anonymous"
