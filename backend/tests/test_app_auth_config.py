"""
Application auth middleware configuration regression tests.
"""

import importlib
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from middleware.auth_middleware import AuthMiddleware  # noqa: E402
from utils.auth_settings import get_auth_settings  # noqa: E402


def _auth_middleware_options(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("LDAP_ENABLED", "1")
    get_auth_settings.cache_clear()

    import app as app_module

    app_module = importlib.reload(app_module)
    auth_middlewares = [
        middleware
        for middleware in app_module.app.user_middleware
        if middleware.cls is AuthMiddleware
    ]
    assert auth_middlewares, "AuthMiddleware should be mounted when LDAP is enabled"
    middleware_options = getattr(auth_middlewares[0], "kwargs", None) or getattr(
        auth_middlewares[0], "options", {}
    )
    return middleware_options


def _auth_exempt_prefixes(monkeypatch):
    return _auth_middleware_options(monkeypatch).get("exempt_prefixes", [])


def test_collections_prefix_not_exempt_when_ldap_enabled(monkeypatch):
    """Collection APIs require AuthMiddleware user context."""
    exempt_prefixes = _auth_exempt_prefixes(monkeypatch)
    assert "/api/collections" not in exempt_prefixes
    get_auth_settings.cache_clear()


def test_agent_tasks_prefix_not_exempt_when_ldap_enabled(monkeypatch):
    """Agent task metadata and copy templates require authentication."""
    exempt_prefixes = _auth_exempt_prefixes(monkeypatch)
    assert "/api/agent-tasks" not in exempt_prefixes
    get_auth_settings.cache_clear()


def test_copy_template_suffix_requires_auth_when_parent_prefix_is_exempt(monkeypatch):
    """Copying needs authenticated user context for its owner check."""
    middleware_options = _auth_middleware_options(monkeypatch)
    assert "/api/llm-tasks" in middleware_options.get("exempt_prefixes", [])
    assert "/api/http-tasks" in middleware_options.get("exempt_prefixes", [])
    assert "/copy-template" in middleware_options.get("auth_required_suffixes", [])
    get_auth_settings.cache_clear()
