"""
System config API tests.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from model.system import AIServiceConfig, SystemConfigListResponse, SystemConfigResponse
from utils.masking import mask_config_value

client = TestClient(app)


class TestSystemAPI:
    """System config API tests."""

    @patch("api.api_system.get_system_configs_svc")
    def test_get_system_configs(self, mock_get_configs):
        mock_get_configs.return_value = SystemConfigListResponse(
            data=[
                SystemConfigResponse(
                    config_key="host",
                    config_value="https://api.example.com",
                    description="AI host",
                    created_at="2025-01-01T00:00:00Z",
                    updated_at="2025-01-01T00:00:00Z",
                )
            ],
            status="success",
            error=None,
        )
        response = client.get("/api/system")
        assert response.status_code == 200
        assert response.json()["data"][0]["config_key"] == "host"

    @patch("api.api_system.get_system_configs_internal_svc")
    def test_get_system_configs_internal(self, mock_get_internal):
        mock_get_internal.return_value = SystemConfigListResponse(
            data=[
                SystemConfigResponse(
                    config_key="api_key",
                    config_value="sk-xxx",
                    description="AI key",
                    created_at="2025-01-01T00:00:00Z",
                    updated_at="2025-01-01T00:00:00Z",
                )
            ],
            status="success",
            error=None,
        )
        response = client.get("/api/system/internal")
        assert response.status_code == 200
        assert response.json()["data"][0]["config_key"] == "api_key"

    @patch("api.api_system.create_system_config_svc")
    def test_create_system_config(self, mock_create):
        mock_create.return_value = SystemConfigResponse(
            config_key="host",
            config_value="https://api.example.com",
            description="AI host",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        response = client.post(
            "/api/system",
            json={
                "config_key": "host",
                "config_value": "https://api.example.com",
                "description": "AI host",
            },
        )
        assert response.status_code == 200
        assert response.json()["config_key"] == "host"

    @patch("api.api_system.update_system_config_svc")
    def test_update_system_config(self, mock_update):
        mock_update.return_value = SystemConfigResponse(
            config_key="host",
            config_value="https://api.example.com/v2",
            description="AI host",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-02T00:00:00Z",
        )
        response = client.put(
            "/api/system/host",
            json={
                "config_key": "host",
                "config_value": "https://api.example.com/v2",
                "description": "AI host",
            },
        )
        assert response.status_code == 200
        assert response.json()["config_value"].endswith("/v2")

    @patch("api.api_system.delete_system_config_svc")
    def test_delete_system_config(self, mock_delete):
        mock_delete.return_value = {"status": "success"}
        response = client.delete("/api/system/host")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("api.api_system.get_ai_service_config_svc")
    def test_get_ai_service_config(self, mock_get_ai_config):
        mock_get_ai_config.return_value = AIServiceConfig(
            host="https://api.example.com", model="gpt-4", api_key="sk-xxx"
        )
        response = client.get("/api/system/ai-service")
        assert response.status_code == 200
        assert response.json()["model"] == "gpt-4"


@pytest.mark.asyncio
async def test_batch_upsert_system_configs(mock_db_session, mock_request):
    mock_request.state.db = mock_db_session
    test_configs = [
        {
            "config_key": "test_host",
            "config_value": "https://api.test.com",
            "description": "Test host configuration",
        },
        {
            "config_key": "test_model",
            "config_value": "gpt-4",
            "description": "Test model configuration",
        },
        {
            "config_key": "test_api_key",
            "config_value": "sk-test-key",
            "description": "Test API key configuration",
        },
    ]

    @asynccontextmanager
    async def mock_session_factory():
        yield mock_db_session

    with patch("middleware.db_middleware.async_session_factory") as mock_factory:
        mock_factory.return_value = mock_session_factory()
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/system/batch", json={"configs": test_configs}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["data"]) == 3

            for config in data["data"]:
                assert config["config_key"] in [
                    "test_host",
                    "test_model",
                    "test_api_key",
                ]
                if config["config_key"] == "test_api_key":
                    expected_value = mask_config_value(
                        config["config_key"], "sk-test-key"
                    )
                    assert config["config_value"] == expected_value


@pytest.mark.asyncio
async def test_batch_upsert_mixed_operations(mock_db_session, mock_request):
    mock_request.state.db = mock_db_session
    mixed_configs = [
        {
            "config_key": "test_existing",
            "config_value": "updated_value",
            "description": "Updated configuration",
        },
        {
            "config_key": "test_new",
            "config_value": "new_value",
            "description": "New configuration",
        },
    ]

    @asynccontextmanager
    async def mock_session_factory():
        yield mock_db_session

    with patch("middleware.db_middleware.async_session_factory") as mock_factory:
        mock_factory.return_value = mock_session_factory()
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/system/batch", json={"configs": mixed_configs}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["data"]) == 2
            config_keys = [config["config_key"] for config in data["data"]]
            assert "test_existing" in config_keys
            assert "test_new" in config_keys
