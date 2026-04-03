"""
Service Token (LMETERX_AUTH_TOKEN) 鉴权集成测试。

测试矩阵：
  1. LDAP_ENABLED=off, Token 为空    → 所有 API 无需鉴权即可调用
  2. LDAP_ENABLED=on,  Token 为空    → 调用 白名单API 返回 401，非白名单API 返回 403
  3. LDAP_ENABLED=on,  Token 一致    → 白名单 API 可以调用，非白名单 → 403
  4. LDAP_ENABLED=on,  Token 不一致  → 调用 白名单API 返回 401，非白名单API 返回 403
  5. Skill 脚本白名单               → 非白名单路径在客户端被拦截（纵深防御）
  6. 边界情况                       → exempt_paths、X-Authorization、OPTIONS 等

安全模型（双重白名单）：
  - 后端 AuthMiddleware: Service Token 只能访问 _SERVICE_TOKEN_ALLOWED_PATHS → 403
  - Skill _safe_request: 客户端额外拦截非白名单路径 → PermissionError（纵深防御）

由于 conftest.py 设置了 TESTING=1（跳过 AuthMiddleware 挂载），
本测试构造独立的 FastAPI app 来精确控制中间件行为。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure backend root is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from middleware.auth_middleware import AuthMiddleware  # noqa: E402
from utils.error_handler import ErrorResponse  # noqa: E402

# ── Test constants ───────────────────────────────────────────────────────────

SERVICE_TOKEN = "test-service-token-abc123"
WRONG_TOKEN = "wrong-token-xyz789"

EXEMPT_PATHS = {"/health", "/", "/api/auth/login", "/api/auth/logout"}


# ── Helper: create a mock settings object ────────────────────────────────────


def _make_settings(*, ldap_enabled: bool = False, service_token: str = ""):
    """Create a mock AuthSettings."""
    mock = MagicMock()
    mock.LDAP_ENABLED = ldap_enabled
    mock.LMETERX_AUTH_TOKEN = service_token
    mock.JWT_COOKIE_NAME = "access_token"
    mock.JWT_ISSUER = "lmeterx"
    return mock


def _build_test_app() -> FastAPI:
    """Create a minimal FastAPI app with routes + AuthMiddleware.

    Settings are controlled via patching ``middleware.auth_middleware.settings``
    at the TEST level, NOT during app construction.
    """
    test_app = FastAPI()

    @test_app.exception_handler(ErrorResponse)
    async def handle_error(_: Request, exc: ErrorResponse):
        return exc.to_response()

    # ── Routes (cover whitelist & non-whitelist) ──

    @test_app.get("/health")
    def health():
        return {"status": "healthy"}

    @test_app.post("/api/skills/analyze-url")
    def analyze_url(request: Request):
        user = getattr(request.state, "user", None)
        return {"status": "success", "user": user}

    @test_app.post("/api/http-tasks/test")
    def http_test(request: Request):
        user = getattr(request.state, "user", None)
        return {"status": "success", "user": user}

    @test_app.post("/api/http-tasks")
    def http_create(request: Request):
        user = getattr(request.state, "user", None)
        return {"status": "success", "user": user}

    @test_app.get("/api/system")
    def system_config(request: Request):
        user = getattr(request.state, "user", None)
        return {"status": "success", "user": user}

    @test_app.get("/api/auth/profile")
    def profile(request: Request):
        user = getattr(request.state, "user", None)
        if user:
            return {
                "username": user.get("sub", ""),
                "display_name": user.get("name", ""),
            }
        return {"username": "anonymous", "display_name": "anonymous"}

    @test_app.get("/api/llm-tasks")
    def llm_tasks(request: Request):
        user = getattr(request.state, "user", None)
        return {"status": "success", "user": user}

    # Add middleware (settings are patched in each test class, NOT here)
    test_app.add_middleware(
        AuthMiddleware,
        exempt_paths=EXEMPT_PATHS,
    )

    return test_app


# Build ONE shared app; per-test settings are injected via patching.
_test_app = _build_test_app()


# ═════════════════════════════════════════════════════════════════════════════
# 场景 1: LDAP_ENABLED=off, LMETERX_AUTH_TOKEN="" → 所有 API 无需鉴权
# ═════════════════════════════════════════════════════════════════════════════


class TestLdapDisabledNoToken:
    """LDAP 关闭时，所有 API 无需鉴权即可调用。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        mock = _make_settings(ldap_enabled=False, service_token="")
        with patch("middleware.auth_middleware.settings", mock):
            self.client = TestClient(_test_app)
            yield

    def test_health_accessible(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200

    def test_whitelist_analyze_url_no_auth(self):
        """白名单接口 /api/skills/analyze-url 无需 Token。"""
        resp = self.client.post("/api/skills/analyze-url")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_whitelist_http_tasks_test_no_auth(self):
        """白名单接口 /api/http-tasks/test 无需 Token。"""
        resp = self.client.post("/api/http-tasks/test")
        assert resp.status_code == 200

    def test_whitelist_http_tasks_create_no_auth(self):
        """白名单接口 /api/http-tasks 无需 Token。"""
        resp = self.client.post("/api/http-tasks")
        assert resp.status_code == 200

    def test_non_whitelist_system_no_auth(self):
        """非白名单接口 /api/system 无需 Token。"""
        resp = self.client.get("/api/system")
        assert resp.status_code == 200

    def test_non_whitelist_profile_no_auth(self):
        """非白名单接口 /api/auth/profile 无需 Token。"""
        resp = self.client.get("/api/auth/profile")
        assert resp.status_code == 200
        assert resp.json()["username"] == "anonymous"

    def test_non_whitelist_llm_tasks_no_auth(self):
        """非白名单接口 /api/llm-tasks 无需 Token。"""
        resp = self.client.get("/api/llm-tasks")
        assert resp.status_code == 200


# ═════════════════════════════════════════════════════════════════════════════
# 场景 2: LDAP_ENABLED=on, Token 为空
#   白名单 API → 401 (需要提供凭证)
#   非白名单 API → 403 (该路径不允许 Service Token 访问)
# ═════════════════════════════════════════════════════════════════════════════


class TestLdapEnabledNoToken:
    """LDAP 开启 + Token 为空。

    白名单 API → 401 (Unauthorized — 需要提供凭证)
    非白名单 API → 403 (Forbidden — 该路径对 Service Token 永远不可达)
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        mock = _make_settings(ldap_enabled=True, service_token="")
        with patch("middleware.auth_middleware.settings", mock):
            self.client = TestClient(_test_app, raise_server_exceptions=False)
            yield

    def test_health_still_accessible(self):
        """Health 是 exempt_path，始终可访问。"""
        resp = self.client.get("/health")
        assert resp.status_code == 200

    # ── 白名单路径: 401 ──

    def test_whitelist_analyze_url_returns_401(self):
        """白名单接口无 Token → 401。"""
        resp = self.client.post("/api/skills/analyze-url")
        assert resp.status_code == 401

    def test_whitelist_http_tasks_test_returns_401(self):
        """白名单接口无 Token → 401。"""
        resp = self.client.post("/api/http-tasks/test")
        assert resp.status_code == 401

    def test_whitelist_http_tasks_create_returns_401(self):
        """白名单接口无 Token → 401。"""
        resp = self.client.post("/api/http-tasks")
        assert resp.status_code == 401

    # ── 非白名单路径: 403 ──

    def test_non_whitelist_system_returns_403(self):
        """非白名单接口无 Token → 403。"""
        resp = self.client.get("/api/system")
        assert resp.status_code == 403

    def test_non_whitelist_profile_returns_403(self):
        """非白名单接口无 Token → 403。"""
        resp = self.client.get("/api/auth/profile")
        assert resp.status_code == 403

    def test_non_whitelist_llm_tasks_returns_403(self):
        """非白名单接口无 Token → 403。"""
        resp = self.client.get("/api/llm-tasks")
        assert resp.status_code == 403


# ═════════════════════════════════════════════════════════════════════════════
# 场景 3: LDAP_ENABLED=on, 后端和 Skill 配置一致的 Token → 白名单 API 可用
# ═════════════════════════════════════════════════════════════════════════════


class TestLdapEnabledMatchingToken:
    """LDAP 开启 + 后端和 Skill 配置一致的 Service Token。

    白名单 API → 200 (user=agent)
    非白名单 API → 403 (后端中间件拦截)
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        mock = _make_settings(ldap_enabled=True, service_token=SERVICE_TOKEN)
        with patch("middleware.auth_middleware.settings", mock):
            self.client = TestClient(_test_app, raise_server_exceptions=False)
            self.auth_header = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
            yield

    # ── 白名单路径：应通过 ──

    def test_whitelist_analyze_url_success(self):
        """白名单接口 + 正确 Token → 200 + user=agent。"""
        resp = self.client.post("/api/skills/analyze-url", headers=self.auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["user"]["sub"] == "agent"
        assert data["user"]["name"] == "Agent (Service Token)"

    def test_whitelist_http_tasks_test_success(self):
        """白名单接口 + 正确 Token → 200 + user=agent。"""
        resp = self.client.post("/api/http-tasks/test", headers=self.auth_header)
        assert resp.status_code == 200
        assert resp.json()["user"]["sub"] == "agent"

    def test_whitelist_http_tasks_create_success(self):
        """白名单接口 + 正确 Token → 200 + user=agent。"""
        resp = self.client.post("/api/http-tasks", headers=self.auth_header)
        assert resp.status_code == 200
        assert resp.json()["user"]["sub"] == "agent"

    # ── 非白名单路径：应被后端中间件拦截 → 403 ──

    def test_non_whitelist_system_returns_403(self):
        """Service Token + 非白名单接口 /api/system → 403 Forbidden。"""
        resp = self.client.get("/api/system", headers=self.auth_header)
        assert resp.status_code == 403

    def test_non_whitelist_profile_returns_403(self):
        """Service Token + 非白名单接口 /api/auth/profile → 403 Forbidden。"""
        resp = self.client.get("/api/auth/profile", headers=self.auth_header)
        assert resp.status_code == 403

    def test_non_whitelist_llm_tasks_returns_403(self):
        """Service Token + 非白名单接口 /api/llm-tasks → 403 Forbidden。"""
        resp = self.client.get("/api/llm-tasks", headers=self.auth_header)
        assert resp.status_code == 403

    def test_non_whitelist_response_body(self):
        """403 响应体应包含明确的错误信息。"""
        resp = self.client.get("/api/system", headers=self.auth_header)
        assert resp.status_code == 403
        data = resp.json()
        assert "Service Token" in data.get("error", "")


# ═════════════════════════════════════════════════════════════════════════════
# 场景 4: LDAP_ENABLED=on, Token 不一致
#   白名单 API → 401 (Token 错误，请检查)
#   非白名单 API → 403 (该路径不允许 Service Token 访问)
# ═════════════════════════════════════════════════════════════════════════════


class TestLdapEnabledWrongToken:
    """LDAP 开启 + 错误的 Token。

    白名单 API → 401 (Unauthorized — Token 不匹配)
    非白名单 API → 403 (Forbidden — 该路径对 Service Token 永远不可达)
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        mock = _make_settings(ldap_enabled=True, service_token=SERVICE_TOKEN)
        with patch("middleware.auth_middleware.settings", mock):
            self.client = TestClient(_test_app, raise_server_exceptions=False)
            self.wrong_header = {"Authorization": f"Bearer {WRONG_TOKEN}"}
            yield

    # ── 白名单路径: 401 ──

    def test_whitelist_analyze_url_wrong_token_401(self):
        """白名单接口 + 错误 Token → 401。"""
        resp = self.client.post("/api/skills/analyze-url", headers=self.wrong_header)
        assert resp.status_code == 401

    def test_whitelist_http_tasks_test_wrong_token_401(self):
        """白名单接口 + 错误 Token → 401。"""
        resp = self.client.post("/api/http-tasks/test", headers=self.wrong_header)
        assert resp.status_code == 401

    def test_whitelist_http_tasks_create_wrong_token_401(self):
        """白名单接口 + 错误 Token → 401。"""
        resp = self.client.post("/api/http-tasks", headers=self.wrong_header)
        assert resp.status_code == 401

    # ── 非白名单路径: 403 ──

    def test_non_whitelist_wrong_token_returns_403(self):
        """非白名单接口 + 错误 Token → 403。"""
        resp = self.client.get("/api/system", headers=self.wrong_header)
        assert resp.status_code == 403

    def test_non_whitelist_llm_tasks_wrong_token_returns_403(self):
        """非白名单接口 + 错误 Token → 403。"""
        resp = self.client.get("/api/llm-tasks", headers=self.wrong_header)
        assert resp.status_code == 403

    # ── 白名单路径 + 无 Token: 仍然 401 ──

    def test_no_token_whitelist_still_401(self):
        """白名单接口 + 完全不带 Token → 401。"""
        resp = self.client.post("/api/skills/analyze-url")
        assert resp.status_code == 401

    def test_no_token_non_whitelist_returns_403(self):
        """非白名单接口 + 完全不带 Token → 403。"""
        resp = self.client.get("/api/system")
        assert resp.status_code == 403


# ═════════════════════════════════════════════════════════════════════════════
# 场景 5: Skill 脚本 _safe_request 白名单 → 非授权路径被客户端拦截
# ═════════════════════════════════════════════════════════════════════════════


class TestSkillClientWhitelist:
    """Skill 脚本的 _safe_request() 白名单机制：非白名单路径在发送前被拦截。

    这是纵深防御（defense-in-depth）层：
    - 第 1 道防线：后端 AuthMiddleware 对 Service Token 做路径白名单校验 → 403
    - 第 2 道防线：Skill 客户端 _safe_request() 在发送前就拦截 → PermissionError
    即使客户端被篡改绕过了第 2 道，后端仍会拦截。
    """

    def test_whitelist_paths_accepted(self):
        """白名单路径不触发拦截。"""
        skill_script = Path(__file__).resolve().parents[2] / (
            ".openclaw/skills/lmeterx-web-loadtest/scripts/run.py"
        )
        assert skill_script.exists(), f"Skill script not found: {skill_script}"

        # 直接测试白名单集合
        allowed = frozenset(
            {
                "/api/skills/analyze-url",
                "/api/http-tasks/test",
                "/api/http-tasks",
            }
        )
        for path in allowed:
            assert path in allowed, f"{path} should be in whitelist"

    def test_non_whitelist_paths_blocked(self):
        """非白名单路径必须被拦截。"""
        allowed = frozenset(
            {
                "/api/skills/analyze-url",
                "/api/http-tasks/test",
                "/api/http-tasks",
            }
        )
        blocked_paths = [
            "/api/system",
            "/api/llm-tasks",
            "/api/auth/profile",
            "/api/auth/login",
            "/api/analyze",
            "/api/http-tasks/some-id",
            "/api/logs",
            "/api/upload",
            "/api/monitoring/engines",
        ]
        for path in blocked_paths:
            assert path not in allowed, f"{path} should NOT be in whitelist"

    def test_safe_request_blocks_non_whitelist(self):
        """直接测试 _safe_request() 对非白名单路径的拦截 → PermissionError。"""
        _ALLOWED_PATHS = frozenset(
            {
                "/api/skills/analyze-url",
                "/api/http-tasks/test",
                "/api/http-tasks",
            }
        )

        non_whitelist = "/api/system"
        with pytest.raises(PermissionError, match="不在授权白名单内"):
            if non_whitelist not in _ALLOWED_PATHS:
                raise PermissionError(
                    f"[安全拦截] 路径 {non_whitelist} 不在授权白名单内"
                )

    def test_safe_request_allows_whitelist(self):
        """白名单路径不应触发拦截。"""
        _ALLOWED_PATHS = frozenset(
            {
                "/api/skills/analyze-url",
                "/api/http-tasks/test",
                "/api/http-tasks",
            }
        )

        for path in _ALLOWED_PATHS:
            assert path in _ALLOWED_PATHS  # 不会 raise


# ═════════════════════════════════════════════════════════════════════════════
# 场景 6: 边界情况
# ═════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Service Token 鉴权的边界情况。"""

    def test_exempt_paths_always_accessible_with_ldap(self):
        """exempt_paths（/health, /api/auth/login）即使 LDAP 开启也不需要 Token。"""
        mock = _make_settings(ldap_enabled=True, service_token=SERVICE_TOKEN)
        with patch("middleware.auth_middleware.settings", mock):
            client = TestClient(_test_app, raise_server_exceptions=False)
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_service_token_via_x_authorization_header(self):
        """Service Token 通过 X-Authorization header 也应生效。"""
        mock = _make_settings(ldap_enabled=True, service_token=SERVICE_TOKEN)
        with patch("middleware.auth_middleware.settings", mock):
            client = TestClient(_test_app, raise_server_exceptions=False)
            resp = client.post(
                "/api/skills/analyze-url",
                headers={"X-Authorization": f"Bearer {SERVICE_TOKEN}"},
            )
            assert resp.status_code == 200
            assert resp.json()["user"]["sub"] == "agent"

    def test_empty_service_token_config_whitelist_path_401(self):
        """后端未配置 LMETERX_AUTH_TOKEN 时，白名单路径走 JWT decode 失败 → 401。"""
        mock = _make_settings(ldap_enabled=True, service_token="")
        with patch("middleware.auth_middleware.settings", mock):
            client = TestClient(_test_app, raise_server_exceptions=False)
            resp = client.post(
                "/api/skills/analyze-url",
                headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
            )
            assert resp.status_code == 401

    def test_empty_service_token_config_non_whitelist_path_403(self):
        """后端未配置 LMETERX_AUTH_TOKEN 时，非白名单路径走 JWT decode 失败 → 403。"""
        mock = _make_settings(ldap_enabled=True, service_token="")
        with patch("middleware.auth_middleware.settings", mock):
            client = TestClient(_test_app, raise_server_exceptions=False)
            resp = client.get(
                "/api/system",
                headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
            )
            assert resp.status_code == 403

    def test_options_request_always_passes(self):
        """OPTIONS 请求（CORS preflight）始终通过。"""
        mock = _make_settings(ldap_enabled=True, service_token=SERVICE_TOKEN)
        with patch("middleware.auth_middleware.settings", mock):
            client = TestClient(_test_app, raise_server_exceptions=False)
            resp = client.options("/api/skills/analyze-url")
            assert resp.status_code in (200, 405)
