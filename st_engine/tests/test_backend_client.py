"""
BackendClient unit tests: registration, heartbeat, claim, status, results, stopping.
"""

from unittest.mock import MagicMock, PropertyMock, patch

import httpx
import pytest

from client.backend_client import BackendClient


@pytest.fixture
def mock_httpx_client():
    """Patch the httpx.Client used internally by BackendClient."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.is_closed = False
    with patch("client.backend_client.httpx.Client", return_value=mock_client):
        bc = BackendClient()
        bc._client = mock_client
        yield bc, mock_client
        bc.close()


class TestBackendClientRegister:
    def test_register_success(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": "registered",
            "heartbeat_interval": 10,
            "task_poll_interval": 3,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        result = bc.register(
            engine_id="eng-001",
            cluster_id="gpu-prod",
            capabilities={
                "cpu_cores": 2.0,
                "memory_gb": 4.0,
                "max_concurrent_tasks": 1,
            },
            version="1.0.0",
        )

        assert result["status"] == "registered"
        mock_client.post.assert_called_once()

    def test_register_network_error(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        result = bc.register(
            engine_id="eng-001",
            cluster_id="gpu-prod",
            capabilities={},
        )

        assert result is None


class TestBackendClientHeartbeat:
    def test_heartbeat_success(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok", "commands": []}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        result = bc.heartbeat(
            engine_id="eng-001",
            cluster_id="gpu-prod",
            running_tasks=[],
            cpu_usage=10.0,
            memory_usage=30.0,
            available_slots=1,
        )

        assert result["status"] == "ok"

    def test_heartbeat_not_registered(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "not_registered"}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        result = bc.heartbeat(
            engine_id="eng-001",
            cluster_id="gpu-prod",
            running_tasks=[],
            cpu_usage=0.0,
            memory_usage=0.0,
            available_slots=1,
        )

        assert result["status"] == "not_registered"


class TestBackendClientClaimTask:
    def test_claim_task_found(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "task": {
                "id": "task-001",
                "type": "llm",
                "config": {"model": "gpt-4"},
                "test_data_url": None,
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        result = bc.claim_task(
            engine_id="eng-001",
            cluster_id="gpu-prod",
        )

        assert result is not None
        assert result["id"] == "task-001"
        assert result["type"] == "llm"

    def test_claim_task_none(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"task": None}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        result = bc.claim_task(
            engine_id="eng-001",
            cluster_id="gpu-prod",
        )

        assert result is None


class TestBackendClientSubmitResults:
    def test_submit_success(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp

        result = bc.submit_results(
            task_id="task-001",
            engine_id="eng-001",
            locust_results={"num_requests": 100},
            final_status="completed",
        )

        assert result is True

    def test_submit_failure(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client.post.return_value = mock_resp

        result = bc.submit_results(
            task_id="task-001",
            engine_id="eng-001",
            final_status="completed",
        )

        assert result is False


class TestBackendClientUpdateTaskStatus:
    def test_update_success(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        mock_resp.raise_for_status = MagicMock()
        mock_client.put.return_value = mock_resp

        result = bc.update_task_status(
            task_id="task-001",
            engine_id="eng-001",
            status="running",
            progress=50,
        )

        assert result is True

    def test_update_failure(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_client.put.side_effect = httpx.ConnectError("timeout")

        result = bc.update_task_status(
            task_id="task-001",
            engine_id="eng-001",
            status="running",
        )

        assert result is False


class TestBackendClientGetStoppingTasks:
    def test_returns_task_ids(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"task_ids": ["task-1", "task-2"]}
        mock_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_resp

        result = bc.get_stopping_tasks(engine_id="eng-001", cluster_id="gpu-prod")

        assert result == ["task-1", "task-2"]

    def test_empty_response(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"task_ids": []}
        mock_resp.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_resp

        result = bc.get_stopping_tasks(engine_id="eng-001", cluster_id="gpu-prod")

        assert result == []

    def test_network_error(self, mock_httpx_client):
        bc, mock_client = mock_httpx_client
        mock_client.get.side_effect = httpx.ConnectError("timeout")

        result = bc.get_stopping_tasks(engine_id="eng-001", cluster_id="gpu-prod")

        assert result == []
