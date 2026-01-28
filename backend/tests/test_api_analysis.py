"""
Analysis API tests.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from model.analysis import AnalysisResponse, GetAnalysisResponse

client = TestClient(app)


class TestAnalysisAPI:
    """Analysis API tests."""

    @patch("api.api_analysis.analyze_tasks_svc")
    def test_analyze_tasks(self, mock_analyze):
        mock_analyze.return_value = AnalysisResponse(
            task_ids=["task_1"],
            analysis_report="report",
            status="completed",
            created_at="2025-01-01T00:00:00Z",
        )
        response = client.post(
            "/api/analyze", json={"task_ids": ["task_1"], "language": "en"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_analyze_tasks_validation_error(self):
        response = client.post("/api/analyze", json={"language": "en"})
        assert response.status_code == 422

    @patch("api.api_analysis.get_analysis_svc")
    def test_get_analysis(self, mock_get):
        mock_get.return_value = GetAnalysisResponse(
            data=AnalysisResponse(
                task_ids=["task_2"],
                analysis_report="report",
                status="completed",
                created_at="2025-01-01T00:00:00Z",
            ),
            status="success",
            error=None,
        )
        response = client.get("/api/analyze/task_2")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
