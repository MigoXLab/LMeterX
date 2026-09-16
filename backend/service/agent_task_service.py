"""Business services for MCP and A2A protocol load tests."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx
from fastapi import Request
from sqlalchemy import delete, func, select

from model.agent_task import (
    A2ADatasetRow,
    AgentTask,
    AgentTaskCreateReq,
    AgentTaskResult,
    MCPDatasetRow,
)
from service.task_dispatch_service import add_dispatch_entry, cancel_dispatch_entry
from utils.auth import get_current_user, is_admin_user
from utils.be_config import UPLOAD_FOLDER
from utils.converters import safe_isoformat
from utils.credential_crypto import (
    KEYRING_ENV,
    CredentialEncryptionError,
    decrypt_headers,
    encrypt_headers,
    get_header_names,
    is_encrypted_headers,
)
from utils.error_handler import ErrorResponse
from utils.file_cleanup import cleanup_task_files
from utils.logger import logger
from utils.request_headers import merge_headers, redact_header_names_for_copy


def _split_url(target_url: str) -> tuple[str, str]:
    parts = urlsplit(target_url)
    host = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return host, path


def _headers_dict(items) -> Dict[str, str]:
    return {item.key: item.value for item in items}


def _protocol_config(task: AgentTask) -> Dict[str, Any]:
    try:
        value = json.loads(str(task.protocol_config or "{}"))
    except json.JSONDecodeError as exc:
        raise ErrorResponse.internal_server_error(
            "Task configuration is invalid"
        ) from exc
    if not isinstance(value, dict):
        raise ErrorResponse.internal_server_error("Task configuration is invalid")
    return value


def _assert_safe_source_inheritance(
    source: AgentTask, body: AgentTaskCreateReq
) -> None:
    """Prevent inherited secrets/data from being redirected to another target."""
    if source.protocol != body.protocol or source.target_url != body.target_url:
        raise ErrorResponse.bad_request(
            "Source credentials and dataset can only be inherited by the "
            "original target"
        )
    if body.inherit_source_headers and body.protocol == "a2a":
        source_card_url = _protocol_config(source).get("agent_card_url") or None
        requested_card_url = body.agent_card_url or None
        if source_card_url != requested_card_url:
            raise ErrorResponse.bad_request(
                "Source credentials can only be inherited with the original "
                "agent card URL"
            )


async def _get_copy_source(db, body: AgentTaskCreateReq) -> Optional[AgentTask]:
    if not body.copy_source_task_id:
        return None
    source = await db.get(AgentTask, body.copy_source_task_id)
    if not source or source.is_deleted:
        raise ErrorResponse.not_found("Source task not found")
    if body.inherit_source_headers or body.inherit_source_dataset:
        _assert_safe_source_inheritance(source, body)
    return source


def _resolved_headers(
    source: Optional[AgentTask], body: AgentTaskCreateReq
) -> Dict[str, str]:
    overrides = _headers_dict(body.headers)
    if not source or not body.inherit_source_headers:
        return overrides
    inherited = decrypt_headers(source.headers)
    return merge_headers(inherited, overrides)


def _safe_headers(header_names) -> list[Dict[str, Any]]:
    """Expose header names and state, never credential values.

    Custom header names are unbounded, so every user-supplied Agent header is
    treated as sensitive.  This guarantee does not depend on a denylist.
    """
    return redact_header_names_for_copy(header_names)


def _parse_sse_or_json(response: httpx.Response) -> Dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response is not a JSON object")
        return payload
    for line in response.text.splitlines():
        if line.startswith("data:") and line[5:].strip():
            payload = json.loads(line[5:].strip())
            if isinstance(payload, dict) and (
                "result" in payload or "error" in payload
            ):
                return payload
    raise ValueError("SSE stream did not contain a JSON-RPC response")


def _rpc_error(payload: Dict[str, Any]) -> Optional[str]:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "JSON-RPC error")
    return None


def _mcp_2026_meta(protocol_version: str) -> Dict[str, Any]:
    return {
        "io.modelcontextprotocol/protocolVersion": protocol_version,
        "io.modelcontextprotocol/clientInfo": {"name": "LMeterX", "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def _validate_protocol_dataset(body: AgentTaskCreateReq) -> None:
    """Validate every JSONL record before a protocol task is persisted."""
    if not body.dataset_file:
        return

    upload_root = os.path.realpath(UPLOAD_FOLDER)
    dataset_path = os.path.realpath(body.dataset_file)
    try:
        if os.path.commonpath([upload_root, dataset_path]) != upload_root:
            raise ValueError("dataset file is outside the upload directory")
    except ValueError as exc:
        raise ErrorResponse.bad_request(str(exc)) from exc
    if not os.path.isfile(dataset_path):
        raise ErrorResponse.bad_request("dataset file does not exist")

    configured_ids = {
        item.id
        for item in (body.a2a_scenarios if body.protocol == "a2a" else body.mcp_calls)
    }
    covered_ids: set[str] = set()
    try:
        with open(dataset_path, "r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"dataset line {line_number} is not valid JSON: {exc.msg}"
                    ) from exc
                if not isinstance(value, dict):
                    raise ValueError(
                        f"dataset line {line_number} must be a JSON object"
                    )
                try:
                    if body.protocol == "a2a":
                        row = A2ADatasetRow.model_validate(value)
                    else:
                        row = MCPDatasetRow.model_validate(value)
                except Exception as exc:
                    raise ValueError(
                        f"dataset line {line_number} is not a valid "
                        f"{body.protocol.upper()} scenario: {exc}"
                    ) from exc
                if row.scenario_id not in configured_ids:
                    raise ValueError(
                        f"dataset line {line_number} references unknown scenario_id "
                        f"{row.scenario_id!r}"
                    )
                covered_ids.add(row.scenario_id)
    except (OSError, ValueError) as exc:
        raise ErrorResponse.bad_request(str(exc)) from exc
    if not covered_ids:
        raise ErrorResponse.bad_request(
            "dataset must contain at least one JSONL record"
        )
    missing_ids = sorted(configured_ids - covered_ids)
    if missing_ids:
        raise ErrorResponse.bad_request(
            "dataset has no rows for configured scenarios: " + ", ".join(missing_ids)
        )


def _connection_response_preview(response: httpx.Response) -> Any:
    """Return a bounded upstream response body suitable for the test UI."""
    try:
        text = response.text
    except Exception:
        return None
    if not text:
        return None
    if len(text) > 4000:
        return {"body": text[:4000], "truncated": True}
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError):
        return text


def _connection_error_result(
    body: AgentTaskCreateReq,
    started: float,
    diagnostics: Dict[str, Any],
    *,
    error_type: str,
    error: str,
    response: Optional[httpx.Response] = None,
) -> Dict[str, Any]:
    upstream_response = (
        response if response is not None else diagnostics.get("response")
    )
    result: Dict[str, Any] = {
        "status": "error",
        "protocol": body.protocol,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "operation": diagnostics.get("operation"),
        "error_type": error_type,
        "error": error,
        "response": None,
    }
    if isinstance(upstream_response, httpx.Response):
        result["http_status"] = upstream_response.status_code
        result["response"] = {
            "status_code": upstream_response.status_code,
            "data": _connection_response_preview(upstream_response),
        }
    return result


async def _perform_agent_connection(
    body: AgentTaskCreateReq,
    configured_headers: Dict[str, str],
    diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    """Perform protocol discovery while retaining safe diagnostic context."""
    timeout = httpx.Timeout(body.request_timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        if body.protocol == "a2a":
            if body.agent_card_url:
                card_url = body.agent_card_url
            else:
                origin, _ = _split_url(body.target_url)
                card_url = f"{origin}/.well-known/agent-card.json"
            diagnostics["operation"] = "agent-card/get"
            response = await client.get(
                card_url,
                headers={"Accept": "application/json", **configured_headers},
            )
            diagnostics["response"] = response
            response.raise_for_status()
            card = response.json()
            required_card_fields = {
                "name",
                "description",
                "supportedInterfaces",
                "version",
                "capabilities",
                "defaultInputModes",
                "defaultOutputModes",
                "skills",
            }
            if not isinstance(card, dict):
                raise ValueError("Agent Card is not a JSON object")
            missing_fields = sorted(required_card_fields - set(card))
            if missing_fields:
                raise ValueError(
                    "Agent Card is missing required fields: "
                    + ", ".join(missing_fields)
                )
            interfaces = card.get("supportedInterfaces") or []
            compatible = [
                item
                for item in interfaces
                if isinstance(item, dict)
                and item.get("protocolVersion") == body.protocol_version
                and str(item.get("protocolBinding") or "").upper() == "JSONRPC"
                and str(item.get("url") or "").rstrip("/")
                == body.target_url.rstrip("/")
            ]
            if not compatible:
                raise ValueError(
                    "Agent Card does not advertise the target URL as the requested "
                    "JSONRPC protocol version"
                )
            interface_tenant = compatible[0].get("tenant")
            if interface_tenant != body.a2a_tenant:
                raise ValueError(
                    "a2a_tenant must exactly match the selected Agent Card interface"
                )
            if body.a2a_mode == "stream" and not card["capabilities"].get("streaming"):
                raise ValueError("Agent Card does not advertise streaming support")
            return {
                "status": "success",
                "protocol": "a2a",
                "http_status": response.status_code,
                "operation": diagnostics["operation"],
                "agent_card": {
                    "name": card.get("name"),
                    "protocol_version": card.get("protocolVersion"),
                    "capabilities": card.get("capabilities", {}),
                    "skills": card.get("skills", []),
                    "supported_interfaces": interfaces,
                },
            }

        protocol_version = body.protocol_version or "2026-07-28"
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            **configured_headers,
        }
        if protocol_version >= "2026-07-28":
            headers.update(
                {
                    "MCP-Protocol-Version": protocol_version,
                    "Mcp-Method": "tools/list",
                }
            )
            diagnostics["operation"] = "tools/list"
            listed = await client.post(
                body.target_url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {"_meta": _mcp_2026_meta(protocol_version)},
                },
            )
            diagnostics["response"] = listed
            listed.raise_for_status()
            tools_payload = _parse_sse_or_json(listed)
            if _rpc_error(tools_payload):
                raise ValueError(_rpc_error(tools_payload))
            tools_result = tools_payload.get("result") or {}
            if tools_result.get("resultType") != "complete":
                raise ValueError("MCP tools/list did not return a complete result")
            return {
                "status": "success",
                "protocol": "mcp",
                "http_status": listed.status_code,
                "operation": diagnostics["operation"],
                "server": {},
                "protocol_version": protocol_version,
                "capabilities": {"tools": {}},
                "tools": tools_result.get("tools", []),
            }

        diagnostics["operation"] = "initialize"
        initialize = await client.post(
            body.target_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": body.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "LMeterX", "version": "1.0"},
                },
            },
        )
        diagnostics["response"] = initialize
        initialize.raise_for_status()
        init_payload = _parse_sse_or_json(initialize)
        if _rpc_error(init_payload):
            raise ValueError(_rpc_error(init_payload))
        init_result = init_payload.get("result") or {}
        headers["MCP-Protocol-Version"] = str(
            init_result.get("protocolVersion") or protocol_version
        )
        session_id = initialize.headers.get("mcp-session-id")
        if session_id:
            headers["MCP-Session-Id"] = session_id
        diagnostics["operation"] = "notifications/initialized"
        ready = await client.post(
            body.target_url,
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        diagnostics["response"] = ready
        ready.raise_for_status()
        diagnostics["operation"] = "tools/list"
        listed = await client.post(
            body.target_url,
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        diagnostics["response"] = listed
        listed.raise_for_status()
        tools_payload = _parse_sse_or_json(listed)
        if _rpc_error(tools_payload):
            raise ValueError(_rpc_error(tools_payload))
        tools_result = tools_payload.get("result") or {}
        return {
            "status": "success",
            "protocol": "mcp",
            "http_status": listed.status_code,
            "operation": diagnostics["operation"],
            "server": init_result.get("serverInfo", {}),
            "protocol_version": init_result.get("protocolVersion"),
            "capabilities": init_result.get("capabilities", {}),
            "tools": tools_result.get("tools", []),
        }


async def test_agent_connection(
    body: AgentTaskCreateReq,
    configured_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Test a protocol endpoint and always return actionable diagnostics."""
    started = time.perf_counter()
    diagnostics: Dict[str, Any] = {}
    headers = (
        _headers_dict(body.headers)
        if configured_headers is None
        else configured_headers
    )
    try:
        result = await _perform_agent_connection(body, headers, diagnostics)
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        reason = exc.response.reason_phrase or "HTTP error"
        return _connection_error_result(
            body,
            started,
            diagnostics,
            error_type="http_error",
            error=f"Target returned HTTP {status} {reason}",
            response=exc.response,
        )
    except httpx.TimeoutException:
        operation = diagnostics.get("operation") or "connecting"
        return _connection_error_result(
            body,
            started,
            diagnostics,
            error_type="timeout",
            error=(
                f"Request timed out after {body.request_timeout:g} seconds "
                f"while performing {operation}"
            ),
        )
    except httpx.ConnectError as exc:
        return _connection_error_result(
            body,
            started,
            diagnostics,
            error_type="connection_error",
            error=f"Could not connect to the target service: {exc}",
        )
    except httpx.RequestError as exc:
        return _connection_error_result(
            body,
            started,
            diagnostics,
            error_type="request_error",
            error=f"Request to the target service failed: {exc}",
        )
    except ValueError as exc:
        return _connection_error_result(
            body,
            started,
            diagnostics,
            error_type="invalid_protocol_response",
            error=f"Invalid {body.protocol.upper()} response: {exc}",
        )
    except Exception as exc:
        logger.exception(
            "Unexpected {} connection test error during {}: {}",
            body.protocol.upper(),
            diagnostics.get("operation") or "connect",
            type(exc).__name__,
        )
        return _connection_error_result(
            body,
            started,
            diagnostics,
            error_type="internal_error",
            error="The connection test failed because of an unexpected server error",
        )


async def test_agent_connection_for_request(
    request: Request, body: AgentTaskCreateReq
) -> Dict[str, Any]:
    """Test a copied task while resolving inherited credentials server-side."""
    source = await _get_copy_source(request.state.db, body)
    try:
        headers = _resolved_headers(source, body)
    except CredentialEncryptionError as exc:
        logger.error("Agent credential decryption is unavailable: {}", exc)
        raise ErrorResponse(
            503,
            "Agent credential encryption is not configured",
            code="credential_encryption_unavailable",
        ) from exc
    return await test_agent_connection(body, configured_headers=headers)


def _creator(request: Request) -> str:
    user = get_current_user(request)
    if isinstance(user, dict):
        return str(user.get("username") or user.get("sub") or "-")[:100]
    return "-"


def _assert_can_manage(request: Request, task: AgentTask) -> str:
    """Require task ownership or the existing administrator role."""
    username = _creator(request)
    if task.created_by != username and not is_admin_user(username):
        raise ErrorResponse.forbidden("You do not have permission to manage this task")
    return username


def _task_dict(task: AgentTask, include_config: bool = False) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": task.id,
        "name": task.name,
        "status": str(task.status or "created").lower(),
        "created_by": task.created_by or "-",
        "protocol": task.protocol,
        "protocol_version": task.protocol_version,
        "target_url": task.target_url,
        "concurrent_users": task.concurrent_users,
        "spawn_rate": task.spawn_rate,
        "duration": task.duration,
        "engine_id": task.engine_id,
        "cluster_id": task.cluster_id or "local",
        "error_message": task.error_message or "",
        "created_at": safe_isoformat(task.created_at),
        "updated_at": safe_isoformat(task.updated_at),
    }
    if include_config:
        try:
            config = json.loads(str(task.protocol_config or "{}"))
        except json.JSONDecodeError:
            config = {}
        dataset_file = config.pop("dataset_file", None)
        try:
            header_names = get_header_names(task.headers)
        except CredentialEncryptionError:
            # Do not leak ciphertext, key identifiers, or crypto failures to a
            # browser response. Execution will fail closed with server logs.
            header_names = []
        data.update(config)
        data["dataset_configured"] = bool(dataset_file)
        data["dataset_file_name"] = (
            os.path.basename(str(dataset_file)) if dataset_file else None
        )
        data["headers"] = _safe_headers(header_names)
        data["redacted_header_keys"] = header_names
        data["has_configured_headers"] = bool(header_names)
    return data


def _next_rerun_name(name: str) -> str:
    """Match the existing LLM/HTTP task rerun suffix convention."""
    match = re.match(r"^(.*)-(\d+)$", name)
    if match:
        suffix = f"-{int(match.group(2)) + 1}"
        base = match.group(1)
    else:
        suffix = "-1"
        base = name
    return f"{base[: 100 - len(suffix)]}{suffix}"


def _copy_dataset_for_rerun(config: Dict[str, Any], task_id: str) -> Optional[str]:
    """Give a rerun independent ownership of its uploaded dataset file."""
    source = config.get("dataset_file")
    if not source:
        return None
    upload_root = os.path.realpath(UPLOAD_FOLDER)
    source_path = os.path.realpath(str(source))
    if os.path.commonpath([upload_root, source_path]) != upload_root:
        raise ValueError("dataset file is outside the upload directory")
    if not os.path.isfile(source_path):
        raise ValueError("dataset file does not exist")
    destination_dir = os.path.join(upload_root, task_id)
    os.makedirs(destination_dir, exist_ok=True)
    destination = os.path.join(destination_dir, os.path.basename(source_path))
    shutil.copy2(source_path, destination)
    return destination


async def create_agent_task(
    request: Request, body: AgentTaskCreateReq
) -> Dict[str, Any]:
    db = request.state.db
    source = await _get_copy_source(db, body)
    task_id = str(uuid.uuid4())
    copied_dataset: Optional[str] = None
    try:
        from service.dataset_service import (
            authorize_managed_dataset_path,
            resolve_dataset_for_task,
        )

        managed_dataset_path = await resolve_dataset_for_task(
            request, body.dataset_id, body.protocol, task_id
        )
        if not managed_dataset_path:
            managed_dataset_path = await authorize_managed_dataset_path(
                request, body.dataset_file, body.protocol, task_id
            )
        if managed_dataset_path:
            body.dataset_file = managed_dataset_path
            copied_dataset = managed_dataset_path
            body.inherit_source_dataset = False
        if source and body.inherit_source_dataset and not body.dataset_file:
            copied_dataset = _copy_dataset_for_rerun(_protocol_config(source), task_id)
            body.dataset_file = copied_dataset
        _validate_protocol_dataset(body)

        resolved_headers = _resolved_headers(source, body)
        stored_headers = encrypt_headers(resolved_headers)
        if (
            source
            and body.inherit_source_headers
            and not is_encrypted_headers(source.headers)
        ):
            # Upgrade legacy plaintext in the same transaction as the copy.
            source.headers = encrypt_headers(decrypt_headers(source.headers))
    except ErrorResponse:
        await db.rollback()
        cleanup_task_files(task_id, test_data_path=copied_dataset)
        raise
    except CredentialEncryptionError as exc:
        await db.rollback()
        cleanup_task_files(task_id, test_data_path=copied_dataset)
        logger.error("Agent credential encryption is unavailable: {}", exc)
        raise ErrorResponse(
            503,
            "Agent credential encryption is not configured",
            code="credential_encryption_unavailable",
        ) from exc
    except (OSError, ValueError) as exc:
        await db.rollback()
        cleanup_task_files(task_id, test_data_path=copied_dataset)
        raise ErrorResponse.bad_request(str(exc)) from exc

    target_host, api_path = _split_url(body.target_url)
    task = AgentTask(
        id=task_id,
        name=body.name,
        status="created",
        created_by=_creator(request),
        protocol=body.protocol,
        protocol_version=body.protocol_version,
        target_url=body.target_url,
        target_host=target_host,
        api_path=api_path,
        headers=stored_headers,
        protocol_config=body.config_json(),
        concurrent_users=body.concurrent_users,
        spawn_rate=body.spawn_rate,
        duration=body.duration,
        cluster_id=body.cluster_id,
        error_message="",
    )
    try:
        db.add(task)
        add_dispatch_entry(
            db, task_type="agent", task_id=task_id, cluster_id=body.cluster_id
        )
        await db.flush()
        await db.commit()
    except Exception as exc:
        await db.rollback()
        cleanup_task_files(task_id, test_data_path=copied_dataset)
        logger.error("Failed to create agent task: {}", exc, exc_info=True)
        raise ErrorResponse.internal_server_error("Failed to create agent task")
    if source:
        logger.info(
            "Agent task copied: source_task_id={}, new_task_id={}, requester={}, "
            "headers_inherited={}, dataset_inherited={}",
            source.id,
            task_id,
            _creator(request),
            body.inherit_source_headers,
            bool(copied_dataset),
        )
    return {"task_id": task_id, "status": "created", "message": "Agent task created"}


async def update_agent_task(
    request: Request, task_id: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Update mutable agent task fields; currently only the display name."""
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ErrorResponse.bad_request("Task name is required")
    if len(name) > 100:
        raise ErrorResponse.bad_request("Task name must not exceed 100 characters")
    db = request.state.db
    task = await db.get(AgentTask, task_id)
    if not task or task.is_deleted:
        raise ErrorResponse.not_found("Task not found")
    _assert_can_manage(request, task)
    try:
        task.name = name
        await db.commit()
        await db.refresh(task)
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to rename agent task {}: {}", task_id, exc, exc_info=True)
        raise ErrorResponse.internal_server_error("Failed to rename agent task")
    return {"status": "success", "task_id": task_id, "name": task.name}


async def rerun_agent_task(request: Request, task_id: str) -> Dict[str, Any]:
    """Clone and queue a task server-side without exposing its credentials."""
    db = request.state.db
    source = await db.get(AgentTask, task_id)
    if not source or source.is_deleted:
        raise ErrorResponse.not_found("Task not found")
    requester = _creator(request)

    new_task_id = str(uuid.uuid4())
    try:
        config = json.loads(str(source.protocol_config or "{}"))
    except json.JSONDecodeError as exc:
        raise ErrorResponse.internal_server_error(
            "Task configuration is invalid"
        ) from exc

    copied_dataset: Optional[str] = None
    try:
        copied_dataset = _copy_dataset_for_rerun(config, new_task_id)
        config["dataset_file"] = copied_dataset
        # Preserve the complete runtime credential set without returning it to
        # the browser. Upgrade legacy plaintext when encryption is configured,
        # while retaining the documented execution compatibility for tasks
        # created before credential encryption was enabled.
        stored_headers = str(source.headers or "{}")
        if is_encrypted_headers(stored_headers):
            # Fail before queueing if this Backend cannot decrypt the task for
            # an Engine. Reuse the authenticated envelope instead of rotating
            # credentials as an unrelated side effect of rerunning a task.
            decrypt_headers(stored_headers)
            rerun_headers = stored_headers
        else:
            legacy_headers = decrypt_headers(stored_headers)
            try:
                rerun_headers = encrypt_headers(legacy_headers)
            except CredentialEncryptionError:
                if os.getenv(KEYRING_ENV, "").strip() or os.getenv("TESTING"):
                    raise
                rerun_headers = stored_headers
                logger.warning(
                    "Rerunning legacy Agent task {} without credential "
                    "encryption; configure {} to migrate stored headers",
                    task_id,
                    KEYRING_ENV,
                )
            else:
                if legacy_headers:
                    source.headers = rerun_headers
        task = AgentTask(
            id=new_task_id,
            name=_next_rerun_name(source.name),
            status="created",
            created_by=_creator(request),
            protocol=source.protocol,
            protocol_version=source.protocol_version,
            target_url=source.target_url,
            target_host=source.target_host,
            api_path=source.api_path,
            headers=rerun_headers,
            protocol_config=json.dumps(config, ensure_ascii=False),
            concurrent_users=source.concurrent_users,
            spawn_rate=source.spawn_rate,
            duration=source.duration,
            cluster_id=source.cluster_id,
            error_message="",
        )
        db.add(task)
        add_dispatch_entry(
            db,
            task_type="agent",
            task_id=new_task_id,
            cluster_id=source.cluster_id,
        )
        await db.flush()
        await db.commit()
        logger.info(
            "Agent task rerun created: source_task_id={}, new_task_id={}, "
            "source_owner={}, requester={}",
            task_id,
            new_task_id,
            source.created_by or "-",
            requester,
        )
    except CredentialEncryptionError as exc:
        await db.rollback()
        cleanup_task_files(new_task_id, test_data_path=copied_dataset)
        logger.error("Agent credential encryption is unavailable: {}", exc)
        raise ErrorResponse(
            503,
            "Agent credential encryption is not configured",
            code="credential_encryption_unavailable",
        ) from exc
    except (OSError, ValueError) as exc:
        await db.rollback()
        cleanup_task_files(new_task_id, test_data_path=copied_dataset)
        raise ErrorResponse.bad_request(str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        cleanup_task_files(new_task_id, test_data_path=copied_dataset)
        logger.error("Failed to rerun agent task {}: {}", task_id, exc, exc_info=True)
        raise ErrorResponse.internal_server_error("Failed to rerun agent task")
    return {
        "task_id": new_task_id,
        "status": "created",
        "message": "Agent task rerun created",
    }


async def list_agent_tasks(
    request: Request, page: int = 1, page_size: int = 20, protocol: Optional[str] = None
) -> Dict[str, Any]:
    conditions = [AgentTask.is_deleted == 0]
    if protocol in {"a2a", "mcp"}:
        conditions.append(AgentTask.protocol == protocol)
    db = request.state.db
    count = await db.scalar(
        select(func.count()).select_from(AgentTask).where(*conditions)
    )
    result = await db.execute(
        select(AgentTask)
        .where(*conditions)
        .order_by(AgentTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "data": [_task_dict(task) for task in result.scalars().all()],
        "pagination": {"total": count or 0, "page": page, "page_size": page_size},
        "status": "success",
    }


async def get_agent_task(request: Request, task_id: str) -> Dict[str, Any]:
    task = await request.state.db.get(AgentTask, task_id)
    if not task or task.is_deleted:
        raise ErrorResponse.not_found("Task not found")
    return _task_dict(task, include_config=True)


async def get_agent_task_copy_template(
    request: Request, task_id: str
) -> Dict[str, Any]:
    """Return a copy-safe template that cannot disclose credential values."""
    task = await request.state.db.get(AgentTask, task_id)
    if not task or task.is_deleted:
        raise ErrorResponse.not_found("Task not found")
    data = _task_dict(task, include_config=True)
    data["copy_source_task_id"] = task.id
    data["inherit_source_headers"] = bool(data.get("has_configured_headers"))
    data["inherit_source_dataset"] = bool(data.get("dataset_configured"))
    data["dataset_reupload_required"] = False
    data["copy_policy"] = {
        "credentials_removed": bool(data.get("has_configured_headers")),
        "credential_reuse_allowed": True,
        "credentials_inherited_on_start": bool(data.get("has_configured_headers")),
        "dataset_inherited_on_start": bool(data.get("dataset_configured")),
    }
    logger.info(
        "Agent task copy template requested: task_id={}, requester={}, "
        "credentials_removed={}",
        task_id,
        _creator(request),
        data["copy_policy"]["credentials_removed"],
    )
    return data


async def migrate_legacy_agent_headers(db) -> int:
    """Encrypt legacy plaintext Agent headers in-place during startup."""
    result = await db.execute(select(AgentTask))
    migrated = 0
    changed = False
    for task in result.scalars().all():
        stored = str(task.headers or "{}")
        if task.is_deleted:
            if stored != "{}":
                task.headers = "{}"
                changed = True
            continue
        if is_encrypted_headers(stored):
            continue
        headers = decrypt_headers(stored)
        if not headers:
            continue
        task.headers = encrypt_headers(headers)
        migrated += 1
        changed = True
    if changed:
        await db.commit()
    if migrated:
        logger.info("Encrypted {} legacy Agent credential record(s)", migrated)
    return migrated


async def get_agent_task_results(request: Request, task_id: str) -> Dict[str, Any]:
    task = await request.state.db.get(AgentTask, task_id)
    if not task or task.is_deleted:
        raise ErrorResponse.not_found("Task not found")
    result = await request.state.db.execute(
        select(AgentTaskResult)
        .where(AgentTaskResult.task_id == task_id)
        .order_by(AgentTaskResult.id.asc())
    )
    rows = [item.to_dict() for item in result.scalars().all()]
    summary = next(
        (row["details"] for row in rows if row["metric_type"] == "protocol_summary"), {}
    )
    return {"status": "success", "results": rows, "protocol_metrics": summary}


async def stop_agent_task(request: Request, task_id: str) -> Dict[str, Any]:
    task = await request.state.db.get(AgentTask, task_id)
    if not task or task.is_deleted:
        raise ErrorResponse.not_found("Task not found")
    _assert_can_manage(request, task)
    if str(task.status).lower() in {"created", "queuing"}:
        task.status = "stopped"
        await cancel_dispatch_entry(
            request.state.db, task_type="agent", task_id=task_id
        )
    elif str(task.status).lower() == "running":
        task.status = "stopping"
    await request.state.db.flush()
    return {"task_id": task_id, "status": task.status}


async def delete_agent_task(request: Request, task_id: str) -> Dict[str, Any]:
    task = await request.state.db.get(AgentTask, task_id)
    if not task or task.is_deleted:
        raise ErrorResponse.not_found("Task not found")
    _assert_can_manage(request, task)
    if str(task.status).lower() in {"created", "queuing", "running", "stopping"}:
        raise ErrorResponse.bad_request("Stop the task before deleting it")
    task.is_deleted = 1
    # Soft-deleted task metadata can be retained, but its credential material
    # has no further purpose and must be cryptographically erased.
    task.headers = "{}"
    try:
        config = json.loads(str(task.protocol_config or "{}"))
    except json.JSONDecodeError:
        config = {}
    cleanup_task_files(task_id, test_data_path=config.get("dataset_file"))
    await request.state.db.execute(
        delete(AgentTaskResult).where(AgentTaskResult.task_id == task_id)
    )
    await request.state.db.flush()
    return {"task_id": task_id, "status": "deleted"}
