import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from model.http_task import HttpTaskCreateReq
from model.llm_task import TaskCreateReq
from service import http_task_service, llm_task_service


@pytest.mark.asyncio
async def test_llm_copy_restores_original_headers_and_applies_overrides(monkeypatch):
    monkeypatch.setattr(llm_task_service.settings, "LDAP_ENABLED", False)
    source = SimpleNamespace(
        id="source",
        is_deleted=0,
        target_host="https://api.example",
        api_path="/v1/chat/completions",
        headers=json.dumps({"Authorization": "Bearer original", "X-Trace": "original"}),
        created_by="-",
    )
    request = SimpleNamespace(
        state=SimpleNamespace(db=SimpleNamespace(get=AsyncMock(return_value=source)))
    )
    body = TaskCreateReq(
        temp_task_id="temp",
        name="copy",
        target_host=source.target_host,
        api_path=source.api_path,
        concurrent_users=1,
        spawn_rate=1,
        headers=[{"key": "X-Trace", "value": "replacement"}],
        copy_source_task_id=source.id,
        inherit_source_headers=True,
    )

    assert await llm_task_service._resolved_copy_headers(request, body) == {
        "Authorization": "Bearer original",
        "X-Trace": "replacement",
    }


@pytest.mark.asyncio
async def test_http_copy_restores_original_headers(monkeypatch):
    monkeypatch.setattr(http_task_service.settings, "LDAP_ENABLED", False)
    source = SimpleNamespace(
        id="source",
        is_deleted=0,
        target_url="https://api.example/orders",
        method="POST",
        headers=json.dumps({"X-Api-Key": "original"}),
        created_by="-",
    )
    request = SimpleNamespace(
        state=SimpleNamespace(db=SimpleNamespace(get=AsyncMock(return_value=source)))
    )
    body = HttpTaskCreateReq(
        temp_task_id="temp",
        name="copy",
        method=source.method,
        target_url=source.target_url,
        concurrent_users=1,
        headers=[],
        copy_source_task_id=source.id,
        inherit_source_headers=True,
    )

    assert await http_task_service._resolved_copy_headers(request, body) == {
        "X-Api-Key": "original"
    }
