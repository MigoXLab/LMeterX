from datetime import datetime
from types import SimpleNamespace


def _fake_record(extra=None):
    return {
        "level": SimpleNamespace(name="INFO"),
        "message": "backend log",
        "time": datetime(2026, 7, 23, 10, 30, 1, 123000),
        "file": SimpleNamespace(name="logger.py"),
        "line": 42,
        "function": "test_func",
        "module": "test_module",
        "process": SimpleNamespace(id=123),
        "thread": SimpleNamespace(id=456),
        "extra": extra or {},
    }


def test_backend_sls_log_sink_uses_shared_fields_without_engine_identity(monkeypatch):
    from utils import sls_log_sink

    monkeypatch.setattr(
        sls_log_sink,
        "get_sls_settings",
        lambda: SimpleNamespace(
            SLS_ENABLED=False,
            SLS_ENDPOINT="",
            SLS_PROJECT="",
            SLS_LOGSTORE="",
            SLS_ACCESS_KEY_ID="",
            SLS_ACCESS_KEY_SECRET="",
            SLS_TOPIC="lmeterx",
            SLS_SOURCE="",
            SLS_BATCH_SIZE=100,
            SLS_FLUSH_INTERVAL=2,
            SLS_QUEUE_SIZE=10000,
        ),
    )

    sink = sls_log_sink.SLSLogSink("backend")
    log = sink._record_to_log(_fake_record({"task_id": "task-1", "empty": None}))

    assert log["service"] == "backend"
    assert log["task_id"] == "task-1"
    assert "empty" not in log
    assert "engine_id" not in log
    assert "cluster_id" not in log
