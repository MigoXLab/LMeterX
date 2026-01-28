"""
Log API tests.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from model.log import LogContentResponse

client = TestClient(app)


class TestLogAPI:
    """Log-related API tests."""

    @patch("api.api_log.get_service_log_svc")
    def test_get_service_log_default(self, mock_get_log):
        mock_response = LogContentResponse(
            content="2025-01-01 00:00:00 INFO: Service started successfully\n"
            "2025-01-01 00:01:00 INFO: Processing request",
            file_size=1024,
        )
        mock_get_log.return_value = mock_response

        response = client.get("/api/logs/backend")
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["file_size"] == 1024
        assert "Service started successfully" in data["content"]

    @patch("api.api_log.get_service_log_svc")
    def test_get_service_log_with_params(self, mock_get_log):
        mock_response = LogContentResponse(content="Latest log content", file_size=512)
        mock_get_log.return_value = mock_response

        response = client.get("/api/logs/engine?offset=100&tail=50")
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["file_size"] == 512

    @patch("api.api_log.get_task_log_svc")
    def test_get_task_log(self, mock_get_task_log):
        mock_response = LogContentResponse(
            content="Task started\nTask in progress...\nTask completed", file_size=2048
        )
        mock_get_task_log.return_value = mock_response

        response = client.get("/api/logs/task/task_123")
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["file_size"] == 2048
        assert "Task started" in data["content"]

    @patch("api.api_log.get_task_log_svc")
    def test_get_task_log_with_tail(self, mock_get_task_log):
        mock_response = LogContentResponse(
            content="Last 10 lines of log", file_size=256
        )
        mock_get_task_log.return_value = mock_response

        response = client.get("/api/logs/task/task_456?tail=10")
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["file_size"] == 256

    @patch("api.api_log.get_service_log_svc")
    def test_get_service_log_invalid_tail(self, mock_get_log):
        mock_get_log.return_value = LogContentResponse(
            content="test content", file_size=100
        )

        response = client.get("/api/logs/backend?tail=-1")
        assert response.status_code == 422


class TestLogParameterValidation:
    """Log API parameter validation tests."""

    def test_get_service_log_invalid_offset(self):
        response = client.get("/api/logs/backend?offset=-1")
        assert response.status_code == 422
