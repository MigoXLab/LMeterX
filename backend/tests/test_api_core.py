"""
Core API endpoint tests (health/root).
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module
from db.mysql import settings

client = TestClient(app_module.app)


class TestHealthAndRoot:
    """Health check and root path tests."""

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200


def test_testing_lifespan_has_no_database_or_scheduler_side_effects():
    """Starting a unit-test client must not touch production dependencies."""
    with (
        patch("db.mysql.async_session_factory") as session_factory,
        patch.object(app_module, "start_scheduler") as start_scheduler,
        patch.object(app_module, "stop_scheduler") as stop_scheduler,
    ):
        with TestClient(app_module.app):
            pass

    session_factory.assert_not_called()
    start_scheduler.assert_not_called()
    stop_scheduler.assert_not_called()


def test_unit_test_database_settings_cannot_target_rds():
    """Test bootstrap overrides any database settings loaded from .env."""
    assert settings.DB_HOST == "127.0.0.1"
    assert settings.DB_PORT == 1
    assert settings.DB_NAME == "lmeterx_unit_test"
