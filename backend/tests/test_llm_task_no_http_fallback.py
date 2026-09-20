"""Tests verifying LLM task lookups no longer fall back to http_tasks.

The shared log/detail pages resolve task kind on the frontend via
``unifiedTaskApi`` (probe by 404). For that probe to work, the LLM endpoints
must return 404 for IDs that only exist in ``http_tasks`` instead of silently
serving them via a cross-table fallback.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.error_handler import ErrorResponse


def _request_with_db(db: AsyncMock) -> MagicMock:
    request = MagicMock()
    request.state.db = db
    return request


def _no_rows_result():
    result = MagicMock()
    result.first.return_value = None
    return result


@pytest.mark.asyncio
async def test_get_task_status_returns_404_without_querying_http_tasks(monkeypatch):
    """Status endpoint must not touch http_tasks when llm_tasks misses."""
    monkeypatch.setitem(sys.modules, "jwt", MagicMock())
    from service import llm_task_service

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_no_rows_result())

    request = _request_with_db(db)

    with pytest.raises(ErrorResponse) as exc_info:
        await llm_task_service.get_task_status_svc(request, "missing-id")

    assert exc_info.value.status_code == 404
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_task_returns_404_without_querying_http_tasks(monkeypatch):
    """Detail endpoint must not touch http_tasks when llm_tasks misses."""
    monkeypatch.setitem(sys.modules, "jwt", MagicMock())
    from service import llm_task_service

    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    request = _request_with_db(db)

    with pytest.raises(ErrorResponse) as exc_info:
        await llm_task_service.get_task_svc(request, "missing-id")

    assert exc_info.value.status_code == 404
    db.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_get_task_status_returns_404_without_querying_http_tasks(
    monkeypatch,
):
    """Legacy /api/tasks status endpoint must also stop falling back."""
    monkeypatch.setitem(sys.modules, "jwt", MagicMock())
    from service import task_service

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_no_rows_result())

    request = _request_with_db(db)

    with pytest.raises(ErrorResponse) as exc_info:
        await task_service.get_task_status_svc(request, "missing-id")

    assert exc_info.value.status_code == 404
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_get_task_returns_404_without_querying_http_tasks(monkeypatch):
    """Legacy /api/tasks detail endpoint must also stop falling back."""
    monkeypatch.setitem(sys.modules, "jwt", MagicMock())
    from service import task_service

    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    request = _request_with_db(db)

    with pytest.raises(ErrorResponse) as exc_info:
        await task_service.get_task_svc(request, "missing-id")

    assert exc_info.value.status_code == 404
    db.get.assert_awaited_once()
