"""
Core API endpoint tests (health/root).
"""

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


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
