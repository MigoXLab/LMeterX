import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from model.agent_task import AgentTaskCreateReq
from service.agent_task_service import (
    _copy_dataset_for_rerun,
    _mcp_2026_meta,
    _next_rerun_name,
    _parse_sse_or_json,
    _safe_headers,
    _split_url,
    _task_dict,
    _validate_protocol_dataset,
    create_agent_task,
    get_agent_task_copy_template,
    migrate_legacy_agent_headers,
    rerun_agent_task,
)
from service.agent_task_service import (
    test_agent_connection as run_agent_connection_test,
)
from utils.credential_crypto import (
    CredentialEncryptionError,
    decrypt_headers,
    encrypt_headers,
    get_header_names,
    is_encrypted_headers,
)
from utils.error_handler import ErrorResponse


def _a2a_payload():
    return {
        "name": "A2A async benchmark",
        "protocol": "a2a",
        "target_url": "https://agent.example.com/rpc",
        "a2a_scenarios": [
            {
                "id": "message",
                "name": "message",
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "hello"}, {"data": {"requestId": "1"}}],
                },
            }
        ],
    }


def test_a2a_defaults_to_v1_async_poll():
    request = AgentTaskCreateReq(**_a2a_payload())
    assert request.protocol_version == "1.0"
    assert request.a2a_mode == "async_poll"
    assert request.a2a_scenarios[0].message["parts"][1]["data"]["requestId"] == "1"


def test_a2a_rejects_non_standard_part_shape():
    payload = _a2a_payload()
    payload["a2a_scenarios"][0]["message"]["parts"] = [{"prompt": "not a Part"}]
    with pytest.raises(ValidationError, match="exactly one"):
        AgentTaskCreateReq(**payload)


def test_a2a_rejects_non_protojson_role_alias():
    payload = _a2a_payload()
    payload["a2a_scenarios"][0]["message"]["role"] = "user"
    with pytest.raises(ValidationError, match="ROLE_USER"):
        AgentTaskCreateReq(**payload)


def test_mcp_requires_standard_tool_call_arguments_object():
    request = AgentTaskCreateReq(
        name="MCP benchmark",
        protocol="mcp",
        target_url="https://mcp.example.com/mcp",
        mcp_calls=[
            {
                "id": "weather",
                "name": "weather",
                "tool_name": "get_weather",
                "arguments": {"city": "Shanghai"},
            }
        ],
    )
    assert request.protocol_version == "2026-07-28"
    assert request.mcp_calls[0].arguments == {"city": "Shanghai"}


def test_agent_header_values_must_not_be_empty():
    payload = _a2a_payload()
    payload["headers"] = [{"key": "SCP-HUB-API-KEY", "value": ""}]
    with pytest.raises(ValidationError, match="at least 1 character"):
        AgentTaskCreateReq(**payload)


def test_every_custom_agent_header_is_write_only():
    result = _safe_headers(
        {
            "SCP-HUB-API-KEY": "sk-sensitive",
            "X-Arbitrary-Custom": "also-sensitive",
        }
    )
    serialized = json.dumps(result)
    assert "sk-sensitive" not in serialized
    assert "also-sensitive" not in serialized
    assert result == [
        {
            "key": "SCP-HUB-API-KEY",
            "value": None,
            "sensitive": True,
            "configured": True,
            "required_on_copy": False,
            "inherited_on_start": True,
        },
        {
            "key": "X-Arbitrary-Custom",
            "value": None,
            "sensitive": True,
            "configured": True,
            "required_on_copy": False,
            "inherited_on_start": True,
        },
    ]


def test_agent_headers_are_encrypted_at_rest_and_legacy_values_still_load():
    encrypted = encrypt_headers({"SCP-HUB-API-KEY": "sk-sensitive"})
    assert is_encrypted_headers(encrypted)
    assert "sk-sensitive" not in encrypted
    assert get_header_names(encrypted) == ["SCP-HUB-API-KEY"]
    assert decrypt_headers(encrypted) == {"SCP-HUB-API-KEY": "sk-sensitive"}
    assert decrypt_headers('{"X-Legacy":"legacy-secret"}') == {
        "X-Legacy": "legacy-secret"
    }


def test_tampered_agent_header_ciphertext_fails_closed():
    envelope = json.loads(encrypt_headers({"Authorization": "Bearer secret"}))
    envelope["ciphertext"] = envelope["ciphertext"][:-2] + "aa"
    with pytest.raises(CredentialEncryptionError, match="integrity"):
        decrypt_headers(json.dumps(envelope))


def test_task_detail_never_serializes_header_values():
    task = SimpleNamespace(
        id="agent-1",
        name="MCP",
        status="completed",
        created_by="alice",
        protocol="mcp",
        protocol_version="2026-07-28",
        target_url="https://mcp.example.com/mcp",
        concurrent_users=1,
        spawn_rate=1,
        duration=60,
        engine_id=None,
        cluster_id="local",
        error_message="",
        created_at=None,
        updated_at=None,
        protocol_config='{"mcp_calls":[]}',
        headers=encrypt_headers({"SCP-HUB-API-KEY": "sk-sensitive"}),
    )
    detail = _task_dict(task, include_config=True)
    assert "sk-sensitive" not in json.dumps(detail)
    assert detail["redacted_header_keys"] == ["SCP-HUB-API-KEY"]
    assert detail["headers"][0]["configured"] is True


@pytest.mark.asyncio
async def test_copy_template_removes_credentials_and_dataset_path():
    task = SimpleNamespace(
        id="agent-1",
        name="A2A",
        status="completed",
        created_by="alice",
        protocol="a2a",
        protocol_version="1.0",
        target_url="https://agent.example.com/rpc",
        concurrent_users=1,
        spawn_rate=1,
        duration=60,
        engine_id=None,
        cluster_id="local",
        error_message="",
        created_at=None,
        updated_at=None,
        protocol_config='{"dataset_file":"/uploads/private.jsonl"}',
        headers=encrypt_headers({"X-Custom": "private-value"}),
        is_deleted=0,
    )
    request = Mock()
    request.state.db.get = AsyncMock(return_value=task)

    result = await get_agent_task_copy_template(request, task.id)

    assert "private-value" not in json.dumps(result)
    assert "dataset_file" not in result
    assert result["dataset_reupload_required"] is False
    assert result["copy_source_task_id"] == task.id
    assert result["inherit_source_headers"] is True
    assert result["inherit_source_dataset"] is True
    assert result["copy_policy"]["credential_reuse_allowed"] is True
    assert result["copy_policy"]["credentials_inherited_on_start"] is True
    assert result["copy_policy"]["dataset_inherited_on_start"] is True


@pytest.mark.asyncio
async def test_copy_and_start_inherits_all_server_side_data(monkeypatch):
    source = SimpleNamespace(
        id="agent-source",
        name="Original MCP",
        status="completed",
        is_deleted=0,
        created_by="alice",
        protocol="mcp",
        protocol_version="2026-07-28",
        target_url="https://mcp.example.com/mcp",
        target_host="https://mcp.example.com",
        api_path="/mcp",
        headers=encrypt_headers(
            {
                "SCP-HUB-API-KEY": "source-secret",
                "X-Tenant": "tenant-a",
            }
        ),
        protocol_config=json.dumps(
            {
                "request_timeout": 45,
                "dataset_file": "/uploads/source/data.jsonl",
                "mcp_calls": [
                    {
                        "id": "protein",
                        "name": "Protein",
                        "tool_name": "get_protein",
                        "arguments": {"name": "TP53"},
                        "weight": 2,
                    }
                ],
            }
        ),
    )
    body = AgentTaskCreateReq(
        name="Original MCP (Copy)",
        protocol="mcp",
        protocol_version="2026-07-28",
        target_url=source.target_url,
        headers=[],
        request_timeout=45,
        mcp_calls=json.loads(source.protocol_config)["mcp_calls"],
        concurrent_users=8,
        spawn_rate=3,
        duration=120,
        cluster_id="gpu-prod",
        copy_source_task_id=source.id,
        inherit_source_headers=True,
        inherit_source_dataset=True,
    )
    request = Mock()
    request.state.db = Mock()
    request.state.db.get = AsyncMock(return_value=source)
    request.state.db.add = Mock()
    request.state.db.flush = AsyncMock()
    request.state.db.commit = AsyncMock()
    request.state.db.rollback = AsyncMock()
    monkeypatch.setattr(
        "service.agent_task_service._copy_dataset_for_rerun",
        lambda _config, _task_id: "/uploads/copied/data.jsonl",
    )
    monkeypatch.setattr(
        "service.agent_task_service._validate_protocol_dataset", lambda _body: None
    )
    monkeypatch.setattr("service.agent_task_service._creator", lambda _: "bob")

    response = await create_agent_task(request, body)
    cloned = request.state.db.add.call_args_list[0].args[0]

    assert "source-secret" not in json.dumps(response)
    assert cloned.created_by == "bob"
    assert cloned.target_url == source.target_url
    assert cloned.concurrent_users == 8
    assert cloned.spawn_rate == 3
    assert cloned.duration == 120
    assert cloned.cluster_id == "gpu-prod"
    assert json.loads(cloned.protocol_config)["dataset_file"] == (
        "/uploads/copied/data.jsonl"
    )
    assert decrypt_headers(cloned.headers) == {
        "SCP-HUB-API-KEY": "source-secret",
        "X-Tenant": "tenant-a",
    }


@pytest.mark.asyncio
async def test_copy_cannot_redirect_inherited_credentials(monkeypatch):
    source = SimpleNamespace(
        id="agent-source",
        is_deleted=0,
        protocol="mcp",
        target_url="https://mcp.example.com/mcp",
        headers=encrypt_headers({"Authorization": "Bearer source-secret"}),
        protocol_config='{"dataset_file":null}',
    )
    body = AgentTaskCreateReq(
        name="Redirected Copy",
        protocol="mcp",
        target_url="https://attacker.example.com/mcp",
        mcp_calls=[
            {
                "id": "tool",
                "name": "Tool",
                "tool_name": "call_tool",
                "arguments": {},
            }
        ],
        copy_source_task_id=source.id,
        inherit_source_headers=True,
    )
    request = Mock()
    request.state.db.get = AsyncMock(return_value=source)

    with pytest.raises(ErrorResponse, match="original target") as exc_info:
        await create_agent_task(request, body)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_other_user_can_rerun_complete_task_without_receiving_credentials(
    monkeypatch,
):
    source = SimpleNamespace(
        id="agent-1",
        name="Original MCP",
        status="completed",
        is_deleted=0,
        created_by="alice",
        protocol="mcp",
        protocol_version="2026-07-28",
        target_url="https://mcp.example.com/mcp",
        target_host="https://mcp.example.com",
        api_path="/mcp",
        headers=encrypt_headers({"SCP-HUB-API-KEY": "source-secret"}),
        protocol_config=json.dumps(
            {
                "request_timeout": 45,
                "dataset_file": None,
                "mcp_calls": [
                    {
                        "id": "protein",
                        "name": "Protein",
                        "tool_name": "get_protein",
                        "arguments": {"name": "TP53"},
                        "weight": 2,
                    }
                ],
            }
        ),
        concurrent_users=8,
        spawn_rate=3,
        duration=120,
        cluster_id="gpu-prod",
    )
    request = Mock()
    request.state.db = Mock()
    request.state.db.get = AsyncMock(return_value=source)
    request.state.db.add = Mock()
    request.state.db.flush = AsyncMock()
    request.state.db.commit = AsyncMock()
    request.state.db.rollback = AsyncMock()
    monkeypatch.setattr("service.agent_task_service._creator", lambda _: "bob")

    response = await rerun_agent_task(request, source.id)
    cloned = request.state.db.add.call_args_list[0].args[0]

    assert "source-secret" not in json.dumps(response)
    assert cloned.created_by == "bob"
    assert cloned.protocol_config == source.protocol_config
    assert cloned.target_url == source.target_url
    assert cloned.concurrent_users == source.concurrent_users
    assert cloned.spawn_rate == source.spawn_rate
    assert cloned.duration == source.duration
    assert cloned.cluster_id == source.cluster_id
    assert decrypt_headers(cloned.headers) == {"SCP-HUB-API-KEY": "source-secret"}


@pytest.mark.asyncio
async def test_rerun_legacy_task_without_encryption_key_remains_compatible(
    monkeypatch,
):
    source = SimpleNamespace(
        id="legacy-agent",
        name="Legacy MCP",
        status="completed",
        is_deleted=0,
        created_by="alice",
        protocol="mcp",
        protocol_version="2026-07-28",
        target_url="https://mcp.example.com/mcp",
        target_host="https://mcp.example.com",
        api_path="/mcp",
        headers='{"SCP-HUB-API-KEY":"legacy-secret"}',
        protocol_config='{"dataset_file":null,"mcp_calls":[]}',
        concurrent_users=1,
        spawn_rate=1,
        duration=60,
        cluster_id="local",
    )
    request = Mock()
    request.state.db = Mock()
    request.state.db.get = AsyncMock(return_value=source)
    request.state.db.add = Mock()
    request.state.db.flush = AsyncMock()
    request.state.db.commit = AsyncMock()
    request.state.db.rollback = AsyncMock()
    monkeypatch.delenv("AGENT_CREDENTIAL_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("TESTING", raising=False)

    response = await rerun_agent_task(request, source.id)
    cloned = request.state.db.add.call_args_list[0].args[0]

    assert response["status"] == "created"
    assert cloned.headers == source.headers
    assert decrypt_headers(cloned.headers) == {"SCP-HUB-API-KEY": "legacy-secret"}
    request.state.db.commit.assert_awaited_once()
    request.state.db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_migrates_legacy_plaintext_headers_to_ciphertext():
    task = SimpleNamespace(headers='{"SCP-HUB-API-KEY":"legacy-secret"}', is_deleted=0)
    result = Mock()
    result.scalars.return_value.all.return_value = [task]
    db = Mock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()

    migrated = await migrate_legacy_agent_headers(db)

    assert migrated == 1
    assert is_encrypted_headers(task.headers)
    assert "legacy-secret" not in task.headers
    assert decrypt_headers(task.headers) == {"SCP-HUB-API-KEY": "legacy-secret"}
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_startup_clears_credentials_from_legacy_deleted_tasks():
    task = SimpleNamespace(headers='{"SCP-HUB-API-KEY":"deleted-secret"}', is_deleted=1)
    result = Mock()
    result.scalars.return_value.all.return_value = [task]
    db = Mock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()

    migrated = await migrate_legacy_agent_headers(db)

    assert migrated == 0
    assert task.headers == "{}"
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("header", ["mcp-method", "Mcp-Param-Region", "TraceParent"])
def test_rejects_protocol_headers_managed_by_lmeterx(header):
    payload = _a2a_payload()
    payload["headers"] = [{"key": header, "value": "override"}]
    with pytest.raises(ValidationError, match="managed by LMeterX"):
        AgentTaskCreateReq(**payload)


@pytest.mark.parametrize(
    ("protocol", "version"),
    [("a2a", "0.3"), ("mcp", "2025-06-18"), ("mcp", "next")],
)
def test_rejects_protocol_versions_not_implemented(protocol, version):
    payload = _a2a_payload()
    payload["protocol"] = protocol
    payload["protocol_version"] = version
    if protocol == "mcp":
        payload["a2a_scenarios"] = []
        payload["mcp_calls"] = [
            {
                "id": "weather",
                "name": "weather",
                "tool_name": "get_weather",
                "arguments": {},
            }
        ]
    with pytest.raises(ValidationError, match="supported|A2A"):
        AgentTaskCreateReq(**payload)


def test_split_url_keeps_query_in_protocol_endpoint():
    assert _split_url("https://agent.example.com/a2a?tenant=1") == (
        "https://agent.example.com",
        "/a2a?tenant=1",
    )


def test_mcp_sse_parser_reads_jsonrpc_response():
    import httpx

    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n',
    )
    assert _parse_sse_or_json(response)["result"]["tools"] == []


def test_a2a_sse_parser_reads_http_json_task():
    import httpx

    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=(
            'event: message\ndata: {"task":{"id":"t1",'
            '"status":{"state":"completed"}}}\n\n'
        ),
    )
    payload = _parse_sse_or_json(response)
    assert payload["task"]["id"] == "t1"
    assert payload["task"]["status"]["state"] == "completed"


def test_mcp_2026_metadata_matches_protocol_version():
    metadata = _mcp_2026_meta("2026-07-28")
    assert metadata["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert metadata["io.modelcontextprotocol/clientInfo"]["name"] == "LMeterX"


def _mcp_payload():
    return {
        "name": "MCP benchmark",
        "protocol": "mcp",
        "target_url": "https://mcp.example.com/mcp",
        "mcp_calls": [
            {
                "id": "weather",
                "name": "weather",
                "tool_name": "get_weather",
                "arguments": {"city": "Shanghai"},
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_factory", "operation"),
    [(_mcp_payload, "tools/list"), (_a2a_payload, "agent-card/get")],
)
async def test_agent_connection_reports_upstream_http_error_for_each_protocol(
    monkeypatch, payload_factory, operation
):
    import httpx

    async def fail_with_http_status(_body, _headers, diagnostics):
        diagnostics["operation"] = operation
        request = httpx.Request("POST", "https://target.example.com/protocol")
        response = httpx.Response(
            401,
            json={"error": "invalid credentials"},
            request=request,
        )
        diagnostics["response"] = response
        raise httpx.HTTPStatusError(
            "401 Unauthorized", request=request, response=response
        )

    monkeypatch.setattr(
        "service.agent_task_service._perform_agent_connection",
        fail_with_http_status,
    )

    result = await run_agent_connection_test(AgentTaskCreateReq(**payload_factory()))

    assert result["status"] == "error"
    assert result["error_type"] == "http_error"
    assert result["http_status"] == 401
    assert result["operation"] == operation
    assert result["response"] == {
        "status_code": 401,
        "data": {"error": "invalid credentials"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_factory", "operation"),
    [(_mcp_payload, "initialize"), (_a2a_payload, "agent-card/get")],
)
async def test_agent_connection_reports_timeout_for_each_protocol(
    monkeypatch, payload_factory, operation
):
    import httpx

    async def fail_with_timeout(_body, _headers, diagnostics):
        diagnostics["operation"] = operation
        raise httpx.ReadTimeout("upstream did not respond")

    monkeypatch.setattr(
        "service.agent_task_service._perform_agent_connection",
        fail_with_timeout,
    )

    result = await run_agent_connection_test(AgentTaskCreateReq(**payload_factory()))

    assert result["status"] == "error"
    assert result["error_type"] == "timeout"
    assert result["operation"] == operation
    assert result["response"] is None
    assert "timed out" in result["error"]


def test_a2a_dataset_is_optional_and_scenarios_remain_required():
    payload = _a2a_payload()
    payload.update(
        dataset_file="/uploads/a2a.jsonl",
    )
    request = AgentTaskCreateReq(**payload)
    config = request.config_json()
    assert '"dataset_file": "/uploads/a2a.jsonl"' in config

    payload["a2a_scenarios"] = []
    with pytest.raises(ValidationError, match="a2a_scenarios"):
        AgentTaskCreateReq(**payload)


def test_agent_upload_source_requires_jsonl_file():
    payload = _a2a_payload()
    payload.update(
        dataset_file="/uploads/a2a.json",
    )
    with pytest.raises(ValidationError, match=".jsonl"):
        AgentTaskCreateReq(**payload)


def test_validates_every_protocol_jsonl_record(tmp_path, monkeypatch):
    import service.agent_task_service as service

    dataset = tmp_path / "a2a.jsonl"
    dataset.write_text(
        '{"id":"order-1","scenario_id":"message",'
        '"message":{"role":"ROLE_USER","parts":[{"text":"hello"}]}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "UPLOAD_FOLDER", str(tmp_path))
    request = AgentTaskCreateReq(
        **{
            **_a2a_payload(),
            "dataset_file": str(dataset),
        }
    )
    _validate_protocol_dataset(request)


def test_rejects_protocol_jsonl_with_invalid_weight(tmp_path, monkeypatch):
    import service.agent_task_service as service

    dataset = tmp_path / "mcp.jsonl"
    dataset.write_text(
        '{"id":"weather-1","scenario_id":"weather","weight":1,' '"arguments":{}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "UPLOAD_FOLDER", str(tmp_path))
    request = AgentTaskCreateReq(
        name="MCP upload",
        protocol="mcp",
        target_url="https://mcp.example.com/mcp",
        dataset_file=str(dataset),
        mcp_calls=[
            {
                "id": "weather",
                "name": "Weather",
                "tool_name": "get_weather",
                "arguments": {},
            }
        ],
    )
    with pytest.raises(ErrorResponse) as error:
        _validate_protocol_dataset(request)
    assert "dataset line 1" in error.value.error
    assert "weight" in error.value.error


def test_rejects_dataset_row_for_unknown_scenario(tmp_path, monkeypatch):
    import service.agent_task_service as service

    dataset = tmp_path / "a2a.jsonl"
    dataset.write_text(
        '{"id":"row-1","scenario_id":"unknown",'
        '"message":{"role":"ROLE_USER","parts":[{"text":"hello"}]}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "UPLOAD_FOLDER", str(tmp_path))
    request = AgentTaskCreateReq(**{**_a2a_payload(), "dataset_file": str(dataset)})
    with pytest.raises(ErrorResponse) as error:
        _validate_protocol_dataset(request)
    assert "unknown scenario_id" in error.value.error


def test_rerun_name_uses_incrementing_suffix_and_limit():
    assert _next_rerun_name("agent-load") == "agent-load-1"
    assert _next_rerun_name("agent-load-9") == "agent-load-10"
    assert len(_next_rerun_name("x" * 100)) == 100


def test_rerun_copies_dataset_to_independent_task_directory(tmp_path, monkeypatch):
    import service.agent_task_service as service

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "a2a.jsonl"
    source.write_text('{"id":"1"}\n', encoding="utf-8")
    monkeypatch.setattr(service, "UPLOAD_FOLDER", str(tmp_path))

    copied = _copy_dataset_for_rerun({"dataset_file": str(source)}, "new-task")

    assert copied == str(tmp_path / "new-task" / "a2a.jsonl")
    assert (tmp_path / "new-task" / "a2a.jsonl").read_text(encoding="utf-8") == (
        '{"id":"1"}\n'
    )


def _fake_response(
    status_code: int, payload: dict | None = None, *, text: str | None = None
):
    import httpx

    request = httpx.Request("GET", "https://target.example.com")
    if text is not None:
        return httpx.Response(
            status_code,
            headers={"content-type": "text/event-stream"},
            text=text,
            request=request,
        )
    return httpx.Response(status_code, json=payload or {}, request=request)


class _FakeAsyncClient:
    """A minimal httpx.AsyncClient double that serves scripted responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []
        self.gets = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        self.gets.append((url, headers))
        return self._responses.pop(0)

    async def post(self, url, headers=None, json=None):
        self.posts.append((url, headers, json))
        return self._responses.pop(0)


def _a2a_card_payload(target_url: str, *, binding: str = "JSONRPC", tenant=None):
    interface = {
        "protocolVersion": "1.0",
        "protocolBinding": binding,
        "url": target_url,
    }
    if tenant is not None:
        interface["tenant"] = tenant
    return {
        "name": "Echo",
        "description": "echo",
        "version": "1.0",
        "capabilities": {"streaming": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [],
        "supportedInterfaces": [interface],
    }


@pytest.mark.asyncio
async def test_a2a_connection_runs_discovery_then_real_sendmessage(monkeypatch):
    import service.agent_task_service as service

    target = "https://agent.example.com/a2a"
    card = _a2a_card_payload(target)
    send_result = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"status": {"state": "completed"}},
    }
    client = _FakeAsyncClient(
        [_fake_response(200, card), _fake_response(200, send_result)]
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client)

    body = AgentTaskCreateReq(
        name="probe",
        protocol="a2a",
        target_url=target,
        a2a_mode="sync",
        a2a_scenarios=[
            {
                "id": "s1",
                "name": "s1",
                "message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]},
            }
        ],
    )
    result = await run_agent_connection_test(body)

    assert result["status"] == "success"
    assert result["protocol"] == "a2a"
    # The reported HTTP status is the business request, not the card fetch.
    assert result["http_status"] == 200
    assert result["operation"] == "a2a/sendmessage"
    assert result["discovery_operation"] == "agent-card/get"
    assert result["discovery_http_status"] == 200
    assert result["agent_card"]["name"] == "Echo"
    assert result["response"]["status_code"] == 200
    # Discovery GET + one business POST were issued.
    assert len(client.gets) == 1
    assert len(client.posts) == 1
    assert client.posts[0][2]["method"] == "SendMessage"


@pytest.mark.asyncio
async def test_a2a_connection_accepts_http_jsonrpc_binding(monkeypatch):
    import service.agent_task_service as service

    target = "https://agent.example.com/a2a/"
    # Card advertises HTTP+JSONRPC and a trailing slash; configured URL has none.
    card = _a2a_card_payload(target, binding="HTTP+JSONRPC")
    send_result = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"status": {"state": "completed"}},
    }
    client = _FakeAsyncClient(
        [_fake_response(200, card), _fake_response(200, send_result)]
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client)

    body = AgentTaskCreateReq(
        name="probe",
        protocol="a2a",
        target_url="https://agent.example.com/a2a",
        a2a_mode="sync",
        a2a_scenarios=[
            {
                "id": "s1",
                "name": "s1",
                "message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]},
            }
        ],
    )
    result = await run_agent_connection_test(body)

    assert result["status"] == "success"
    assert result["operation"] == "a2a/sendmessage"


@pytest.mark.asyncio
async def test_a2a_connection_accepts_http_json_binding(monkeypatch):
    import service.agent_task_service as service

    target = "https://agent.example.com/a2a/"
    card = _a2a_card_payload(target, binding="HTTP+JSON")
    send_result = {"status": {"state": "completed"}}
    client = _FakeAsyncClient(
        [_fake_response(200, card), _fake_response(200, send_result)]
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client)

    body = AgentTaskCreateReq(
        name="probe",
        protocol="a2a",
        target_url="https://agent.example.com/a2a",
        a2a_binding="http_json",
        a2a_mode="sync",
        a2a_scenarios=[
            {
                "id": "s1",
                "name": "s1",
                "message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]},
            }
        ],
    )
    result = await run_agent_connection_test(body)

    assert result["status"] == "success"
    assert result["operation"] == "a2a/rest/message:send"


def test_a2a_binding_field_in_config_json():
    body = AgentTaskCreateReq(
        name="probe",
        protocol="a2a",
        target_url="https://agent.example.com/a2a",
        a2a_binding="http_json",
        a2a_scenarios=[
            {
                "id": "s1",
                "name": "s1",
                "message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]},
            }
        ],
    )
    import json

    config = json.loads(body.config_json())
    assert config["a2a_binding"] == "http_json"


def test_grpc_binding_rejects_http_url():
    import pytest as _pt

    with _pt.raises(Exception, match="gRPC target_url must be host:port"):
        AgentTaskCreateReq(
            name="probe",
            protocol="a2a",
            target_url="https://grpc.example.com:443",
            a2a_binding="grpc",
            a2a_scenarios=[
                {
                    "id": "s1",
                    "name": "s1",
                    "message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]},
                }
            ],
        )


def test_grpc_binding_accepts_host_port():
    body = AgentTaskCreateReq(
        name="probe",
        protocol="a2a",
        target_url="grpc.example.com:443",
        a2a_binding="grpc",
        a2a_scenarios=[
            {
                "id": "s1",
                "name": "s1",
                "message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]},
            }
        ],
    )
    assert body.a2a_binding == "grpc"


@pytest.mark.asyncio
async def test_a2a_connection_reports_business_request_401(monkeypatch):
    import service.agent_task_service as service

    target = "https://agent.example.com/a2a"
    card = _a2a_card_payload(target)
    client = _FakeAsyncClient(
        [
            _fake_response(200, card),
            _fake_response(401, {"error": "invalid credentials"}),
        ]
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client)

    body = AgentTaskCreateReq(
        name="probe",
        protocol="a2a",
        target_url=target,
        a2a_scenarios=[
            {
                "id": "s1",
                "name": "s1",
                "message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]},
            }
        ],
    )
    result = await run_agent_connection_test(body)

    # The card fetch succeeded (discovery), but the real SendMessage returned 401.
    assert result["status"] == "error"
    assert result["error_type"] == "http_error"
    assert result["http_status"] == 401
    assert result["operation"] == "a2a/sendmessage"
    assert result["response"]["status_code"] == 401
    assert result["response"]["data"] == {"error": "invalid credentials"}


@pytest.mark.asyncio
async def test_mcp_stateless_connection_runs_discovery_then_real_tools_call(
    monkeypatch,
):
    import service.agent_task_service as service

    target = "https://mcp.example.com/mcp"
    tools_list = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "resultType": "complete",
            "tools": [{"name": "get_weather", "inputSchema": {}}],
        },
    }
    call_result = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"resultType": "complete", "content": []},
    }
    client = _FakeAsyncClient(
        [_fake_response(200, tools_list), _fake_response(200, call_result)]
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client)

    body = AgentTaskCreateReq(
        name="probe",
        protocol="mcp",
        protocol_version="2026-07-28",
        target_url=target,
        mcp_calls=[
            {"id": "w", "name": "w", "tool_name": "get_weather", "arguments": {}}
        ],
    )
    result = await run_agent_connection_test(body)

    assert result["status"] == "success"
    assert result["protocol"] == "mcp"
    assert result["http_status"] == 200
    assert result["operation"] == "mcp/tools-call"
    assert result["discovery_operation"] == "tools/list"
    assert result["tools"][0]["name"] == "get_weather"
    assert result["response"]["status_code"] == 200
    assert len(client.posts) == 2
    assert client.posts[0][2]["method"] == "tools/list"
    assert client.posts[1][2]["method"] == "tools/call"
    # The business probe carries the stateless MCP routing headers.
    assert client.posts[1][1]["Mcp-Method"] == "tools/call"
    assert client.posts[1][1]["Mcp-Name"] == "get_weather"
