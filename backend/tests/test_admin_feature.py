"""
Admin feature tests – is_admin_user utility, Auth API, Auth Service login,
and task-service permission bypass for admin / agent users.

Test matrix:
  1. is_admin_user() core function (empty config, single admin, multiple admins, case sensitivity, etc.)
  2. Auth API /profile endpoint returns correct is_admin flag
  3. Auth Service login sets is_admin on UserInfo
  4. LLM task service: admin / agent / normal-user permission enforcement
  5. HTTP task service: admin / agent / normal-user permission enforcement
  6. Regression: non-admin users still blocked from other users' tasks
"""

import asyncio
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from model.auth import LoginResponse, UserInfo
from utils.auth import is_admin_user
from utils.error_handler import ErrorMessages, ErrorResponse

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Helper factories
# ═══════════════════════════════════════════════════════════════════════════


def _mock_task(
    *,
    task_id: str = "task_001",
    name: str = "Test Task",
    status: str = "running",
    created_by: Optional[str] = "alice",
    is_deleted: int = 0,
):
    """Create a mock Task / HttpTask ORM object."""
    task = MagicMock()
    task.id = task_id
    task.name = name
    task.status = status
    task.created_by = created_by
    task.is_deleted = is_deleted
    return task


def _mock_request(*, username: str = "alice") -> MagicMock:
    """Create a mock FastAPI Request with an authenticated user."""
    req = MagicMock()
    req.state = MagicMock()
    req.state.user = {"sub": username, "username": username, "name": username}
    # async db methods
    db = AsyncMock()
    req.state.db = db
    return req


# ═══════════════════════════════════════════════════════════════════════════
# 1. is_admin_user() core function
# ═══════════════════════════════════════════════════════════════════════════


class TestIsAdminUser:
    """Tests for utils.auth.is_admin_user()."""

    def test_empty_config_returns_false(self, monkeypatch):
        """Verify ADMIN_USERNAMES is empty, any user is not an admin."""
        from utils import auth as auth_mod

        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "")
        assert is_admin_user("alice") is False
        assert is_admin_user("admin") is False
        assert is_admin_user("") is False

    def test_single_admin_match(self, monkeypatch):
        """Verify single admin match, return True."""
        from utils import auth as auth_mod

        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "admin")
        assert is_admin_user("admin") is True

    def test_single_admin_no_match(self, monkeypatch):
        """Verify single admin no match, return False."""
        from utils import auth as auth_mod

        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "admin")
        assert is_admin_user("alice") is False

    def test_multiple_admins(self, monkeypatch):
        """Verify multiple admins, all users in the list return True."""
        from utils import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "ADMIN_USERNAMES", "admin,superuser,john"
        )
        assert is_admin_user("admin") is True
        assert is_admin_user("superuser") is True
        assert is_admin_user("john") is True
        assert is_admin_user("alice") is False

    def test_case_insensitive(self, monkeypatch):
        """Verify admin name match is case insensitive."""
        from utils import auth as auth_mod

        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "Admin,SuperUser")
        assert is_admin_user("admin") is True
        assert is_admin_user("ADMIN") is True
        assert is_admin_user("superuser") is True
        assert is_admin_user("SUPERUSER") is True

    def test_whitespace_handling(self, monkeypatch):
        """Verify whitespace handling in config."""
        from utils import auth as auth_mod

        monkeypatch.setattr(
            auth_mod.settings, "ADMIN_USERNAMES", " admin , superuser , john "
        )
        assert is_admin_user("admin") is True
        assert is_admin_user("superuser") is True
        assert is_admin_user("john") is True

    def test_empty_username_returns_false(self, monkeypatch):
        """Verify empty username returns False."""
        from utils import auth as auth_mod

        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "admin")
        assert is_admin_user("") is False

    def test_trailing_commas_ignored(self, monkeypatch):
        """Verify trailing commas in config are ignored."""
        from utils import auth as auth_mod

        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "admin,,superuser,")
        assert is_admin_user("admin") is True
        assert is_admin_user("superuser") is True
        assert is_admin_user("") is False

    def test_only_commas_returns_false(self, monkeypatch):
        """Verify only commas (no valid usernames) return False."""
        from utils import auth as auth_mod

        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", ",,,")
        assert is_admin_user("admin") is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. Auth API /profile – is_admin flag
# ═══════════════════════════════════════════════════════════════════════════


class TestProfileAdminFlag:
    """Test that /api/auth/profile returns correct is_admin flag."""

    def test_profile_ldap_disabled_no_admin(self):
        """Verify LDAP disabled, profile returns anonymous, is_admin default False."""
        response = client.get("/api/auth/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "anonymous"
        assert data.get("is_admin") is False

    def test_profile_ldap_enabled_admin_user(self, monkeypatch):
        """Verify LDAP enabled + admin user, is_admin is True."""
        import api.api_auth as api_auth_mod
        import utils.auth as auth_mod

        monkeypatch.setattr(api_auth_mod.settings, "LDAP_ENABLED", True)
        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "admin_user")

        mock_user = {"sub": "admin_user", "name": "Admin", "email": "admin@test.com"}
        with patch("api.api_auth.get_current_user", return_value=mock_user):
            response = client.get("/api/auth/profile")
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "admin_user"
            assert data["is_admin"] is True

    def test_profile_ldap_enabled_normal_user(self, monkeypatch):
        """Verify LDAP enabled + normal user, is_admin is False."""
        import api.api_auth as api_auth_mod
        import utils.auth as auth_mod

        monkeypatch.setattr(api_auth_mod.settings, "LDAP_ENABLED", True)
        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "admin_user")

        mock_user = {"sub": "alice", "name": "Alice", "email": "alice@test.com"}
        with patch("api.api_auth.get_current_user", return_value=mock_user):
            response = client.get("/api/auth/profile")
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "alice"
            assert data["is_admin"] is False

    def test_profile_admin_usernames_empty(self, monkeypatch):
        """Verify ADMIN_USERNAMES is empty, all users is_admin is False."""
        import api.api_auth as api_auth_mod
        import utils.auth as auth_mod

        monkeypatch.setattr(api_auth_mod.settings, "LDAP_ENABLED", True)
        monkeypatch.setattr(auth_mod.settings, "ADMIN_USERNAMES", "")

        mock_user = {"sub": "admin", "name": "Admin", "email": "admin@test.com"}
        with patch("api.api_auth.get_current_user", return_value=mock_user):
            response = client.get("/api/auth/profile")
            assert response.status_code == 200
            data = response.json()
            assert data["is_admin"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. Auth Service login – is_admin flag in UserInfo
# ═══════════════════════════════════════════════════════════════════════════


class TestLoginAdminFlag:
    """Test that auth service login correctly sets is_admin on UserInfo."""

    def test_extract_user_info_does_not_set_admin(self):
        """_extract_user_info 默认 is_admin=False。"""
        from service.auth_service import _extract_user_info

        user_info = _extract_user_info(None, "alice")
        assert user_info.is_admin is False

    def test_user_info_model_has_is_admin(self):
        """Verify UserInfo 模型包含 is_admin 字段，默认 False。"""
        info = UserInfo(username="alice")
        assert info.is_admin is False

    def test_user_info_model_is_admin_true(self):
        """Verify UserInfo 模型可以设置 is_admin=True。"""
        info = UserInfo(username="admin", is_admin=True)
        assert info.is_admin is True

    def test_user_info_model_dump_includes_is_admin(self):
        """model_dump() 包含 is_admin 字段。"""
        info = UserInfo(username="admin", is_admin=True)
        dumped = info.model_dump()
        assert "is_admin" in dumped
        assert dumped["is_admin"] is True

    def test_login_response_includes_admin_flag(self):
        """Verify LoginResponse 嵌套的 UserInfo 包含 is_admin。"""
        resp = LoginResponse(
            access_token="test-token",
            user=UserInfo(username="admin", is_admin=True),
        )
        assert resp.user.is_admin is True


# ═══════════════════════════════════════════════════════════════════════════
# 4. LLM Task Service – admin / agent permission checks
# ═══════════════════════════════════════════════════════════════════════════


class TestLlmTaskPermissions:
    """LLM task service permission enforcement for admin, agent, and normal users."""

    # ---------- stop_task_svc ----------

    @pytest.mark.asyncio
    async def test_admin_can_stop_other_users_task(self, monkeypatch):
        """管理员可以停止其他用户的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.stop_task_svc(req, "task_001")
            assert result.status == "stopping"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_stop_other_users_task(self, monkeypatch):
        """非管理员不能停止其他用户的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)

        with patch.object(svc, "is_admin_user", return_value=False):
            # ErrorResponse inherits from HTTPException, but the stop_task_svc
            # catches generic Exception and returns error status
            result = await svc.stop_task_svc(req, "task_001")
            # Should be error because the forbidden exception is caught
            assert result.status == "error"

    @pytest.mark.asyncio
    async def test_any_user_can_stop_agent_task(self, monkeypatch):
        """任何用户都可以停止 agent 创建的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="agent", status="running")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.stop_task_svc(req, "task_001")
            assert result.status == "stopping"

    @pytest.mark.asyncio
    async def test_owner_can_stop_own_task(self, monkeypatch):
        """任务创建者可以停止自己的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="alice")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.stop_task_svc(req, "task_001")
            assert result.status == "stopping"

    # ---------- update_task_svc ----------

    @pytest.mark.asyncio
    async def test_admin_can_rename_other_users_task(self, monkeypatch):
        """管理员可以重命名其他用户的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()
        req.state.db.refresh = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.update_task_svc(req, "task_001", {"name": "New Name"})
            assert result["status"] == "success"
            assert task.name == "New Name"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_rename_other_users_task(self, monkeypatch):
        """非管理员不能重命名其他用户的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            with pytest.raises(ErrorResponse) as exc:
                await svc.update_task_svc(req, "task_001", {"name": "New Name"})
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_any_user_can_rename_agent_task(self, monkeypatch):
        """任何用户都可以重命名 agent 创建的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="agent", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()
        req.state.db.refresh = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.update_task_svc(req, "task_001", {"name": "New Name"})
            assert result["status"] == "success"

    # ---------- delete_task_svc ----------

    @pytest.mark.asyncio
    async def test_admin_can_delete_other_users_task(self, monkeypatch):
        """管理员可以删除其他用户的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.delete_task_svc(req, "task_001")
            assert result["status"] == "success"
            assert task.is_deleted == 1

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_other_users_task(self, monkeypatch):
        """非管理员不能删除其他用户的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_task_svc(req, "task_001")
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_agent_task(self, monkeypatch):
        """非管理员不能删除 agent 创建的任务（delete 不包含 agent bypass）。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="agent", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_task_svc(req, "task_001")
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_delete_agent_task(self, monkeypatch):
        """管理员可以删除 agent 创建的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="agent", status="completed")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.delete_task_svc(req, "task_001")
            assert result["status"] == "success"

    # ---------- LDAP disabled – no permission checks ----------

    @pytest.mark.asyncio
    async def test_ldap_disabled_any_user_can_stop(self, monkeypatch):
        """LDAP 关闭时，不进行权限校验，任何用户都可以操作。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", False)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        result = await svc.stop_task_svc(req, "task_001")
        assert result.status == "stopping"

    @pytest.mark.asyncio
    async def test_ldap_disabled_any_user_can_rename(self, monkeypatch):
        """LDAP 关闭时，不进行权限校验，任何用户都可以重命名。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", False)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()
        req.state.db.refresh = AsyncMock()

        result = await svc.update_task_svc(req, "task_001", {"name": "New Name"})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_ldap_disabled_any_user_can_delete(self, monkeypatch):
        """LDAP 关闭时，不进行权限校验，任何用户都可以删除。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", False)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        result = await svc.delete_task_svc(req, "task_001")
        assert result["status"] == "success"

    # ---------- Edge case: task without created_by ----------

    @pytest.mark.asyncio
    async def test_non_admin_cannot_stop_task_without_creator(self, monkeypatch):
        """非管理员不能停止没有创建者信息的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by=None, status="running")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.stop_task_svc(req, "task_001")
            # The forbidden exception is caught by the generic except in stop_task_svc
            assert result.status == "error"

    @pytest.mark.asyncio
    async def test_admin_can_stop_task_without_creator(self, monkeypatch):
        """管理员可以停止没有创建者信息的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by=None, status="running")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.stop_task_svc(req, "task_001")
            assert result.status == "stopping"


# ═══════════════════════════════════════════════════════════════════════════
# 5. HTTP Task Service – admin / agent permission checks
# ═══════════════════════════════════════════════════════════════════════════


class TestHttpTaskPermissions:
    """HTTP task service permission enforcement for admin, agent, and normal users."""

    # ---------- stop_http_task_svc ----------

    @pytest.mark.asyncio
    async def test_admin_can_stop_http_task(self, monkeypatch):
        """管理员可以停止其他用户的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.stop_http_task_svc(req, "task_001")
            assert result.status == "stopping"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_stop_http_task(self, monkeypatch):
        """非管理员不能停止其他用户的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.stop_http_task_svc(req, "task_001")
            assert result.status == "error"

    @pytest.mark.asyncio
    async def test_any_user_can_stop_agent_http_task(self, monkeypatch):
        """任何用户都可以停止 agent 创建的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="agent", status="running")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.stop_http_task_svc(req, "task_001")
            assert result.status == "stopping"

    # ---------- update_http_task_svc ----------

    @pytest.mark.asyncio
    async def test_admin_can_rename_http_task(self, monkeypatch):
        """管理员可以重命名其他用户的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()
        req.state.db.refresh = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.update_http_task_svc(req, "task_001", {"name": "New"})
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_rename_http_task(self, monkeypatch):
        """非管理员不能重命名其他用户的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            with pytest.raises(ErrorResponse) as exc:
                await svc.update_http_task_svc(req, "task_001", {"name": "New"})
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_any_user_can_rename_agent_http_task(self, monkeypatch):
        """任何用户都可以重命名 agent 创建的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="agent", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()
        req.state.db.refresh = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.update_http_task_svc(req, "task_001", {"name": "New"})
            assert result["status"] == "success"

    # ---------- delete_http_task_svc ----------

    @pytest.mark.asyncio
    async def test_admin_can_delete_http_task(self, monkeypatch):
        """管理员可以删除其他用户的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.delete_http_task_svc(req, "task_001")
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_http_task(self, monkeypatch):
        """非管理员不能删除其他用户的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_http_task_svc(req, "task_001")
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delete_agent_http_task(self, monkeypatch):
        """非管理员不能删除 agent 创建的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="agent", status="completed")
        req = _mock_request(username="bob")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_http_task_svc(req, "task_001")
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_can_manage_own_http_task(self, monkeypatch):
        """任务创建者可以管理自己的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed")
        req = _mock_request(username="alice")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.commit = AsyncMock()

        with patch.object(svc, "is_admin_user", return_value=False):
            result = await svc.delete_http_task_svc(req, "task_001")
            assert result["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Regression – ensure no new defects introduced
# ═══════════════════════════════════════════════════════════════════════════


class TestRegressionChecks:
    """Ensure existing behavior is not broken by admin/agent changes."""

    @pytest.mark.asyncio
    async def test_cannot_delete_running_task_even_as_admin(self, monkeypatch):
        """管理员也不能删除正在运行的任务（安全检查优先于权限检查）。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_task_svc(req, "task_001")
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_delete_stopping_task_even_as_admin(self, monkeypatch):
        """管理员也不能删除正在停止的任务。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="stopping")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_task_svc(req, "task_001")
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_stop_non_running_task_returns_status(self, monkeypatch):
        """停止非运行状态的任务返回当前状态（不报错）。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="admin", status="completed")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.stop_task_svc(req, "task_001")
            assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_update_empty_name_rejected(self, monkeypatch):
        """空任务名称被拒绝（不受管理员权限影响）。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        with pytest.raises(ErrorResponse) as exc:
            req = _mock_request(username="admin")
            await svc.update_task_svc(req, "task_001", {"name": ""})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_name_too_long_rejected(self, monkeypatch):
        """超长任务名称被拒绝。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        long_name = "x" * 101
        with pytest.raises(ErrorResponse) as exc:
            req = _mock_request(username="admin")
            await svc.update_task_svc(req, "task_001", {"name": long_name})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_stop_deleted_task_returns_not_found(self, monkeypatch):
        """停止已删除的任务返回 'Task not found'。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed", is_deleted=1)
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            result = await svc.stop_task_svc(req, "task_001")
            assert result.status == "unknown"
            assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_delete_already_deleted_task_returns_not_found(self, monkeypatch):
        """删除已删除的任务返回 404。"""
        from service import llm_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="completed", is_deleted=1)
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_task_svc(req, "task_001")
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_http_cannot_delete_running_task_even_as_admin(self, monkeypatch):
        """管理员也不能删除正在运行的 HTTP 任务。"""
        from service import http_task_service as svc

        monkeypatch.setattr(svc.settings, "LDAP_ENABLED", True)

        task = _mock_task(created_by="alice", status="running")
        req = _mock_request(username="admin")
        req.state.db.get = AsyncMock(return_value=task)
        req.state.db.rollback = AsyncMock()

        with patch.object(svc, "is_admin_user", side_effect=lambda u: u == "admin"):
            with pytest.raises(ErrorResponse) as exc:
                await svc.delete_http_task_svc(req, "task_001")
            assert exc.value.status_code == 400
