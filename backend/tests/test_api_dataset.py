"""Dataset endpoint wiring tests."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


@patch("api.api_dataset.list_datasets_svc")
def test_list_datasets(mock_list):
    mock_list.return_value = {
        "data": [],
        "pagination": {
            "total": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
        },
    }
    response = client.get("/api/datasets?dataset_type=llm")
    assert response.status_code == 200
    assert response.json()["data"] == []


@patch("api.api_dataset.create_dataset_svc")
def test_create_dataset_accepts_multi_type_json(mock_create):
    mock_create.return_value = {"id": "dataset-1", "dataset_types": ["llm", "mcp"]}
    response = client.post(
        "/api/datasets",
        data={
            "name": "shared prompts",
            "is_public": "true",
            "dataset_types": '["llm", "mcp"]',
            "tags": '["文本", "shareGPT"]',
        },
        files={"file": ("data.jsonl", b'{"prompt":"hello"}\n', "application/jsonl")},
    )
    assert response.status_code == 200
    assert response.json()["dataset_types"] == ["llm", "mcp"]
    assert mock_create.call_args.args[5] == ["文本", "shareGPT"]


@patch("api.api_dataset.update_dataset_svc")
def test_update_dataset(mock_update):
    mock_update.return_value = {"id": "dataset-1", "is_public": True}
    response = client.put("/api/datasets/dataset-1", json={"is_public": True})
    assert response.status_code == 200
    assert response.json()["is_public"] is True
