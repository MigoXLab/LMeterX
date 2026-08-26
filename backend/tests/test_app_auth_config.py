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


def test_collections_prefix_not_exempt_when_ldap_enabled(monkeypatch):
    """
    `/api/collections` must stay protected so AuthMiddleware injects
    request.state.user for collection APIs.
    """

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
    exempt_prefixes = middleware_options.get("exempt_prefixes", [])
    assert "/api/collections" not in exempt_prefixes

    get_auth_settings.cache_clear()
