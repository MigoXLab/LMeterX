import sys
import types
from types import SimpleNamespace

import pytest

from model.log import SLSLogEntry, SLSLogResponse
from utils.error_handler import ErrorResponse


class FakeGetLogsRequest:
    def __init__(self, *args):
        """Store request arguments for assertions."""
        self.args = args


class FakeLogItem:
    def __init__(self, contents, timestamp=100):
        """Create a fake Aliyun log item."""
        self._contents = contents
        self._timestamp = timestamp

    def get_contents(self):
        return self._contents

    def get_time(self):
        return self._timestamp


class FakeLogResponse:
    def __init__(self, logs):
        """Create a fake Aliyun log response."""
        self._logs = logs

    def get_logs(self):
        return self._logs


def fake_sls_settings():
    return SimpleNamespace(
        SLS_ENABLED=True,
        SLS_ENDPOINT="cn-shanghai.log.aliyuncs.com",
        SLS_PROJECT="lmeterx-log",
        SLS_LOGSTORE="lmeterx-log",
        SLS_ACCESS_KEY_ID="ak",
        SLS_ACCESS_KEY_SECRET="sk",
        is_configured=True,
    )


@pytest.fixture
def fake_aliyun_log(monkeypatch):
    aliyun_module = types.ModuleType("aliyun")
    log_module = types.ModuleType("aliyun.log")
    log_module.GetLogsRequest = FakeGetLogsRequest
    monkeypatch.setitem(sys.modules, "aliyun", aliyun_module)
    monkeypatch.setitem(sys.modules, "aliyun.log", log_module)


@pytest.mark.asyncio
async def test_query_sls_logs_builds_indexed_query_and_reverse(
    fake_aliyun_log, monkeypatch
):
    from service import sls_log_service

    captured = {}

    class FakeClient:
        def get_logs(self, request):
            captured["request"] = request
            return FakeLogResponse(
                [
                    FakeLogItem(
                        {
                            "service": "engine",
                            "engine_id": "engine-local",
                            "cluster_id": "local",
                            "level": "INFO",
                            "message": "hello",
                        },
                        timestamp=123,
                    )
                ]
            )

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    response = await sls_log_service.query_sls_logs_svc(
        service="engine",
        engine_id="engine-local",
        cluster_id="local",
        start_time=10,
        end_time=20,
        limit=100,
        offset=7,
        reverse=True,
    )

    request_args = captured["request"].args
    assert request_args[0:4] == (
        "lmeterx-log",
        "lmeterx-log",
        10,
        20,
    )
    assert request_args[5] == (
        'service: "engine" and engine_id: "engine-local" and cluster_id: "local"'
    )
    assert request_args[6:9] == (100, 7, True)
    assert response.logs[0].message == "hello"
    assert response.next_cursor == 124
    assert response.next_offset == 0


@pytest.mark.asyncio
async def test_query_sls_logs_can_exclude_task_logs(fake_aliyun_log, monkeypatch):
    from service import sls_log_service

    captured = {}

    class FakeClient:
        def get_logs(self, request):
            captured["request"] = request
            return FakeLogResponse(
                [
                    FakeLogItem(
                        {
                            "service": "engine",
                            "engine_id": "engine-local",
                            "cluster_id": "local",
                            "level": "INFO",
                            "message": "system log",
                        },
                        timestamp=123,
                    ),
                    FakeLogItem(
                        {
                            "service": "engine",
                            "task_id": "task-1",
                            "engine_id": "engine-local",
                            "cluster_id": "local",
                            "level": "DEBUG",
                            "message": "Request Payload: {}",
                        },
                        timestamp=124,
                    ),
                ]
            )

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    response = await sls_log_service.query_sls_logs_svc(
        service="engine",
        engine_id="engine-local",
        cluster_id="local",
        exclude_task_logs=True,
        start_time=10,
        end_time=20,
        limit=100,
    )

    assert captured["request"].args[5] == (
        'service: "engine" and engine_id: "engine-local" '
        'and cluster_id: "local" and not task_id: *'
    )
    assert [entry.message for entry in response.logs] == ["system log"]


@pytest.mark.asyncio
async def test_query_sls_logs_sorts_by_precise_raw_time(fake_aliyun_log, monkeypatch):
    from service import sls_log_service

    class FakeClient:
        def get_logs(self, request):
            return FakeLogResponse(
                [
                    FakeLogItem(
                        {
                            "level": "INFO",
                            "message": "third",
                            "time": "2026-07-23T10:49:33.104790+08:00",
                        },
                        timestamp=100,
                    ),
                    FakeLogItem(
                        {
                            "level": "INFO",
                            "message": "first",
                            "time": "2026-07-23T10:49:33.104705+08:00",
                        },
                        timestamp=100,
                    ),
                    FakeLogItem(
                        {
                            "level": "INFO",
                            "message": "second",
                            "time": "2026-07-23T10:49:33.104714+08:00",
                        },
                        timestamp=100,
                    ),
                ]
            )

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    response = await sls_log_service.query_sls_logs_svc(
        task_id="task-1",
        start_time=10,
        end_time=20,
        limit=100,
        reverse=True,
    )

    assert [entry.message for entry in response.logs] == [
        "first",
        "second",
        "third",
    ]
    assert [entry.raw["time"] for entry in response.logs] == [
        "2026-07-23 10:49:33.104705",
        "2026-07-23 10:49:33.104714",
        "2026-07-23 10:49:33.104790",
    ]


@pytest.mark.asyncio
async def test_query_sls_logs_formats_fallback_timestamp(fake_aliyun_log, monkeypatch):
    from service import sls_log_service

    class FakeClient:
        def get_logs(self, request):
            return FakeLogResponse(
                [
                    FakeLogItem(
                        {
                            "level": "INFO",
                            "message": "fallback timestamp",
                        },
                        timestamp=1784787243,
                    )
                ]
            )

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    response = await sls_log_service.query_sls_logs_svc(
        task_id="task-1",
        start_time=10,
        end_time=20,
        limit=100,
    )

    assert response.logs[0].raw["time"].endswith(".000000")
    assert "T" not in response.logs[0].raw["time"]


@pytest.mark.asyncio
async def test_query_sls_logs_normalizes_and_deduplicates_forwarded_child_logs(
    fake_aliyun_log, monkeypatch
):
    from service import sls_log_service

    class FakeClient:
        def get_logs(self, request):
            return FakeLogResponse(
                [
                    FakeLogItem(
                        {
                            "service": "engine",
                            "task_id": "task-1",
                            "engine_id": "engine-local",
                            "cluster_id": "local",
                            "level": "DEBUG",
                            "message": (
                                "2026-07-23 14:35:00.998 | DEBUG    | "
                                "Loaded task configuration: {'task_id': 'task-1'}"
                            ),
                            "time": "2026-07-23 14:35:00.998",
                        },
                        timestamp=100,
                    ),
                    FakeLogItem(
                        {
                            "service": "engine",
                            "task_id": "task-1",
                            "engine_id": "engine-local",
                            "cluster_id": "local",
                            "level": "DEBUG",
                            "message": (
                                "Loaded task configuration: {'task_id': 'task-1'}"
                            ),
                            "time": "2026-07-23 14:35:00.999",
                        },
                        timestamp=100,
                    ),
                ]
            )

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    response = await sls_log_service.query_sls_logs_svc(
        task_id="task-1",
        start_time=10,
        end_time=20,
        limit=100,
    )

    assert len(response.logs) == 1
    assert response.logs[0].message == (
        "Loaded task configuration: {'task_id': 'task-1'}"
    )
    assert response.logs[0].raw["message"] == response.logs[0].message


@pytest.mark.asyncio
async def test_query_sls_logs_normalizes_locust_prefix(fake_aliyun_log, monkeypatch):
    from service import sls_log_service

    class FakeClient:
        def get_logs(self, request):
            return FakeLogResponse(
                [
                    FakeLogItem(
                        {
                            "level": "INFO",
                            "message": (
                                "[2026-07-23 14:35:00,968] "
                                "engine/INFO/locust.main: Starting Locust 2.37.4"
                            ),
                            "time": "2026-07-23 14:35:00.969",
                        },
                        timestamp=100,
                    )
                ]
            )

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    response = await sls_log_service.query_sls_logs_svc(
        task_id="task-1",
        start_time=10,
        end_time=20,
    )

    assert response.logs[0].message == "Starting Locust 2.37.4"


@pytest.mark.asyncio
async def test_query_sls_logs_reports_missing_index(fake_aliyun_log, monkeypatch):
    from service import sls_log_service

    class FakeSlsError(Exception):
        def get_error_code(self):
            return "IndexConfigNotExist"

        def get_error_message(self):
            return "logstore without index config"

        def get_request_id(self):
            return "request-1"

    class FakeClient:
        def get_logs(self, request):
            raise FakeSlsError()

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    with pytest.raises(ErrorResponse) as exc_info:
        await sls_log_service.query_sls_logs_svc(service="engine")

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "sls_index_not_configured"


@pytest.mark.asyncio
async def test_query_sls_logs_reports_transient_network_error(
    fake_aliyun_log, monkeypatch
):
    from service import sls_log_service

    class FakeSlsError(Exception):
        def get_error_code(self):
            return "LogRequestError"

        def get_error_message(self):
            return (
                "HTTPSConnectionPool(host='lmeterx-log.cn-shanghai.log.aliyuncs.com', "
                "port=443): Failed to resolve"
            )

        def get_request_id(self):
            return ""

    class FakeClient:
        def get_logs(self, request):
            raise FakeSlsError()

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    with pytest.raises(ErrorResponse) as exc_info:
        await sls_log_service.query_sls_logs_svc(service="engine")

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "sls_temporarily_unavailable"


@pytest.mark.asyncio
async def test_query_sls_logs_advances_cursor_when_empty(fake_aliyun_log, monkeypatch):
    from service import sls_log_service

    class FakeClient:
        def get_logs(self, request):
            return FakeLogResponse([])

    monkeypatch.setattr(
        sls_log_service,
        "get_sls_settings",
        fake_sls_settings,
    )
    monkeypatch.setattr(sls_log_service, "_client", lambda settings: FakeClient())

    response = await sls_log_service.query_sls_logs_svc(
        service="engine",
        start_time=10,
        end_time=100,
    )

    assert response.logs == []
    assert response.next_cursor == 95


@pytest.mark.asyncio
async def test_engine_log_endpoint_falls_back_without_cluster(monkeypatch):
    from api import api_log

    calls = []

    async def fake_query_sls_logs_svc(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return SLSLogResponse(logs=[], next_cursor=10, has_more=False)
        return SLSLogResponse(
            logs=[
                SLSLogEntry(
                    timestamp=11,
                    service="engine",
                    engine_id="engine-local",
                    message="legacy log",
                )
            ],
            next_cursor=12,
            has_more=False,
        )

    monkeypatch.setattr(api_log, "query_sls_logs_svc", fake_query_sls_logs_svc)

    response = await api_log.query_sls_engine_log(
        engine_id="engine-local",
        cluster_id="local",
        start_time=1,
        end_time=2,
        limit=100,
    )

    assert response.logs[0].message == "legacy log"
    assert calls[0]["cluster_id"] == "local"
    assert calls[0]["exclude_task_logs"] is True
    assert "cluster_id" not in calls[1]
    assert calls[1]["exclude_task_logs"] is True
