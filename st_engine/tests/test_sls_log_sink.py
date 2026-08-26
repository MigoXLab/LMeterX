from datetime import datetime
from types import SimpleNamespace


def _fake_record(extra=None):
    return {
        "level": SimpleNamespace(name="INFO"),
        "message": "engine log",
        "time": datetime(2026, 7, 23, 10, 30, 1, 123000),
        "file": SimpleNamespace(name="logger.py"),
        "line": 42,
        "function": "test_func",
        "module": "test_module",
        "process": SimpleNamespace(id=123),
        "thread": SimpleNamespace(id=456),
        "extra": extra or {},
    }


def test_engine_sls_log_sink_injects_engine_identity(monkeypatch):
    monkeypatch.setenv("SLS_ENABLED", "false")

    from utils import sls_log_sink

    monkeypatch.setattr(sls_log_sink, "resolve_engine_id", lambda: "engine-1")
    monkeypatch.setattr(sls_log_sink, "resolve_cluster_id", lambda: "cluster-a")

    sink = sls_log_sink.SLSLogSink("engine")
    log = sink._record_to_log(_fake_record({"task_id": "task-1"}))

    assert log["service"] == "engine"
    assert log["engine_id"] == "engine-1"
    assert log["cluster_id"] == "cluster-a"
    assert log["task_id"] == "task-1"


def test_engine_sls_log_sink_preserves_multiline_message_as_one_field(monkeypatch):
    monkeypatch.setenv("SLS_ENABLED", "false")

    from utils import sls_log_sink

    table = "Type Name # reqs\n----|----|------\nGET /health 10\nAggregated 10"
    record = _fake_record({"task_id": "task-table"})
    record["message"] = table

    sink = sls_log_sink.SLSLogSink("engine")
    log = sink._record_to_log(record)

    assert log["message"] == table
    assert log["task_id"] == "task-table"
    assert log["time"] == "2026-07-23 10:30:01.123000"
