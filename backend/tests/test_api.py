"""
Unit tests for LMeterX Backend API
Covers all major API interfaces
"""

import io
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from model.log import LogContentResponse
from model.task import (
    Pagination,
    TaskCreateRsp,
    TaskResponse,
    TaskResultItem,
    TaskResultRsp,
    TaskStatusRsp,
)
from model.upload import UploadedFileInfo, UploadFileRsp

# Create test client
client = TestClient(app)


class TestHealthAndRoot:
    """Health check and root path tests"""

    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200


class TestTaskAPI:
    """Task-related API tests"""

    @patch("api.api_task.get_tasks_svc")
    def test_get_tasks_default_params(self, mock_get_tasks):
        """Test get task list - default parameters"""
        # Mock service response
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
        """Test get task list - with filter conditions"""
        mock_response = TaskResponse(
            data=[],
            pagination=Pagination(page=1, page_size=5, total=0, total_pages=0),
            status="success",
        )
        mock_get_tasks.return_value = mock_response

        response = client.get("/api/tasks?page=1&pageSize=5&status=running&search=test")
        assert response.status_code == 200

        # Verify service was called correctly
        mock_get_tasks.assert_called_once()

    @patch("api.api_task.get_tasks_status_svc")
    def test_get_tasks_status(self, mock_get_status):
        """Test get task status"""
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
        """Test create task - success scenario"""
        # Prepare test data
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

        # Mock service response
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

    @patch("api.api_task.create_task_svc")
    def test_create_task_validation_error(self, mock_create_task):
        """Test create task - parameter validation error"""
        # Data missing required fields
        invalid_data = {
            "name": "Test Task"
            # Missing other required fields
        }

        response = client.post("/api/tasks", json=invalid_data)
        assert response.status_code == 422  # Validation error

    @patch("api.api_task.stop_task_svc")
    def test_stop_task(self, mock_stop_task):
        """Test stop task"""
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
        """Test get task results"""
        # Create correct TaskResultItem instance
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
            percentile_90_response_time=300.0,
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
        """Test get single task details"""
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


class TestLogAPI:
    """Log-related API tests"""

    @patch("api.api_log.get_service_log_svc")
    def test_get_service_log_default(self, mock_get_log):
        """Test get service log - default parameters"""
        mock_response = LogContentResponse(
            content="2025-01-01 00:00:00 INFO: Service started successfully\n2025-01-01 00:01:00 INFO: Processing request",
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
        """Test get service log - with parameters"""
        mock_response = LogContentResponse(content="Latest log content", file_size=512)
        mock_get_log.return_value = mock_response

        response = client.get("/api/logs/engine?offset=100&tail=50")
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert data["file_size"] == 512

    @patch("api.api_log.get_task_log_svc")
    def test_get_task_log(self, mock_get_task_log):
        """Test get task log"""
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
        """Test get task log - tail lines"""
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
        """Test get service log with invalid tail parameter"""
        # Mock to avoid actual file system access
        mock_get_log.return_value = LogContentResponse(
            content="test content", file_size=100
        )

        response = client.get("/api/logs/backend?tail=-1")  # tail must be >= 0
        assert response.status_code == 422  # Validation error


class TestUploadAPI:
    """File upload API tests"""

    @patch("api.api_upload.upload_file_svc")
    def test_upload_file_success(self, mock_upload):
        """Test file upload - success scenario"""
        # Prepare test file
        test_file_content = b"test certificate content"
        test_file = io.BytesIO(test_file_content)

        # Create correct UploadedFileInfo instance
        file_info = UploadedFileInfo(
            originalname="cert.pem",
            path="/uploads/cert_123.pem",
            size=len(test_file_content),
        )

        # Mock service response
        mock_response = UploadFileRsp(
            message="File uploaded successfully",
            task_id="task_123",
            files=[file_info],
            cert_config={"cert_file": "/uploads/cert_123.pem", "key_file": None},
        )
        mock_upload.return_value = mock_response

        # Send upload request
        files = {"files": ("cert.pem", test_file, "application/x-pem-file")}
        data = {"type": "cert", "cert_type": "cert_file", "task_id": "task_123"}

        response = client.post("/api/upload", files=files, data=data)
        assert response.status_code == 200

        response_data = response.json()
        assert "successfully" in response_data["message"]
        assert response_data["task_id"] == "task_123"
        assert len(response_data["files"]) == 1

    @patch("api.api_upload.upload_file_svc")
    def test_upload_multiple_files(self, mock_upload):
        """Test multiple file upload"""
        # Create correct UploadedFileInfo instances
        file_info1 = UploadedFileInfo(
            originalname="cert.pem", path="/uploads/cert_123.pem", size=100
        )
        file_info2 = UploadedFileInfo(
            originalname="key.pem", path="/uploads/key_123.pem", size=200
        )

        mock_response = UploadFileRsp(
            message="Files uploaded successfully",
            task_id="task_456",
            files=[file_info1, file_info2],
            cert_config={
                "cert_file": "/uploads/cert_123.pem",
                "key_file": "/uploads/key_123.pem",
            },
        )
        mock_upload.return_value = mock_response

        # Prepare test files
        files = [
            (
                "files",
                ("cert.pem", io.BytesIO(b"cert content"), "application/x-pem-file"),
            ),
            (
                "files",
                ("key.pem", io.BytesIO(b"key content"), "application/x-pem-file"),
            ),
        ]
        data = {"type": "cert", "cert_type": "both", "task_id": "task_456"}

        response = client.post("/api/upload", files=files, data=data)
        assert response.status_code == 200

        response_data = response.json()
        assert "successfully" in response_data["message"]
        assert len(response_data["files"]) == 2

    def test_upload_no_file(self):
        """Test upload without file"""
        data = {"type": "cert", "cert_type": "cert_file", "task_id": "task_789"}

        response = client.post("/api/upload", data=data)
        assert response.status_code == 422  # Validation error


class TestErrorHandling:
    """Error handling tests"""

    @patch("api.api_task.get_task_svc")
    def test_task_not_found(self, mock_get_task):
        """Test task not found scenario"""
        from fastapi import HTTPException

        mock_get_task.side_effect = HTTPException(
            status_code=404, detail="Task not found"
        )

        response = client.get("/api/tasks/nonexistent_task")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @patch("api.api_task.create_task_svc")
    def test_create_task_server_error(self, mock_create_task):
        """Test create task server error"""
        # Mock to return error response instead of raising exception
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


class TestParameterValidation:
    """Parameter validation tests"""

    def test_get_tasks_invalid_page(self):
        """Test get tasks with invalid page parameter"""
        response = client.get("/api/tasks?page=0")  # page must be >= 1
        assert response.status_code == 422  # Validation error

    def test_get_tasks_invalid_page_size(self):
        """Test get tasks with invalid page size parameter"""
        response = client.get("/api/tasks?pageSize=101")  # pageSize must be <= 100
        assert response.status_code == 422  # Validation error

    def test_get_service_log_invalid_offset(self):
        """Test get service log with invalid offset parameter"""
        response = client.get("/api/logs/backend?offset=-1")  # offset must be >= 0
        assert response.status_code == 422  # Validation error

    @patch("api.api_log.get_service_log_svc")
    def test_get_service_log_invalid_tail(self, mock_get_log):
        """Test get service log with invalid tail parameter"""
        # Mock to avoid actual file system access
        mock_get_log.return_value = LogContentResponse(
            content="test content", file_size=100
        )

        response = client.get("/api/logs/backend?tail=-1")  # tail must be >= 0
        assert response.status_code == 422  # Validation error


# To run tests, use the following command:
# pytest backend/tests/test_api.py -v
