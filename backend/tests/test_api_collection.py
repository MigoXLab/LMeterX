"""
Collection API tests.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from model.collection import (
    CollectionCreateRequest,
    CollectionTaskAddRequest,
    CollectionUpdateRequest,
)

client = TestClient(app)


class TestCollectionAPI:
    """Collection API tests."""

    @patch("api.api_collection.create_collection_svc")
    def test_create_collection(self, mock_create):
        mock_create.return_value = {
            "id": "col_123",
            "name": "My Collection",
            "description": "Test",
            "rich_content": "",
            "created_by": "tester",
            "is_public": True,
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
            "task_count": 0,
        }

        payload = {"name": "My Collection", "description": "Test", "is_public": True}
        response = client.post("/api/collections", json=payload)
        assert response.status_code == 200
        assert response.json()["id"] == "col_123"

    @patch("api.api_collection.list_collections_svc")
    def test_list_collections(self, mock_list):
        mock_list.return_value = {
            "data": [{"id": "col_123", "name": "My Collection"}],
            "pagination": {"total": 1, "page": 1, "page_size": 10, "total_pages": 1},
        }
        response = client.get("/api/collections?page=1&page_size=10")
        assert response.status_code == 200
        assert response.json()["data"][0]["id"] == "col_123"

    @patch("api.api_collection.get_collection_svc")
    def test_get_collection(self, mock_get):
        mock_get.return_value = {"id": "col_123", "name": "My Collection"}
        response = client.get("/api/collections/col_123")
        assert response.status_code == 200
        assert response.json()["id"] == "col_123"

    @patch("api.api_collection.update_collection_svc")
    def test_update_collection(self, mock_update):
        mock_update.return_value = {"id": "col_123", "name": "Updated Name"}
        payload = {"name": "Updated Name"}
        response = client.put("/api/collections/col_123", json=payload)
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @patch("api.api_collection.delete_collection_svc")
    def test_delete_collection(self, mock_delete):
        mock_delete.return_value = {"message": "Collection deleted successfully"}
        response = client.delete("/api/collections/col_123")
        assert response.status_code == 200
        assert response.json()["message"] == "Collection deleted successfully"

    @patch("api.api_collection.add_task_to_collection_svc")
    def test_add_task_to_collection(self, mock_add_task):
        mock_add_task.return_value = {
            "message": "Task added to collection successfully"
        }
        payload = {"task_id": "task_1", "task_type": "http"}
        response = client.post("/api/collections/col_123/tasks", json=payload)
        assert response.status_code == 200
        assert response.json()["message"] == "Task added to collection successfully"

    @patch("api.api_collection.remove_task_from_collection_svc")
    def test_remove_task_from_collection(self, mock_remove_task):
        mock_remove_task.return_value = {
            "message": "Task removed from collection successfully"
        }
        response = client.delete("/api/collections/col_123/tasks/task_1")
        assert response.status_code == 200
        assert response.json()["message"] == "Task removed from collection successfully"

    @patch("api.api_collection.list_collection_tasks_svc")
    def test_list_collection_tasks(self, mock_list_tasks):
        mock_list_tasks.return_value = {
            "data": [{"id": "task_1", "name": "Test Task", "task_type": "http"}]
        }
        response = client.get("/api/collections/col_123/tasks")
        assert response.status_code == 200
        assert response.json()["data"][0]["id"] == "task_1"
