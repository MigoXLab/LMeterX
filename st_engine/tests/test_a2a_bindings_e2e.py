"""Local protocol E2E for the three A2A bindings against the echo fixture.

These cases do not require a deployed Backend/Engine; they send the same
payloads the Locust workload and connection probe use, so they run in CI.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Iterator

import httpx
import pytest

try:
    import grpc
except ImportError:  # pragma: no cover
    grpc = None  # type: ignore[assignment]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fixtures"))
from a2a_echo_server import start_server  # noqa: E402

from engine.agent_protocol import (
    a2a_message_request,
    a2a_task_id,
    a2a_task_state,
    is_a2a_send_response,
    jsonrpc_request,
    parse_json_or_sse,
)

_POLL_DEADLINE_S = 2.0
_POLL_INTERVAL_S = 0.05


@pytest.fixture(scope="module")
def echo_server() -> Iterator[Any]:
    server, shutdown = start_server(port=0, advertised_host="127.0.0.1")
    yield server
    shutdown()


@pytest.fixture(scope="module")
def echo_urls(echo_server: Any) -> dict[str, str]:
    port = echo_server.server_port
    return {
        "jsonrpc": f"http://127.0.0.1:{port}/a2a/jsonrpc",
        "http_json": f"http://127.0.0.1:{port}/a2a",
        "grpc": f"127.0.0.1:{echo_server.grpc_port}",
        "card": f"http://127.0.0.1:{port}/.well-known/agent-card.json",
    }


def _message(text: str) -> dict[str, Any]:
    return {"role": "ROLE_USER", "parts": [{"text": text}]}


def _params(text: str, *, return_immediately: bool) -> dict[str, Any]:
    return a2a_message_request(_message(text), return_immediately=return_immediately)


def _grpc_call(target: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    if grpc is None:
        pytest.skip("grpcio is not installed")
    if target.endswith(":0"):
        pytest.skip("gRPC echo server did not start")
    channel = grpc.insecure_channel(target)
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
        raw = channel.unary_unary(
            f"/a2a.A2AService/{method}",
            request_serializer=lambda body: body,
            response_deserializer=lambda body: body,
        )(json.dumps(params).encode(), timeout=5)
        payload = json.loads(raw)
        assert isinstance(payload, dict)
        return payload
    finally:
        channel.close()


def _poll_until_completed(fetch: Any) -> dict[str, Any]:
    deadline = time.monotonic() + _POLL_DEADLINE_S
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = fetch()
        if a2a_task_state(latest) == "completed":
            return latest
        time.sleep(_POLL_INTERVAL_S)
    raise AssertionError(f"task did not complete: {latest}")


def test_agent_card_advertises_http_bindings(echo_urls: dict[str, str]) -> None:
    card = httpx.get(echo_urls["card"], timeout=5).json()
    bindings = {
        str(item.get("protocolBinding"))
        for item in card["supportedInterfaces"]
        if isinstance(item, dict)
    }
    assert {"JSONRPC", "HTTP+JSON"}.issubset(bindings)
    if echo_urls["grpc"].endswith(":0"):
        assert "GRPC" not in bindings
    else:
        assert "GRPC" in bindings
    assert card["capabilities"]["streaming"] is True


@pytest.mark.parametrize("mode", ["sync", "stream", "async_poll"])
def test_jsonrpc_send_and_get_task(echo_urls: dict[str, str], mode: str) -> None:
    url = echo_urls["jsonrpc"]
    method = "SendStreamingMessage" if mode == "stream" else "SendMessage"
    params = _params(f"jsonrpc {mode}", return_immediately=mode == "async_poll")
    response = httpx.post(
        url,
        json=jsonrpc_request(method, params, request_id=1),
        timeout=5,
    )
    response.raise_for_status()
    if mode == "stream":
        messages = parse_json_or_sse(
            response.headers.get("content-type", ""), response.text
        )
        assert is_a2a_send_response(messages)
        assert a2a_task_state(messages[-1]) == "completed"
        return
    payload = response.json()
    assert is_a2a_send_response([payload])
    if mode == "sync":
        assert a2a_task_state(payload) == "completed"
        return
    task_id = a2a_task_id(payload)
    assert task_id
    completed = _poll_until_completed(
        lambda: httpx.post(
            url,
            json=jsonrpc_request("GetTask", {"id": task_id}, request_id=2),
            timeout=5,
        ).json()
    )
    assert a2a_task_state(completed) == "completed"


@pytest.mark.parametrize("mode", ["sync", "stream", "async_poll"])
def test_http_json_send_and_get_task(echo_urls: dict[str, str], mode: str) -> None:
    base = echo_urls["http_json"]
    params = _params(f"rest {mode}", return_immediately=mode == "async_poll")
    path = "/message:stream" if mode == "stream" else "/message:send"
    response = httpx.post(base + path, json=params, timeout=5)
    response.raise_for_status()
    if mode == "stream":
        messages = parse_json_or_sse(
            response.headers.get("content-type", ""), response.text
        )
        assert is_a2a_send_response(messages)
        assert a2a_task_state(messages[-1]) == "completed"
        return
    payload = response.json()
    assert is_a2a_send_response([payload])
    if mode == "sync":
        assert a2a_task_state(payload) == "completed"
        return
    task_id = a2a_task_id(payload)
    assert task_id
    completed = _poll_until_completed(
        lambda: httpx.post(f"{base}/tasks/{task_id}", json={}, timeout=5).json()
    )
    assert a2a_task_state(completed) == "completed"


@pytest.mark.parametrize("mode", ["sync", "stream", "async_poll"])
def test_grpc_send_and_get_task(echo_urls: dict[str, str], mode: str) -> None:
    target = echo_urls["grpc"]
    method = "SendStreamingMessage" if mode == "stream" else "SendMessage"
    params = _params(f"grpc {mode}", return_immediately=mode == "async_poll")
    payload = _grpc_call(target, method, params)
    assert is_a2a_send_response([payload])
    if mode in {"sync", "stream"}:
        assert a2a_task_state(payload) == "completed"
        return
    task_id = a2a_task_id(payload)
    assert task_id
    completed = _poll_until_completed(
        lambda: _grpc_call(target, "GetTask", {"id": task_id})
    )
    assert a2a_task_state(completed) == "completed"
