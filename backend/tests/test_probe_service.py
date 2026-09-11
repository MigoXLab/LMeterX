"""Probe result waiting and timeout diagnostics tests."""

from types import SimpleNamespace

import pytest

from service import probe_service


class _SessionContext:
    def __init__(self, probe):
        self.probe = probe

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, probe_id):
        return self.probe


@pytest.mark.asyncio
async def test_wait_returns_completed_result_without_initial_sleep(monkeypatch):
    expected = {"status": "success", "response": {"status_code": 200}}
    probe = SimpleNamespace(status="completed", result=expected, engine_id="engine-1")
    sleep_calls = []

    monkeypatch.setattr(
        probe_service, "async_session_factory", lambda: _SessionContext(probe)
    )

    async def record_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(probe_service.asyncio, "sleep", record_sleep)

    result = await probe_service.wait_for_probe_result("probe-1", timeout=1)

    assert result == expected
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_wait_explains_claimed_probe_timeout(monkeypatch):
    probe = SimpleNamespace(status="claimed", result=None, engine_id="engine-cloud-1")
    monkeypatch.setattr(
        probe_service, "async_session_factory", lambda: _SessionContext(probe)
    )

    result = await probe_service.wait_for_probe_result("probe-2", timeout=0)

    assert result["status"] == "error"
    assert "engine-cloud-1 claimed" in result["error"]
    assert "target API may be responding slowly" in result["error"]


@pytest.mark.asyncio
async def test_wait_explains_unclaimed_probe_timeout(monkeypatch):
    probe = SimpleNamespace(status="pending", result=None, engine_id=None)
    monkeypatch.setattr(
        probe_service, "async_session_factory", lambda: _SessionContext(probe)
    )

    result = await probe_service.wait_for_probe_result("probe-3", timeout=0)

    assert result["status"] == "error"
    assert "No engine in the selected cluster claimed" in result["error"]
    assert "engine registration and health" in result["error"]


@pytest.mark.asyncio
async def test_wait_handles_empty_completed_result(monkeypatch):
    probe = SimpleNamespace(status="completed", result=None, engine_id="engine-1")
    monkeypatch.setattr(
        probe_service, "async_session_factory", lambda: _SessionContext(probe)
    )

    result = await probe_service.wait_for_probe_result("probe-4", timeout=1)

    assert result == {
        "status": "error",
        "error": "The engine returned an empty probe result.",
        "response": None,
    }
