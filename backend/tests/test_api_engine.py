"""
Engine API endpoint tests.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


class TestEngineRegisterAPI:
    @patch("api.api_engine.engine_service.register_engine", new_callable=AsyncMock)
    def test_register_success(self, mock_register):
        mock_register.return_value = {
            "status": "registered",
            "heartbeat_interval": 10,
            "task_poll_interval": 3,
        }

        response = client.post(
            "/api/engine/register",
            json={
                "engine_id": "eng-001",
                "cluster_id": "gpu-prod",
                "capabilities": {
                    "cpu_cores": 4.0,
                    "memory_gb": 8.0,
                    "max_concurrent_tasks": 1,
                },
                "version": "1.0.0",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "registered"
        assert data["heartbeat_interval"] == 10
        mock_register.assert_called_once()

    def test_register_missing_fields(self):
        response = client.post(
            "/api/engine/register",
            json={"cluster_id": "gpu-prod"},
        )
        assert response.status_code == 422


class TestEngineHeartbeatAPI:
    @patch("api.api_engine.engine_service.process_heartbeat", new_callable=AsyncMock)
    def test_heartbeat_success(self, mock_hb):
        mock_hb.return_value = {"status": "ok", "commands": []}

        response = client.post(
            "/api/engine/heartbeat",
            json={
                "engine_id": "eng-001",
                "cluster_id": "gpu-prod",
                "running_tasks": ["task-123"],
                "cpu_usage": 45.0,
                "memory_usage": 60.0,
                "available_slots": 0,
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @patch("api.api_engine.engine_service.process_heartbeat", new_callable=AsyncMock)
    def test_heartbeat_not_registered(self, mock_hb):
        mock_hb.return_value = {"status": "not_registered"}

        response = client.post(
            "/api/engine/heartbeat",
            json={
                "engine_id": "eng-unknown",
                "cluster_id": "gpu-prod",
                "running_tasks": [],
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "available_slots": 1,
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "not_registered"


class TestEngineClaimTaskAPI:
    @patch("api.api_engine.engine_service.claim_task", new_callable=AsyncMock)
    def test_claim_task_found(self, mock_claim):
        mock_claim.return_value = {
            "id": "task-001",
            "type": "llm",
            "config": {"model": "gpt-4", "duration": 60},
            "test_data_url": None,
        }

        response = client.post(
            "/api/engine/tasks/claim",
            json={
                "engine_id": "eng-001",
                "cluster_id": "gpu-prod",
                "task_types": ["llm", "http"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task"]["id"] == "task-001"
        assert data["task"]["type"] == "llm"

    @patch("api.api_engine.engine_service.claim_task", new_callable=AsyncMock)
    def test_claim_task_empty(self, mock_claim):
        mock_claim.return_value = None

        response = client.post(
            "/api/engine/tasks/claim",
            json={
                "engine_id": "eng-001",
                "cluster_id": "gpu-prod",
                "task_types": ["llm"],
            },
        )

        assert response.status_code == 200
        assert response.json()["task"] is None


class TestEngineTaskStatusAPI:
    @patch("api.api_engine.engine_service.update_task_status", new_callable=AsyncMock)
    def test_update_status_success(self, mock_update):
        mock_update.return_value = True

        response = client.put(
            "/api/engine/tasks/task-001/status",
            json={
                "engine_id": "eng-001",
                "status": "running",
                "progress": 50,
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @patch("api.api_engine.engine_service.update_task_status", new_callable=AsyncMock)
    def test_update_status_not_owned(self, mock_update):
        mock_update.return_value = False

        response = client.put(
            "/api/engine/tasks/task-001/status",
            json={
                "engine_id": "eng-wrong",
                "status": "running",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "error"


class TestEngineTaskResultsAPI:
    @patch("api.api_engine.engine_service.submit_task_results", new_callable=AsyncMock)
    def test_submit_results_success(self, mock_submit):
        mock_submit.return_value = True

        response = client.post(
            "/api/engine/tasks/task-001/results",
            json={
                "engine_id": "eng-001",
                "locust_results": {"num_requests": 100, "rps": 10.0},
                "final_status": "completed",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @patch("api.api_engine.engine_service.submit_task_results", new_callable=AsyncMock)
    def test_submit_results_not_found(self, mock_submit):
        mock_submit.return_value = False

        response = client.post(
            "/api/engine/tasks/task-999/results",
            json={
                "engine_id": "eng-001",
                "final_status": "completed",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "error"


class TestEngineStoppingTasksAPI:
    @patch("api.api_engine.engine_service.get_stopping_tasks", new_callable=AsyncMock)
    def test_get_stopping_tasks(self, mock_get):
        mock_get.return_value = ["task-1", "task-2"]

        response = client.get(
            "/api/engine/tasks/stopping",
            params={"engine_id": "eng-001", "cluster_id": "gpu-prod"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_ids"] == ["task-1", "task-2"]

    @patch("api.api_engine.engine_service.get_stopping_tasks", new_callable=AsyncMock)
    def test_get_stopping_tasks_empty(self, mock_get):
        mock_get.return_value = []

        response = client.get(
            "/api/engine/tasks/stopping",
            params={"engine_id": "eng-001", "cluster_id": "gpu-prod"},
        )

        assert response.status_code == 200
        assert response.json()["task_ids"] == []
