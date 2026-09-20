"""Real-service E2E coverage for MCP and A2A protocol jobs.

This module deliberately has no HTTP, A2A, or MCP mocks.  It submits work via
the public LMeterX Backend API and waits for a real Engine to execute it.  It is
opt-in because it creates short-lived load-test jobs and calls external agents.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Iterator

import httpx
import pytest

pytestmark = pytest.mark.e2e

_ACTIVE_STATUSES = {"created", "queuing", "running", "stopping"}
_TERMINAL_STATUSES = {"completed", "failed", "failed_requests", "stopped"}


def _enabled() -> bool:
    return os.getenv("LMETERX_RUN_AGENT_E2E", "").lower() in {"1", "true", "yes"}


def _json_env(name: str, default: dict[str, str] | None = None) -> dict[str, str]:
    value = os.getenv(name)
    if not value:
        return dict(default or {})
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in parsed.items()
    ):
        raise pytest.UsageError(f"{name} must be a JSON object of string headers")
    return dict(parsed)


@pytest.fixture(scope="session")
def backend_client() -> Iterator[httpx.Client]:
    """Client for a deployed Backend with a registered Engine."""
    if not _enabled():
        pytest.skip("set LMETERX_RUN_AGENT_E2E=1 to run real protocol E2E tests")
    backend_url = os.getenv("LMETERX_E2E_BACKEND_URL", "").rstrip("/")
    if not backend_url:
        raise pytest.UsageError("LMETERX_E2E_BACKEND_URL is required for agent E2E")
    timeout = float(os.getenv("LMETERX_E2E_HTTP_TIMEOUT_SECONDS", "30"))
    with httpx.Client(
        base_url=backend_url,
        headers=_json_env("LMETERX_E2E_BACKEND_HEADERS_JSON"),
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        response = client.get("/health")
        response.raise_for_status()
        assert response.json().get("status") == "healthy"
        yield client


def _task_duration() -> int:
    return int(os.getenv("LMETERX_E2E_DURATION_SECONDS", "20"))


def _task_deadline() -> float:
    return float(os.getenv("LMETERX_E2E_TASK_TIMEOUT_SECONDS", "420"))


def _upload_jsonl(
    client: httpx.Client, filename: str, records: list[dict[str, Any]]
) -> str:
    """Upload a real JSONL dataset through the Backend public upload endpoint."""
    body = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    response = client.post(
        "/api/upload",
        params={"file_type": "dataset"},
        files={"files": (filename, body.encode("utf-8"), "application/x-jsonl")},
    )
    response.raise_for_status()
    payload = response.json()
    files = payload.get("files") or []
    assert payload.get("test_data")
    assert len(files) == 1
    assert files[0]["path"] == payload["test_data"]
    return str(payload["test_data"])


def _assert_ok(response: httpx.Response) -> dict[str, Any]:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:  # Preserve safe API diagnostics in CI.
        raise AssertionError(f"{exc}; response={response.text[:2000]}") from exc
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def _wait_for_result(client: httpx.Client, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + _task_deadline()
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = _assert_ok(client.get(f"/api/agent-tasks/{task_id}"))
        if str(latest.get("status", "")).lower() in _TERMINAL_STATUSES:
            return latest
        time.sleep(1)
    raise AssertionError(f"agent task {task_id} did not finish: {latest}")


def _cleanup_task(client: httpx.Client, task_id: str) -> None:
    """Only delete a job created by this test, after safely stopping it."""
    response = client.get(f"/api/agent-tasks/{task_id}")
    if response.status_code == 404:
        return
    response.raise_for_status()
    status = str(response.json().get("status", "")).lower()
    if status in _ACTIVE_STATUSES:
        stopped = client.post(f"/api/agent-tasks/{task_id}/stop")
        stopped.raise_for_status()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = client.get(f"/api/agent-tasks/{task_id}")
            current.raise_for_status()
            if str(current.json().get("status", "")).lower() not in _ACTIVE_STATUSES:
                break
            time.sleep(1)
    deleted = client.delete(f"/api/agent-tasks/{task_id}")
    if deleted.status_code not in {200, 404}:
        _assert_ok(deleted)


def _run_task(
    client: httpx.Client, payload: dict[str, Any]
) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Create a task, verify its saved upload reference, and always clean it up."""
    created = _assert_ok(client.post("/api/agent-tasks", json=payload))
    task_id = str(created["task_id"])
    try:
        persisted = _assert_ok(client.get(f"/api/agent-tasks/{task_id}"))
        assert persisted["dataset_file"] == payload["dataset_file"]
        final = _wait_for_result(client, task_id)
        assert final["status"] == "completed", final.get("error_message")
        results = _assert_ok(client.get(f"/api/agent-tasks/{task_id}/results"))
        metrics = results.get("protocol_metrics")
        assert isinstance(metrics, dict) and metrics, results
        yield final, metrics
    finally:
        _cleanup_task(client, task_id)


def _assert_weighted_dataset_use(
    metrics: dict[str, Any], expected_weights: dict[str, int], row_ids: set[str]
) -> None:
    assert metrics["scenario_weights"] == expected_weights
    selections = metrics["scenario_selections"]
    assert set(selections) == set(expected_weights)
    total = sum(int(count) for count in selections.values())
    assert total >= len(expected_weights) * 2, selections
    total_weight = sum(expected_weights.values())
    for scenario_id, weight in expected_weights.items():
        # Smooth weighted round-robin is never farther than one request from
        # the ideal allocation for a single virtual user.
        assert abs(selections[scenario_id] - total * weight / total_weight) <= 1
    used_rows = metrics["dataset_row_selections"]
    assert row_ids.issubset(used_rows), used_rows
    assert all(used_rows[row_id] > 0 for row_id in row_ids)


def _mcp_payload(dataset_file: str) -> dict[str, Any]:
    return {
        "name": f"e2e-deepwiki-{uuid.uuid4().hex[:8]}",
        "protocol": "mcp",
        # DeepWiki currently advertises this real Streamable HTTP version.
        "protocol_version": "2025-11-25",
        "target_url": "https://mcp.deepwiki.com/mcp",
        "duration": _task_duration(),
        "concurrent_users": 1,
        "spawn_rate": 1,
        "request_timeout": 90,
        "dataset_file": dataset_file,
        "mcp_calls": [
            {
                "id": "structure",
                "name": "Repository structure",
                "tool_name": "read_wiki_structure",
                "arguments": {"repoName": "modelcontextprotocol/python-sdk"},
                "weight": 3,
            },
            {
                "id": "contents",
                "name": "Repository contents",
                "tool_name": "read_wiki_contents",
                "arguments": {"repoName": "modelcontextprotocol/python-sdk"},
                "weight": 1,
            },
        ],
    }


def test_mcp_real_tools_multi_scenario_weight_and_uploaded_dataset(
    backend_client: httpx.Client,
) -> None:
    """DeepWiki tools/list/tools/call execute through Backend → Engine → Locust."""
    rows = [
        {
            "id": "deepwiki-structure",
            "scenario_id": "structure",
            "arguments": {"repoName": "modelcontextprotocol/python-sdk"},
        },
        {
            "id": "deepwiki-contents",
            "scenario_id": "contents",
            "arguments": {"repoName": "modelcontextprotocol/python-sdk"},
        },
    ]
    dataset_file = _upload_jsonl(backend_client, "deepwiki-e2e.jsonl", rows)
    payload = _mcp_payload(dataset_file)

    connection = _assert_ok(
        backend_client.post("/api/agent-tasks/test-connection", json=payload)
    )
    tool_names = {tool["name"] for tool in connection["tools"]}
    assert {"read_wiki_structure", "read_wiki_contents"}.issubset(tool_names)

    for _, metrics in _run_task(backend_client, payload):
        assert metrics["protocol"] == "mcp"
        assert metrics["failed_requests"] == 0
        assert metrics["tool_call_success_rate"] == 1.0
        _assert_weighted_dataset_use(
            metrics,
            {"structure": 3, "contents": 1},
            {"deepwiki-structure", "deepwiki-contents"},
        )


def _a2a_headers_and_card() -> tuple[dict[str, str], str, dict[str, Any]]:
    """Use a supplied Bearer token or exchange the EP demo's client secret."""
    headers = _json_env("LMETERX_E2E_A2A_HEADERS_JSON")
    base_url = os.getenv("LMETERX_E2E_A2A_BASE_URL", "").rstrip("/")
    secret = os.getenv("LMETERX_E2E_A2A_CLIENT_SECRET")
    if secret:
        if not base_url:
            raise pytest.UsageError(
                "LMETERX_E2E_A2A_BASE_URL is required with A2A client secret"
            )
        response = httpx.post(
            f"{base_url}/a2a/token",
            headers={"X-Client-Secret": secret, "Accept": "application/json"},
            json={"user_id": f"lmeterx-e2e-{uuid.uuid4()}"},
            timeout=30,
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
        assert isinstance(access_token, str) and access_token
        headers["Authorization"] = f"Bearer {access_token}"
    if not headers.get("Authorization"):
        raise pytest.UsageError(
            "provide LMETERX_E2E_A2A_HEADERS_JSON with Authorization or "
            "LMETERX_E2E_A2A_CLIENT_SECRET"
        )

    card_url = os.getenv("LMETERX_E2E_A2A_CARD_URL", "").strip()
    if not card_url:
        if not base_url:
            raise pytest.UsageError(
                "LMETERX_E2E_A2A_CARD_URL or LMETERX_E2E_A2A_BASE_URL is required"
            )
        card_url = (
            f"{base_url}/a2a/agents/electroplating-agent/" ".well-known/agent-card.json"
        )
    card_response = httpx.get(card_url, headers=headers, timeout=30)
    card_response.raise_for_status()
    card = card_response.json()
    assert isinstance(card, dict)
    return headers, card_url, card


_A2A_CARD_BINDINGS: dict[str, set[str]] = {
    "jsonrpc": {"JSONRPC", "HTTP+JSONRPC"},
    "http_json": {"HTTP+JSON"},
    "grpc": {"GRPC"},
}


def _a2a_payload(
    mode: str, dataset_file: str, binding: str = "jsonrpc"
) -> dict[str, Any]:
    headers, card_url, card = _a2a_headers_and_card()
    interfaces = card.get("supportedInterfaces") or []
    accepted = _A2A_CARD_BINDINGS[binding]
    interface = next(
        (
            item
            for item in interfaces
            if isinstance(item, dict)
            and item.get("protocolVersion") == "1.0"
            and str(item.get("protocolBinding", "")).upper() in accepted
        ),
        None,
    )
    if not interface:
        pytest.skip(f"EP Agent Card has no A2A 1.0 {binding} interface")
    assert interface is not None
    if mode == "stream":
        assert card.get("capabilities", {}).get("streaming") is True
    target_url = str(interface["url"])
    if binding == "grpc":
        target_url = target_url.replace("grpc://", "").replace("grpcs://", "")
        if target_url.startswith(("http://", "https://")):
            pytest.skip("GRPC interface url is an HTTP URL; cannot use as gRPC target")
    payload: dict[str, Any] = {
        "name": f"e2e-ep-agent-{binding}-{mode}-{uuid.uuid4().hex[:8]}",
        "protocol": "a2a",
        "protocol_version": "1.0",
        "target_url": target_url,
        "a2a_binding": binding,
        "a2a_tenant": interface.get("tenant"),
        "headers": [{"key": key, "value": value} for key, value in headers.items()],
        "a2a_mode": mode,
        "duration": _task_duration(),
        "concurrent_users": 1,
        "spawn_rate": 1,
        "request_timeout": 90,
        "task_timeout": 240,
        "poll_interval": 0.5,
        "dataset_file": dataset_file,
        "a2a_scenarios": [
            {
                "id": "capabilities",
                "name": "Capabilities query",
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "你支持哪些电镀能力？"}],
                },
                "weight": 3,
            },
            {
                "id": "knowledge",
                "name": "Knowledge query",
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "简要说明电镀液添加剂的作用。"}],
                },
                "weight": 1,
            },
        ],
    }
    if binding != "grpc":
        payload["agent_card_url"] = card_url
    return payload


@pytest.mark.parametrize("binding", ["jsonrpc", "http_json", "grpc"])
@pytest.mark.parametrize("mode", ["sync", "stream", "async_poll"])
def test_a2a_real_execution_modes_weight_and_uploaded_dataset(
    backend_client: httpx.Client, mode: str, binding: str
) -> None:
    """Exercise all three A2A bindings × SendMessage / stream / GetTask."""
    rows = [
        {
            "id": "ep-capabilities",
            "scenario_id": "capabilities",
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "请列出你能执行的电镀相关任务。"}],
            },
        },
        {
            "id": "ep-knowledge",
            "scenario_id": "knowledge",
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "什么是电镀液的整平剂？"}],
            },
        },
    ]
    dataset_file = _upload_jsonl(
        backend_client, f"ep-agent-{binding}-{mode}-e2e.jsonl", rows
    )
    payload = _a2a_payload(mode, dataset_file, binding=binding)

    connection = _assert_ok(
        backend_client.post("/api/agent-tasks/test-connection", json=payload)
    )
    assert connection["protocol"] == "a2a"
    if binding != "grpc":
        assert connection["agent_card"]["name"]

    for _, metrics in _run_task(backend_client, payload):
        assert metrics["protocol"] == "a2a"
        assert metrics["failed_requests"] == 0
        assert metrics["task_submission_success_rate"] == 1.0
        if mode == "stream":
            assert metrics["time_to_first_event_ms"]["count"] > 0
        if mode == "async_poll":
            assert metrics["terminal_tasks"] > 0
        _assert_weighted_dataset_use(
            metrics,
            {"capabilities": 3, "knowledge": 1},
            {"ep-capabilities", "ep-knowledge"},
        )
