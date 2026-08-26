"""
Cluster API endpoint tests.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


class TestClusterListAPI:
    @patch("api.api_cluster.cluster_service.list_clusters", new_callable=AsyncMock)
    def test_list_clusters_empty(self, mock_list):
        mock_list.return_value = []

        response = client.get("/api/clusters")

        assert response.status_code == 200
        assert response.json()["clusters"] == []

    @patch("api.api_cluster.cluster_service.list_clusters", new_callable=AsyncMock)
    def test_list_clusters_with_data(self, mock_list):
        mock_list.return_value = [
            {
                "id": "gpu-prod",
                "name": "GPU Production",
                "status": "active",
                "online_engines": 3,
                "available_slots": 2,
                "running_tasks": 1,
                "desired_replicas": 3,
                "current_replicas": 3,
                "ready_replicas": 3,
                "min_replicas": 1,
                "max_replicas": 10,
            }
        ]

        response = client.get("/api/clusters")

        assert response.status_code == 200
        data = response.json()
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["id"] == "gpu-prod"
        assert data["clusters"][0]["online_engines"] == 3


class TestClusterCreateAPI:
    @patch("api.api_cluster.cluster_service.get_cluster", new_callable=AsyncMock)
    @patch("api.api_cluster.cluster_service.create_cluster", new_callable=AsyncMock)
    def test_create_cluster_success(self, mock_create, mock_get):
        mock_get.return_value = None
        mock_create.return_value = {
            "id": "new-cluster",
            "name": "New Cluster",
            "status": "active",
        }

        response = client.post(
            "/api/clusters",
            json={
                "id": "new-cluster",
                "name": "New Cluster",
                "min_replicas": 1,
                "max_replicas": 10,
            },
        )

        assert response.status_code == 200
        assert response.json()["id"] == "new-cluster"

    @patch("api.api_cluster.cluster_service.get_cluster", new_callable=AsyncMock)
    def test_create_cluster_duplicate(self, mock_get):
        mock_get.return_value = {"id": "existing", "name": "Existing"}

        response = client.post(
            "/api/clusters",
            json={
                "id": "existing",
                "name": "Existing",
            },
        )

        assert response.status_code == 400


class TestClusterDetailAPI:
    @patch("api.api_cluster.cluster_service.get_cluster", new_callable=AsyncMock)
    def test_get_cluster_found(self, mock_get):
        mock_get.return_value = {
            "id": "gpu-prod",
            "name": "GPU Production",
            "status": "active",
            "desired_replicas": 3,
            "min_replicas": 1,
            "max_replicas": 10,
            "current_replicas": 3,
            "ready_replicas": 3,
        }

        response = client.get("/api/clusters/gpu-prod")

        assert response.status_code == 200
        assert response.json()["id"] == "gpu-prod"

    @patch("api.api_cluster.cluster_service.get_cluster", new_callable=AsyncMock)
    def test_get_cluster_not_found(self, mock_get):
        mock_get.return_value = None

        response = client.get("/api/clusters/nonexistent")

        assert response.status_code == 404


class TestClusterDesiredStateAPI:
    @patch("api.api_cluster.cluster_service.get_desired_state", new_callable=AsyncMock)
    def test_get_desired_state(self, mock_state):
        mock_state.return_value = {
            "desired_replicas": 5,
            "min_replicas": 1,
            "max_replicas": 10,
        }

        response = client.get("/api/clusters/gpu-prod/desired-state")

        assert response.status_code == 200
        data = response.json()
        assert data["desired_replicas"] == 5
        assert data["min_replicas"] == 1

    @patch("api.api_cluster.cluster_service.get_desired_state", new_callable=AsyncMock)
    def test_get_desired_state_not_found(self, mock_state):
        mock_state.return_value = None

        response = client.get("/api/clusters/nonexistent/desired-state")

        assert response.status_code == 404


class TestClusterActualStateAPI:
    @patch(
        "api.api_cluster.cluster_service.update_actual_state", new_callable=AsyncMock
    )
    def test_update_actual_state(self, mock_update):
        mock_update.return_value = True

        response = client.post(
            "/api/clusters/gpu-prod/actual-state",
            json={
                "current_replicas": 5,
                "ready_replicas": 4,
                "available_replicas": 4,
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @patch(
        "api.api_cluster.cluster_service.update_actual_state", new_callable=AsyncMock
    )
    def test_update_actual_state_not_found(self, mock_update):
        mock_update.return_value = False

        response = client.post(
            "/api/clusters/nonexistent/actual-state",
            json={
                "current_replicas": 1,
                "ready_replicas": 1,
                "available_replicas": 1,
            },
        )

        assert response.status_code == 404


class TestClusterScaleAPI:
    @patch("api.api_cluster.cluster_service.scale_cluster", new_callable=AsyncMock)
    def test_scale_success(self, mock_scale):
        mock_scale.return_value = {
            "cluster_id": "gpu-prod",
            "desired_replicas": 5,
            "min_replicas": 1,
            "max_replicas": 10,
        }

        response = client.put(
            "/api/clusters/gpu-prod/scale",
            json={"desired_replicas": 5},
        )

        assert response.status_code == 200
        assert response.json()["desired_replicas"] == 5

    @patch("api.api_cluster.cluster_service.scale_cluster", new_callable=AsyncMock)
    def test_scale_not_found(self, mock_scale):
        mock_scale.return_value = None

        response = client.put(
            "/api/clusters/nonexistent/scale",
            json={"desired_replicas": 5},
        )

        assert response.status_code == 404

    def test_scale_invalid_value(self):
        response = client.put(
            "/api/clusters/gpu-prod/scale",
            json={"desired_replicas": 200},
        )
        assert response.status_code == 422
