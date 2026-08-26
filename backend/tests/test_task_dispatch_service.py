"""Tests for the shared regular-task dispatch projection."""

import sys
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from model.http_task import HttpTask, HttpTaskCreateReq
from model.llm_task import Task, TaskCreateReq
from model.task_dispatch_queue import TaskDispatchQueue
from service.task_dispatch_service import add_dispatch_entry, cancel_dispatch_entry


def test_add_dispatch_entry_uses_business_task_transaction():
    db = Mock()

    entry = add_dispatch_entry(
        db,
        task_type="http",
        task_id="http-001",
        cluster_id="gpu-prod",
    )

    db.add.assert_called_once_with(entry)
    assert entry.task_type == "http"
    assert entry.task_id == "http-001"
    assert entry.cluster_id == "gpu-prod"
    assert entry.status == "created"


def _request_with_db():
    request = MagicMock()
    request.state.user = {"username": "tester"}
    request.state.db = AsyncMock()
    request.state.db.add = Mock()
    request.state.db.flush = AsyncMock()
    request.state.db.commit = AsyncMock()
    request.state.db.rollback = AsyncMock()
    return request


@pytest.mark.asyncio
async def test_llm_creation_adds_dispatch_entry_in_same_transaction(monkeypatch):
    monkeypatch.setitem(sys.modules, "jwt", MagicMock())
    from service import llm_task_service

    monkeypatch.setattr(llm_task_service.settings, "LDAP_ENABLED", False)
    monkeypatch.setattr(
        llm_task_service, "_get_cert_config", Mock(return_value=(None, None))
    )
    request = _request_with_db()
    body = TaskCreateReq(
        temp_task_id="temp-llm",
        name="LLM task",
        target_host="https://api.example.com",
        concurrent_users=1,
        spawn_rate=1,
    )

    await llm_task_service.create_task_svc(request, body)

    added = [call.args[0] for call in request.state.db.add.call_args_list]
    assert any(isinstance(item, Task) for item in added)
    queue_entry = next(item for item in added if isinstance(item, TaskDispatchQueue))
    assert queue_entry.task_type == "llm"
    assert queue_entry.cluster_id == "local"
    request.state.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_http_creation_adds_dispatch_entry_in_same_transaction(monkeypatch):
    monkeypatch.setitem(sys.modules, "jwt", MagicMock())
    from service import http_task_service

    monkeypatch.setattr(http_task_service.settings, "LDAP_ENABLED", False)
    request = _request_with_db()
    body = HttpTaskCreateReq(
        temp_task_id="temp-http",
        name="HTTP task",
        method="GET",
        target_url="https://api.example.com/health",
        concurrent_users=1,
    )

    await http_task_service.create_http_task_svc(request, body)

    added = [call.args[0] for call in request.state.db.add.call_args_list]
    assert any(isinstance(item, HttpTask) for item in added)
    queue_entry = next(item for item in added if isinstance(item, TaskDispatchQueue))
    assert queue_entry.task_type == "http"
    assert queue_entry.cluster_id == "local"
    request.state.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_dispatch_entry_only_cancels_unclaimed_rows():
    db = AsyncMock()

    await cancel_dispatch_entry(db, task_type="llm", task_id="llm-001")

    statement = db.execute.await_args.args[0]
    sql = str(statement)
    assert "UPDATE task_dispatch_queue" in sql
    assert "task_dispatch_queue.task_type" in sql
    assert "task_dispatch_queue.task_id" in sql
    assert "task_dispatch_queue.status IN" in sql


@pytest.mark.asyncio
async def test_scheduler_only_activates_entries_for_queuing_tasks(monkeypatch):
    from service import scheduler

    session = AsyncMock()
    llm_update_result = MagicMock(rowcount=1)
    http_update_result = MagicMock(rowcount=1)
    queue_update_result = MagicMock(rowcount=1)
    session.execute = AsyncMock(
        side_effect=[
            llm_update_result,
            queue_update_result,
            http_update_result,
            queue_update_result,
        ]
    )

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(
        scheduler, "async_session_factory", Mock(return_value=SessionContext())
    )

    await scheduler._enqueue_created_tasks()

    session.commit.assert_awaited_once()
    assert session.execute.await_count == 4

    llm_queue_update = str(session.execute.await_args_list[1].args[0])
    http_queue_update = str(session.execute.await_args_list[3].args[0])
    assert "SELECT llm_tasks.id" in llm_queue_update
    assert "llm_tasks.status" in llm_queue_update
    assert "SELECT http_tasks.id" in http_queue_update
    assert "http_tasks.status" in http_queue_update
