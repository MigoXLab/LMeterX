"""
Skill API tests for /api/skills/analyze-url.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from model.skill import AnalyzeUrlResponse, DiscoveredApiItem
from service.skill_service import _CapturedRequest

client = TestClient(app)


class TestSkillAPIUnit:
    """Unit tests for router behavior."""

    @patch("api.api_skill.analyze_url_svc", new_callable=AsyncMock)
    def test_analyze_url_calls_service(self, mock_analyze):
        mock_analyze.return_value = AnalyzeUrlResponse(
            status="success",
            message="ok",
            target_url="https://example.com",
        )

        payload = {
            "target_url": "https://example.com",
            "wait_seconds": 3,
            "scroll": False,
        }
        response = client.post("/api/skills/analyze-url", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_analyze.assert_awaited_once()
        called_body = mock_analyze.await_args.args[1]
        assert called_body.target_url == "https://example.com"
        assert called_body.wait_seconds == 3
        assert called_body.scroll is False

    @patch("api.api_skill.analyze_url_svc", new_callable=AsyncMock)
    def test_analyze_url_validation_error(self, mock_analyze):
        response = client.post(
            "/api/skills/analyze-url",
            json={"target_url": "example.com"},
        )

        assert response.status_code == 422
        mock_analyze.assert_not_awaited()


class TestSkillAPIFunctional:
    """Functional tests for end-to-end endpoint + service flow (with stubs)."""

    @patch("service.skill_service._generate_configs_via_llm", new_callable=AsyncMock)
    @patch("service.skill_service._analyze_page", new_callable=AsyncMock)
    def test_analyze_url_success_with_default_configs(
        self,
        mock_analyze_page,
        mock_generate_configs_via_llm,
    ):
        mock_analyze_page.return_value = [
            _CapturedRequest(
                url="https://api.example.com/v1/orders",
                method="GET",
                resource_type="xhr",
                headers={"Authorization": "Bearer token", "X-Trace-Id": "abc"},
                status=200,
            ),
            # Should be filtered out as static resource.
            _CapturedRequest(
                url="https://example.com/static/app.js",
                method="GET",
                resource_type="fetch",
                headers={},
                status=200,
            ),
        ]
        mock_generate_configs_via_llm.return_value = None

        response = client.post(
            "/api/skills/analyze-url",
            json={
                "target_url": "https://example.com",
                "concurrent_users": 80,
                "duration": 120,
                "spawn_rate": 20,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["llm_used"] is False
        assert len(data["discovered_apis"]) == 1
        assert len(data["loadtest_configs"]) == 1
        assert data["loadtest_configs"][0]["concurrent_users"] == 80
        assert data["loadtest_configs"][0]["duration"] == 120
        assert data["loadtest_configs"][0]["spawn_rate"] == 20
        assert (
            data["discovered_apis"][0]["target_url"]
            == "https://api.example.com/v1/orders"
        )

    @patch("service.skill_service._generate_configs_via_llm", new_callable=AsyncMock)
    @patch("service.skill_service._analyze_page", new_callable=AsyncMock)
    def test_analyze_url_success_with_llm_configs(
        self,
        mock_analyze_page,
        mock_generate_configs_via_llm,
    ):
        url_login = "https://api.example.com/v1/login"
        url_orders = "https://api.example.com/v1/orders"
        mock_analyze_page.return_value = [
            _CapturedRequest(
                url=url_login,
                method="POST",
                resource_type="xhr",
                headers={"Content-Type": "application/json"},
                post_data='{"u":"a"}',
                status=200,
            ),
            _CapturedRequest(
                url=url_orders,
                method="GET",
                resource_type="fetch",
                headers={"Accept": "application/json"},
                status=200,
            ),
        ]
        mock_generate_configs_via_llm.return_value = [
            {
                "target_url": url_login,
                "concurrent_users": 20,
                "duration": 300,
                "spawn_rate": 20,
            }
        ]

        response = client.post(
            "/api/skills/analyze-url",
            json={
                "target_url": "https://example.com",
                "concurrent_users": 60,
                "duration": 180,
                "spawn_rate": 15,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["llm_used"] is True
        assert len(data["loadtest_configs"]) == 2

        cfg_by_url = {cfg["target_url"]: cfg for cfg in data["loadtest_configs"]}
        assert cfg_by_url[url_login]["concurrent_users"] == 20
        assert cfg_by_url[url_login]["spawn_rate"] == 20
        # No LLM output for url_orders, falls back to request defaults.
        assert cfg_by_url[url_orders]["concurrent_users"] == 60
        assert cfg_by_url[url_orders]["duration"] == 180
        assert cfg_by_url[url_orders]["spawn_rate"] == 15

    @patch("service.skill_service._analyze_page", new_callable=AsyncMock)
    def test_analyze_url_playwright_missing(self, mock_analyze_page):
        mock_analyze_page.side_effect = RuntimeError("Playwright is required")

        response = client.post(
            "/api/skills/analyze-url",
            json={"target_url": "https://example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Playwright is required" in data["message"]

    @pytest.mark.skip(reason="JS static scan is disabled in skill_service")
    @patch("service.skill_service._generate_configs_via_llm", new_callable=AsyncMock)
    @patch(
        "service.skill_service._discover_apis_via_js_static_scan",
        new_callable=AsyncMock,
    )
    @patch("service.skill_service._analyze_page", new_callable=AsyncMock)
    def test_analyze_url_success_with_js_static_scan_merge(
        self,
        mock_analyze_page,
        mock_discover_js,
        mock_generate_configs_via_llm,
    ):
        mock_analyze_page.return_value = []
        mock_discover_js.return_value = [
            DiscoveredApiItem(
                name="GET /orders/list",
                target_url="https://api.example.com/v1/orders/list",
                method="GET",
                headers=[],
                request_body=None,
                http_status=None,
                source="js_static_scan",
                confidence="medium",
            )
        ]
        mock_generate_configs_via_llm.return_value = None

        response = client.post(
            "/api/skills/analyze-url",
            json={
                "target_url": "https://example.com",
                "concurrent_users": 30,
                "duration": 90,
                "spawn_rate": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["discovered_apis"]) == 1
        assert data["discovered_apis"][0]["source"] == "js_static_scan"
        assert data["discovered_apis"][0]["confidence"] == "medium"
        assert len(data["loadtest_configs"]) == 1
        assert data["loadtest_configs"][0]["target_url"] == (
            "https://api.example.com/v1/orders/list"
        )
