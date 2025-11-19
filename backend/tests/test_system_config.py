"""
Test cases for system configuration batch operations.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from utils.tools import mask_config_value


@pytest.mark.asyncio
async def test_batch_upsert_system_configs(mock_db_session, mock_request):
    """Test batch upsert system configurations."""
    # Mock the database session
    mock_request.state.db = mock_db_session

    # Test data
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

    # Mock the database session factory used by middleware
    with patch("middleware.db_middleware.async_session_factory") as mock_factory:
        mock_factory.return_value = mock_session_factory()
        with TestClient(app) as client:
            response = client.post("/api/system/batch", json={"configs": test_configs})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["data"]) == 3

            # Verify configurations were created
            for config in data["data"]:
                assert config["config_key"] in [
                    "test_host",
                    "test_model",
                    "test_api_key",
                ]
                # Sensitive values should be masked
                if config["config_key"] == "test_api_key":
                    expected_value = mask_config_value(
                        config["config_key"], "sk-test-key"
                    )
                    assert config["config_value"] == expected_value


@pytest.mark.asyncio
async def test_batch_upsert_mixed_operations(mock_db_session, mock_request):
    """Test batch upsert with mixed create and update operations."""
    # Mock the database session
    mock_request.state.db = mock_db_session

    # Test mixed operations (update existing + create new)
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
        with TestClient(app) as client:
            response = client.post("/api/system/batch", json={"configs": mixed_configs})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert len(data["data"]) == 2

            # Verify both operations worked
            config_keys = [config["config_key"] for config in data["data"]]
            assert "test_existing" in config_keys
            assert "test_new" in config_keys
