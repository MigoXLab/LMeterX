"""Lightweight A2A 1.0 echo server for E2E testing.

Implements the minimal A2A JSON-RPC surface needed by the LMeterX
agent_locustfile: Agent Card, SendMessage (sync & async_poll),
SendStreamingMessage (SSE), and GetTask.

Start with ``start_server(port)`` which returns the server thread and a
shutdown callable.  The server binds to 0.0.0.0 so Docker containers on
the bridge network can reach it via the host gateway IP.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

_tasks: dict[str, dict[str, Any]] = {}
_task_lock = threading.Lock()

_WORKING_DELAY_S = 0.15


def _agent_card(host: str, port: int) -> dict[str, Any]:
    base = f"http://{host}:{port}"
    return {
        "name": "LMeterX E2E Echo Agent",
        "description": "Minimal A2A echo agent for load-test E2E verification",
        "version": "1.0.0",
        "protocolVersion": "1.0",
        "capabilities": {"streaming": True, "pushNotifications": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "echo",
                "name": "Echo",
                "description": "Echoes the user message back",
                "tags": ["test"],
            }
        ],
        "supportedInterfaces": [
            {
                "protocolVersion": "1.0",
                "protocolBinding": "JSONRPC",
                "url": f"{base}/a2a/jsonrpc",
            }
        ],
    }


def _extract_text(message: dict[str, Any]) -> str:
    parts = message.get("parts") or []
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
    return " ".join(texts) or "echo"


def _new_task(
    message: dict[str, Any],
    state: str = "submitted",
    mcp_calls: int = 0,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    text = _extract_text(message)
    task: dict[str, Any] = {
        "kind": "task",
        "id": task_id,
        "status": {"state": state},
        "history": [message],
        "artifacts": [
            {
                "artifactId": str(uuid.uuid4()),
                "parts": [{"text": f"echo: {text}"}],
            }
        ],
        "_created": time.monotonic(),
    }
    if mcp_calls > 0:
        task["metadata"] = {"mcp_calls": mcp_calls}
    return task


def _task_result(task: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in task.items() if not k.startswith("_")}
    return {"task": clean}


def _jsonrpc_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class A2AHandler(BaseHTTPRequestHandler):
    server: "A2AEchoServer"

    def log_message(self, format: str, *args: Any) -> None:
        """Silence default HTTP access logs during tests."""

    def do_GET(self) -> None:
        """Serve the A2A Agent Card at ``/.well-known/agent-card.json``."""
        if self.path == "/.well-known/agent-card.json":
            card = _agent_card(self.server.advertised_host, self.server.server_port)
            body = json.dumps(card).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        """Handle A2A JSON-RPC methods on ``/a2a/jsonrpc``."""
        if self.path != "/a2a/jsonrpc":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            request = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, _jsonrpc_error(None, -32700, "Parse error"))
            return

        method = request.get("method", "")
        params = request.get("params") or {}
        req_id = request.get("id")

        if method == "SendMessage":
            self._handle_send_message(req_id, params)
        elif method == "SendStreamingMessage":
            self._handle_send_streaming(req_id, params)
        elif method == "GetTask":
            self._handle_get_task(req_id, params)
        else:
            self._send_json(
                200, _jsonrpc_error(req_id, -32601, f"Unknown method: {method}")
            )

    def _handle_send_message(self, req_id: Any, params: dict[str, Any]) -> None:
        message = params.get("message", {})
        config = params.get("configuration") or {}
        return_immediately = config.get("returnImmediately", False)
        mcp = self.server.mcp_calls

        if return_immediately:
            task = _new_task(message, state="submitted", mcp_calls=mcp)
            with _task_lock:
                _tasks[task["id"]] = task
            self._send_json(200, _jsonrpc_response(req_id, _task_result(task)))
        else:
            task = _new_task(message, state="completed", mcp_calls=mcp)
            self._send_json(200, _jsonrpc_response(req_id, _task_result(task)))

    def _handle_send_streaming(self, req_id: Any, params: dict[str, Any]) -> None:
        message = params.get("message", {})
        mcp = self.server.mcp_calls
        task = _new_task(message, state="submitted", mcp_calls=mcp)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        states = ["submitted", "working", "completed"]
        for state in states:
            task["status"]["state"] = state
            event_data = json.dumps(_jsonrpc_response(req_id, _task_result(task)))
            self.wfile.write(f"event: message\ndata: {event_data}\n\n".encode())
            self.wfile.flush()
            if state != "completed":
                time.sleep(_WORKING_DELAY_S)
        self.wfile.flush()

    def _handle_get_task(self, req_id: Any, params: dict[str, Any]) -> None:
        task_id = params.get("id", "")
        with _task_lock:
            task = _tasks.get(task_id)

        if not task:
            self._send_json(200, _jsonrpc_error(req_id, -32001, "Task not found"))
            return

        elapsed = time.monotonic() - task["_created"]
        if elapsed < _WORKING_DELAY_S:
            task["status"]["state"] = "submitted"
        elif elapsed < _WORKING_DELAY_S * 2:
            task["status"]["state"] = "working"
        else:
            task["status"]["state"] = "completed"

        self._send_json(200, _jsonrpc_response(req_id, _task_result(task)))

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class A2AEchoServer(HTTPServer):
    advertised_host: str = "127.0.0.1"
    mcp_calls: int = 0


def start_server(
    port: int = 0,
    host: str = "0.0.0.0",
    advertised_host: str = "127.0.0.1",
    mcp_calls: int = 0,
) -> tuple["A2AEchoServer", Callable[[], None]]:
    """Start the echo server in a daemon thread.

    Returns ``(server, shutdown_fn)``.  The actual bound port is
    available as ``server.server_port``.

    *mcp_calls* — when > 0, every task response includes a
    ``metadata.mcp_calls`` counter so the cascade-observation path can
    be exercised.
    """
    server = A2AEchoServer((host, port), A2AHandler)
    server.advertised_host = advertised_host
    server.mcp_calls = mcp_calls
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def shutdown() -> None:
        server.shutdown()
        _tasks.clear()

    return server, shutdown
