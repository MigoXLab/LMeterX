"""
Common task API tests.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from model.common_task import (
    CommonComparisonMetrics,
    CommonComparisonRequest,
    CommonComparisonResponse,
    CommonComparisonTaskInfo,
    CommonComparisonTasksResponse,
    CommonTaskCreateRsp,
    CommonTaskPagination,
    CommonTaskResponse,
    CommonTaskResultItem,
    CommonTaskResultRsp,
    CommonTaskStatusRsp,
)

client = TestClient(app)


class TestCommonTaskAPI:
    """Common task API tests."""

    @patch("api.api_common_task.get_common_tasks_svc")
    def test_get_common_tasks(self, mock_get_common_tasks):
        mock_get_common_tasks.return_value = CommonTaskResponse(
            data=[{"id": "ct_1", "name": "Common Task"}],
            pagination=CommonTaskPagination(
                page=1, page_size=10, total=1, total_pages=1
            ),
            status="success",
        )
        response = client.get("/api/common-tasks")
        assert response.status_code == 200
        assert response.json()["data"][0]["id"] == "ct_1"

    @patch("api.api_common_task.get_common_tasks_status_svc")
    def test_get_common_tasks_status(self, mock_get_status):
        mock_get_status.return_value = CommonTaskStatusRsp(
            data=[{"status": "running", "count": 3}],
            timestamp=1700000000,
            status="success",
        )
        response = client.get("/api/common-tasks/status")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("api.api_common_task.create_common_task_svc")
    def test_create_common_task(self, mock_create):
        mock_create.return_value = CommonTaskCreateRsp(
            task_id="ct_123", status="created", message="ok"
        )
        payload = {
            "temp_task_id": "temp_1",
            "name": "Common Task",
            "method": "POST",
            "target_url": "https://api.example.com/echo",
            "headers": [],
            "cookies": [],
            "duration": 60,
            "concurrent_users": 5,
        }
        response = client.post("/api/common-tasks", json=payload)
        assert response.status_code == 200
        assert response.json()["task_id"] == "ct_123"

    def test_create_common_task_invalid_method(self):
        payload = {
            "temp_task_id": "temp_2",
            "name": "Common Task",
            "method": "BAD",
            "target_url": "https://api.example.com/echo",
            "headers": [],
            "cookies": [],
            "duration": 60,
            "concurrent_users": 5,
        }
        response = client.post("/api/common-tasks", json=payload)
        assert response.status_code == 422

    @patch("api.api_common_task.stop_common_task_svc")
    def test_stop_common_task(self, mock_stop):
        mock_stop.return_value = CommonTaskCreateRsp(
            task_id="ct_456", status="stopping", message="Stop sent"
        )
        response = client.post("/api/common-tasks/stop/ct_456")
        assert response.status_code == 200
        assert response.json()["status"] == "stopping"

    @patch("api.api_common_task.get_common_task_result_svc")
    def test_get_common_task_result(self, mock_get_result):
        item = CommonTaskResultItem(
            id=1,
            task_id="ct_789",
            metric_type="http",
            request_count=100,
            failure_count=1,
            avg_response_time=120.5,
            min_response_time=50.0,
            max_response_time=300.0,
            median_response_time=110.0,
            percentile_90_response_time=200.0,
            rps=15.0,
            avg_content_length=256.0,
            created_at="2025-01-01T00:00:00Z",
        )
        mock_get_result.return_value = CommonTaskResultRsp(
            results=[item], status="success", error=None
        )
        response = client.get("/api/common-tasks/ct_789/results")
        assert response.status_code == 200
        assert response.json()["results"][0]["task_id"] == "ct_789"

    @patch("api.api_common_task.update_common_task_svc")
    def test_update_common_task(self, mock_update):
        mock_update.return_value = {"status": "success"}
        response = client.put("/api/common-tasks/ct_101", json={"name": "Renamed"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("api.api_common_task.delete_common_task_svc")
    def test_delete_common_task(self, mock_delete):
        mock_delete.return_value = {"status": "success"}
        response = client.delete("/api/common-tasks/ct_202")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("api.api_common_task.get_common_task_svc")
    def test_get_common_task(self, mock_get):
        mock_get.return_value = {"id": "ct_303", "name": "Common Task"}
        response = client.get("/api/common-tasks/ct_303")
        assert response.status_code == 200
        assert response.json()["id"] == "ct_303"

    @patch("api.api_common_task.get_common_task_status_svc")
    def test_get_common_task_status(self, mock_status):
        mock_status.return_value = {"status": "running"}
        response = client.get("/api/common-tasks/ct_404/status")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

    @patch("api.api_common_task.get_common_tasks_for_comparison_svc")
    def test_get_common_tasks_for_comparison(self, mock_get_available):
        mock_get_available.return_value = CommonComparisonTasksResponse(
            data=[
                CommonComparisonTaskInfo(
                    task_id="ct_1",
                    task_name="Common 1",
                    method="GET",
                    target_url="https://api.example.com/a",
                    concurrent_users=5,
                    created_at="2025-01-01T00:00:00Z",
                    duration=60,
                )
            ],
            status="success",
            error=None,
        )
        response = client.get("/api/common-tasks/comparison/available")
        assert response.status_code == 200
        assert response.json()["data"][0]["task_id"] == "ct_1"

    @patch("api.api_common_task.compare_common_performance_svc")
    def test_compare_common_performance(self, mock_compare):
        mock_compare.return_value = CommonComparisonResponse(
            data=[
                CommonComparisonMetrics(
                    task_id="ct_1",
                    task_name="Common 1",
                    method="GET",
                    target_url="https://api.example.com/a",
                    concurrent_users=5,
                    duration="60",
                    request_count=100,
                    failure_count=1,
                    success_rate=0.99,
                    rps=12.0,
                    avg_response_time=120.0,
                    p90_response_time=200.0,
                    min_response_time=50.0,
                    max_response_time=300.0,
                    avg_content_length=256.0,
                )
            ],
            status="success",
            error=None,
        )
        response = client.post(
            "/api/common-tasks/comparison",
            json=CommonComparisonRequest(selected_tasks=["ct_1", "ct_2"]).dict(),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_compare_common_performance_validation_error(self):
        response = client.post(
            "/api/common-tasks/comparison",
            json={"selected_tasks": ["ct_1"]},
        )
        assert response.status_code == 422
