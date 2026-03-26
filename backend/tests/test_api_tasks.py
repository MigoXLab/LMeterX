"""
Task API tests.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from model.task import (
    Pagination,
    TaskCreateRsp,
    TaskResponse,
    TaskResultItem,
    TaskResultRsp,
    TaskStatusRsp,
)

client = TestClient(app)


class TestTaskAPI:
    """Task-related API tests."""

    @patch("api.api_task.get_tasks_svc")
    def test_get_tasks_default_params(self, mock_get_tasks):
        mock_response = TaskResponse(
            data=[
                {
                    "id": "task_123",
                    "name": "Test Task",
                    "status": "completed",
                    "created_at": "2025-01-01T00:00:00Z",
                }
            ],
            pagination=Pagination(page=1, page_size=10, total=1, total_pages=1),
            status="success",
        )
        mock_get_tasks.return_value = mock_response

        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == "task_123"

    @patch("api.api_task.get_tasks_svc")
    def test_get_tasks_with_filters(self, mock_get_tasks):
        mock_response = TaskResponse(
            data=[],
            pagination=Pagination(page=1, page_size=5, total=0, total_pages=0),
            status="success",
        )
        mock_get_tasks.return_value = mock_response

        response = client.get("/api/tasks?page=1&pageSize=5&status=running&search=test")
        assert response.status_code == 200
        mock_get_tasks.assert_called_once()

    @patch("api.api_task.get_tasks_status_svc")
    def test_get_tasks_status(self, mock_get_status):
        mock_response = TaskStatusRsp(
            data=[
                {"status": "running", "count": 5},
                {"status": "completed", "count": 10},
                {"status": "failed", "count": 2},
            ],
            timestamp=1640995200,
            status="success",
        )
        mock_get_status.return_value = mock_response

        response = client.get("/api/tasks/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["data"]) == 3

    @patch("api.api_task.create_task_svc")
    def test_create_task_success(self, mock_create_task):
        task_data = {
            "temp_task_id": "temp_123",
            "name": "Performance Test Task",
            "target_host": "https://api.example.com",
            "api_path": "/chat/completions",
            "model": "gpt-3.5-turbo",
            "duration": 300,
            "concurrent_users": 10,
            "spawn_rate": 2,
            "chat_type": 1,
            "stream_mode": True,
            "headers": [],
        }

        mock_response = TaskCreateRsp(
            task_id="task_456", status="created", message="Task created successfully"
        )
        mock_create_task.return_value = mock_response

        response = client.post("/api/tasks", json=task_data)
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_456"
        assert data["status"] == "created"
        assert "successfully" in data["message"]

    def test_create_task_validation_error(self):
        invalid_data = {"name": "Test Task"}
        response = client.post("/api/tasks", json=invalid_data)
        assert response.status_code == 422

    @patch("api.api_task.stop_task_svc")
    def test_stop_task(self, mock_stop_task):
        mock_response = TaskCreateRsp(
            task_id="task_789", status="stopping", message="Stop request sent"
        )
        mock_stop_task.return_value = mock_response

        response = client.post("/api/tasks/stop/task_789")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task_789"
        assert data["status"] == "stopping"

    @patch("api.api_task.get_task_result_svc")
    def test_get_task_results(self, mock_get_results):
        result_item = TaskResultItem(
            id=1,
            task_id="task_123",
            metric_type="http",
            request_count=100,
            failure_count=2,
            avg_response_time=150.5,
            min_response_time=50.0,
            max_response_time=500.0,
            median_response_time=140.0,
            percentile_95_response_time=300.0,
            rps=10.5,
            avg_content_length=256.0,
            total_tps=25.0,
            completion_tps=15.0,
            avg_total_tokens_per_req=50.0,
            avg_completion_tokens_per_req=30.0,
            created_at="2025-01-01T00:00:00Z",
        )

        mock_response = TaskResultRsp(
            results=[result_item], status="success", error=None
        )
        mock_get_results.return_value = mock_response

        response = client.get("/api/tasks/task_123/results")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["results"]) == 1
        assert data["results"][0]["task_id"] == "task_123"

    @patch("api.api_task.get_task_svc")
    def test_get_single_task(self, mock_get_task):
        mock_response = {
            "id": "task_123",
            "name": "Test Task",
            "status": "completed",
            "target_host": "https://api.example.com",
            "model": "gpt-3.5-turbo",
            "created_at": "2025-01-01T00:00:00Z",
        }
        mock_get_task.return_value = mock_response

        response = client.get("/api/tasks/task_123")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "task_123"
        assert data["name"] == "Test Task"


class TestTaskErrors:
    """Task API error handling tests."""

    @patch("api.api_task.get_task_svc")
    def test_task_not_found(self, mock_get_task):
        from fastapi import HTTPException

        mock_get_task.side_effect = HTTPException(
            status_code=404, detail="Task not found"
        )

        response = client.get("/api/tasks/nonexistent_task")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data.lower()

    @patch("api.api_task.create_task_svc")
    def test_create_task_server_error(self, mock_create_task):
        mock_response = TaskCreateRsp(
            task_id="temp_error", status="error", message="Database connection failed"
        )
        mock_create_task.return_value = mock_response

        task_data = {
            "temp_task_id": "temp_error",
            "name": "Error Test Task",
            "target_host": "https://api.example.com",
            "api_path": "/chat/completions",
            "model": "gpt-3.5-turbo",
            "duration": 300,
            "concurrent_users": 10,
            "spawn_rate": 2,
            "chat_type": 1,
            "stream_mode": True,
            "headers": [],
        }

        response = client.post("/api/tasks", json=task_data)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Database connection failed" in data["message"]


class TestTaskParameterValidation:
    """Task API parameter validation tests."""

    def test_get_tasks_invalid_page(self):
        response = client.get("/api/tasks?page=0")
        assert response.status_code == 422

    def test_get_tasks_invalid_page_size(self):
        response = client.get("/api/tasks?pageSize=101")
        assert response.status_code == 422
