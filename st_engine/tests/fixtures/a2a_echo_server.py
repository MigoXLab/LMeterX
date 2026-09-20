"""Lightweight A2A 1.0 echo server for E2E testing.

Implements the three A2A protocol bindings used by LMeterX:

* JSON-RPC 2.0 at ``/a2a/jsonrpc``
* HTTP+JSON (REST) at ``/a2a/message:send``, ``/a2a/message:stream``,
  ``/a2a/tasks/{id}``
* gRPC ``a2a.A2AService/{SendMessage,SendStreamingMessage,GetTask}``
  with JSON payloads (matching the Locust engine's generic unary client)

Each binding supports SendMessage (sync & async_poll),
SendStreamingMessage (SSE for HTTP, unary JSON for gRPC), and GetTask.

Start with ``start_server(port)`` which returns the server and a shutdown
callable.  The servers bind to 0.0.0.0 so Docker containers on the bridge
network can reach them via the host gateway IP.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent import futures
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Optional
from urllib.parse import unquote

try:
    import grpc
except ImportError:  # pragma: no cover - optional in lightweight test envs
    grpc = None  # type: ignore[assignment]

_tasks: dict[str, dict[str, Any]] = {}
_task_lock = threading.Lock()

_WORKING_DELAY_S = 0.15
_A2A_GRPC_METHODS = {
    "SendMessage",
    "SendStreamingMessage",
    "GetTask",
}


def _agent_card(host: str, port: int, grpc_port: int = 0) -> dict[str, Any]:
    base = f"http://{host}:{port}"
    interfaces: list[dict[str, Any]] = [
        {
            "protocolVersion": "1.0",
            "protocolBinding": "JSONRPC",
            "url": f"{base}/a2a/jsonrpc",
        },
        {
            "protocolVersion": "1.0",
            "protocolBinding": "HTTP+JSON",
            "url": f"{base}/a2a",
        },
    ]
    if grpc_port:
        interfaces.append(
            {
                "protocolVersion": "1.0",
                "protocolBinding": "GRPC",
                "url": f"{host}:{grpc_port}",
            }
        )
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
        "supportedInterfaces": interfaces,
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


def _process_send_message(params: dict[str, Any], mcp_calls: int) -> dict[str, Any]:
    message = params.get("message") or {}
    config = params.get("configuration") or {}
    return_immediately = bool(config.get("returnImmediately", False))
    if return_immediately:
        task = _new_task(message, state="submitted", mcp_calls=mcp_calls)
        with _task_lock:
            _tasks[task["id"]] = task
    else:
        task = _new_task(message, state="completed", mcp_calls=mcp_calls)
    return _task_result(task)


def _process_get_task(task_id: str) -> Optional[dict[str, Any]]:
    with _task_lock:
        task = _tasks.get(task_id)
        if not task:
            return None
        elapsed = time.monotonic() - task["_created"]
        if elapsed < _WORKING_DELAY_S:
            task["status"]["state"] = "submitted"
        elif elapsed < _WORKING_DELAY_S * 2:
            task["status"]["state"] = "working"
        else:
            task["status"]["state"] = "completed"
        return _task_result(task)


class A2AHandler(BaseHTTPRequestHandler):
    server: "A2AEchoServer"

    def log_message(self, format: str, *args: Any) -> None:
        """Silence default HTTP access logs during tests."""

    def _path_only(self) -> str:
        return unquote(self.path.split("?", 1)[0])

    def do_GET(self) -> None:
        """Serve the A2A Agent Card at ``/.well-known/agent-card.json``."""
        path = self._path_only()
        if path == "/.well-known/agent-card.json":
            card = _agent_card(
                self.server.advertised_host,
                self.server.server_port,
                self.server.grpc_port,
            )
            body = json.dumps(card).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path.startswith("/a2a/tasks/"):
            self._handle_rest_get_task(path)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        """Dispatch JSON-RPC and HTTP+JSON (REST) A2A methods."""
        path = self._path_only()
        if path == "/a2a/jsonrpc":
            self._handle_jsonrpc()
            return
        if path == "/a2a/message:send":
            self._handle_rest_send(stream=False)
            return
        if path == "/a2a/message:stream":
            self._handle_rest_send(stream=True)
            return
        if path.startswith("/a2a/tasks/"):
            self._handle_rest_get_task(path)
            return
        self.send_error(404)

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        return json.loads(raw)

    def _handle_jsonrpc(self) -> None:
        try:
            request = self._read_json_body()
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, _jsonrpc_error(None, -32700, "Parse error"))
            return
        if not isinstance(request, dict):
            self._send_json(400, _jsonrpc_error(None, -32600, "Invalid request"))
            return

        method = request.get("method", "")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        req_id = request.get("id")

        if method == "SendMessage":
            result = _process_send_message(params, self.server.mcp_calls)
            self._send_json(200, _jsonrpc_response(req_id, result))
        elif method == "SendStreamingMessage":
            self._write_sse_events(
                params, jsonrpc=True, req_id=req_id, mcp_calls=self.server.mcp_calls
            )
        elif method == "GetTask":
            task_id = str(params.get("id") or "")
            task_result = _process_get_task(task_id)
            if task_result is None:
                self._send_json(200, _jsonrpc_error(req_id, -32001, "Task not found"))
                return
            self._send_json(200, _jsonrpc_response(req_id, task_result))
        else:
            self._send_json(
                200, _jsonrpc_error(req_id, -32601, f"Unknown method: {method}")
            )

    def _handle_rest_send(self, *, stream: bool) -> None:
        try:
            params = self._read_json_body()
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, {"error": {"code": -32700, "message": "Parse error"}})
            return
        if not isinstance(params, dict):
            params = {}
        if stream:
            self._write_sse_events(
                params, jsonrpc=False, req_id=None, mcp_calls=self.server.mcp_calls
            )
            return
        result = _process_send_message(params, self.server.mcp_calls)
        self._send_json(200, result)

    def _handle_rest_get_task(self, path: str) -> None:
        task_id = path[len("/a2a/tasks/") :].strip("/")
        # Drain the body so keep-alive clients (Locust) can reuse the socket.
        try:
            self._read_json_body()
        except (json.JSONDecodeError, ValueError):
            pass
        result = _process_get_task(task_id)
        if result is None:
            self._send_json(
                404, {"error": {"code": -32001, "message": "Task not found"}}
            )
            return
        self._send_json(200, result)

    def _write_sse_events(
        self,
        params: dict[str, Any],
        *,
        jsonrpc: bool,
        req_id: Any,
        mcp_calls: int,
    ) -> None:
        message = params.get("message") or {}
        task = _new_task(message, state="submitted", mcp_calls=mcp_calls)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        states = ["submitted", "working", "completed"]
        for state in states:
            task["status"]["state"] = state
            payload: dict[str, Any] = _task_result(task)
            if jsonrpc:
                payload = _jsonrpc_response(req_id, payload)
            event_data = json.dumps(payload)
            self.wfile.write(f"event: message\ndata: {event_data}\n\n".encode())
            self.wfile.flush()
            if state != "completed":
                time.sleep(_WORKING_DELAY_S)
        self.wfile.flush()

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


_GenericHandlerBase = grpc.GenericRpcHandler if grpc is not None else object


class _A2AGenericHandler(_GenericHandlerBase):  # type: ignore[misc, valid-type]
    """JSON-payload generic handler matching the Locust/backend gRPC client."""

    def __init__(self, mcp_calls: int) -> None:
        self.mcp_calls = mcp_calls

    def service(self, handler_call_details: Any) -> Any:
        if grpc is None:
            return None
        method = (getattr(handler_call_details, "method", "") or "").rsplit("/", 1)[-1]
        if method not in _A2A_GRPC_METHODS:
            return None
        impl = {
            "SendMessage": self._send_message,
            "SendStreamingMessage": self._send_streaming,
            "GetTask": self._get_task,
        }[method]
        return grpc.unary_unary_rpc_method_handler(
            impl,
            request_deserializer=lambda body: body,
            response_serializer=lambda body: body,
        )

    def _parse_params(self, request: bytes) -> dict[str, Any]:
        if not request:
            return {}
        payload = json.loads(request)
        return payload if isinstance(payload, dict) else {}

    def _send_message(self, request: bytes, context: Any) -> bytes:
        result = _process_send_message(self._parse_params(request), self.mcp_calls)
        return json.dumps(result).encode()

    def _send_streaming(self, request: bytes, context: Any) -> bytes:
        # The Locust engine uses unary_unary even for SendStreamingMessage.
        params = self._parse_params(request)
        message = params.get("message") or {}
        task = _new_task(message, state="completed", mcp_calls=self.mcp_calls)
        return json.dumps(_task_result(task)).encode()

    def _get_task(self, request: bytes, context: Any) -> bytes:
        params = self._parse_params(request)
        task_id = str(params.get("id") or "")
        result = _process_get_task(task_id)
        if result is None:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Task not found")
            return b"{}"
        return json.dumps(result).encode()


class A2AEchoServer(HTTPServer):
    advertised_host: str = "127.0.0.1"
    mcp_calls: int = 0
    grpc_port: int = 0
    grpc_server: Any = None


def start_server(
    port: int = 0,
    host: str = "0.0.0.0",
    advertised_host: str = "127.0.0.1",
    mcp_calls: int = 0,
) -> tuple["A2AEchoServer", Callable[[], None]]:
    """Start the HTTP and gRPC echo servers in daemon threads.

    Returns ``(server, shutdown_fn)``.  The bound HTTP port is
    ``server.server_port``; the bound gRPC port is ``server.grpc_port``.

    *mcp_calls* — when > 0, every task response includes a
    ``metadata.mcp_calls`` counter so the cascade-observation path can
    be exercised.
    """
    server = A2AEchoServer((host, port), A2AHandler)
    server.advertised_host = advertised_host
    server.mcp_calls = mcp_calls

    grpc_server = None
    grpc_port = 0
    if grpc is not None:
        grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        grpc_server.add_generic_rpc_handlers(
            (_A2AGenericHandler(mcp_calls),)  # type: ignore[arg-type]
        )
        grpc_port = grpc_server.add_insecure_port(f"{host}:0")
        grpc_server.start()
    server.grpc_port = int(grpc_port)
    server.grpc_server = grpc_server

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def shutdown() -> None:
        server.shutdown()
        if grpc_server is not None:
            grpc_server.stop(0)
        _tasks.clear()

    return server, shutdown
