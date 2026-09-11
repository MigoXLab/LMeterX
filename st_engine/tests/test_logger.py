import importlib
import io
import json
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

from utils.logger import (
    SUBPROCESS_LOG_PROTOCOL,
    SUBPROCESS_LOG_PROTOCOL_ENV,
    _LoggingJsonLineFormatter,
    _LoguruJsonLineSink,
    cleanup_subprocess_log_transport,
    enable_subprocess_log_transport,
    forward_subprocess_log_line,
    parse_subprocess_log_event,
    parse_subprocess_log_line,
    setup_clean_log_format,
)

logger_module = importlib.import_module("utils.logger")


def test_parse_subprocess_log_line_removes_structured_prefix():
    level, message = parse_subprocess_log_line(
        "2026-07-23 14:35:00.998 | DEBUG    | Loaded task configuration: {}"
    )

    assert level == "DEBUG"
    assert message == "Loaded task configuration: {}"


def test_parse_subprocess_log_line_removes_locust_prefix():
    level, message = parse_subprocess_log_line(
        "[2026-07-23 14:35:00,968] " "engine/INFO/locust.main: Starting Locust 2.37.4"
    )

    assert level == "INFO"
    assert message == "Starting Locust 2.37.4"


def test_parse_subprocess_log_line_preserves_unstructured_output():
    level, message = parse_subprocess_log_line(
        "RequestsDependencyWarning: unsupported dependency",
        default_level="WARNING",
    )

    assert level == "WARNING"
    assert message == "RequestsDependencyWarning: unsupported dependency"


def test_parse_subprocess_log_line_maps_fatal_to_loguru_critical():
    level, message = parse_subprocess_log_line(
        "2026-07-23 14:35:00.998 | FATAL    | worker crashed"
    )

    assert level == "CRITICAL"
    assert message == "worker crashed"


def _transport_payload(message, level="INFO", **overrides):
    payload = {
        "protocol": SUBPROCESS_LOG_PROTOCOL,
        "level": level,
        "message": message,
        "logger": "locust.stats_logger",
        "time": "2026-08-03T14:07:41.440",
        "file": "stats.py",
        "line": 789,
        "function": "print_stats",
        "process": 123,
        "thread": 456,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def test_parse_jsonl_event_preserves_multiline_message_and_metadata():
    table = "Error report\n# occurrences      Error\n-----------------------\n3                  timeout"

    event = parse_subprocess_log_event(_transport_payload(table, "ERROR"))

    assert event is not None
    assert event.transported is True
    assert event.level == "ERROR"
    assert event.message == table
    assert event.extra == {
        "child_logger": "locust.stats_logger",
        "child_time": "2026-08-03T14:07:41.440",
        "child_file": "stats.py",
        "child_line": 789,
        "child_function": "print_stats",
        "child_process": 123,
        "child_thread": 456,
        "log_protocol": SUBPROCESS_LOG_PROTOCOL,
    }


def test_forward_jsonl_event_emits_exactly_one_parent_log_record():
    table = "Type Name # reqs\n----|----|------\nGET /health 10\nAggregated 10"
    task_logger = Mock()
    bound_logger = Mock()
    task_logger.bind.return_value = bound_logger

    event = forward_subprocess_log_line(
        task_logger, _transport_payload(table), stream="stderr"
    )

    assert event is not None
    task_logger.bind.assert_called_once()
    bound_extra = task_logger.bind.call_args.kwargs
    assert bound_extra["subprocess_stream"] == "stderr"
    assert bound_extra["child_logger"] == "locust.stats_logger"
    assert bound_extra["log_protocol"] == SUBPROCESS_LOG_PROTOCOL
    bound_logger.log.assert_called_once_with("INFO", table)


def test_invalid_or_unrelated_json_remains_plain_child_output():
    raw = '{"message":"application payload, not a transport event"}'

    event = parse_subprocess_log_event(raw, default_level="WARNING")

    assert event is not None
    assert event.transported is False
    assert event.level == "WARNING"
    assert event.message == raw


def test_stdlib_formatter_encodes_multiline_record_as_one_physical_line():
    table = "Response time percentiles\nType Name 50% 95%\nGET /v1 20 80"
    record = logging.LogRecord(
        name="locust.stats_logger",
        level=logging.INFO,
        pathname="/opt/locust/stats.py",
        lineno=100,
        msg=table,
        args=(),
        exc_info=None,
    )

    encoded = _LoggingJsonLineFormatter().format(record)
    event = parse_subprocess_log_event(encoded)

    assert "\n" not in encoded
    assert event is not None
    assert event.message == table
    assert event.extra["child_logger"] == "locust.stats_logger"
    assert event.extra["child_file"] == "stats.py"


def test_stdlib_formatter_keeps_traceback_in_same_event():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = __import__("sys").exc_info()

    record = logging.LogRecord(
        name="locust.user",
        level=logging.ERROR,
        pathname="/opt/locust/user.py",
        lineno=55,
        msg="request failed",
        args=(),
        exc_info=exc_info,
    )

    encoded = _LoggingJsonLineFormatter().format(record)
    event = parse_subprocess_log_event(encoded)

    assert "\n" not in encoded
    assert event is not None
    assert event.message.startswith("request failed\nTraceback")
    assert "RuntimeError: boom" in event.message


def test_loguru_sink_encodes_multiline_record_as_one_physical_line(monkeypatch):
    monkeypatch.setattr(logger_module, "fcntl", None)
    stream = io.StringIO()
    sink = _LoguruJsonLineSink(stream)
    table = "Error report\n# occurrences Error\n1 timeout"

    class FakeMessage:
        record = {
            "level": SimpleNamespace(name="WARNING"),
            "name": "engine.llm_locustfile",
            "time": datetime(2026, 8, 3, 14, 7, 41),
            "file": SimpleNamespace(name="llm_locustfile.py"),
            "line": 350,
            "function": "on_locust_init",
            "process": SimpleNamespace(id=321),
            "thread": SimpleNamespace(id=654),
        }

        def __str__(self):
            return f"{table}\n"

    sink(FakeMessage())

    physical_lines = stream.getvalue().splitlines()
    assert len(physical_lines) == 1
    event = parse_subprocess_log_event(physical_lines[0])
    assert event is not None
    assert event.level == "WARNING"
    assert event.message == table


def test_enable_subprocess_log_transport_sets_versioned_protocol():
    env = {}

    enable_subprocess_log_transport(env)

    assert env[SUBPROCESS_LOG_PROTOCOL_ENV] == SUBPROCESS_LOG_PROTOCOL


def test_setup_clean_log_format_enables_jsonl_for_stdlib_handlers(monkeypatch):
    monkeypatch.setenv(SUBPROCESS_LOG_PROTOCOL_ENV, SUBPROCESS_LOG_PROTOCOL)
    monkeypatch.setattr(logger_module, "fcntl", None)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers = [handler]

    try:
        setup_clean_log_format()
        record = logging.LogRecord(
            name="locust.stats_logger",
            level=logging.INFO,
            pathname="/opt/locust/stats.py",
            lineno=100,
            msg="header\nrow one\nrow two",
            args=(),
            exc_info=None,
        )
        handler.handle(record)
    finally:
        root_logger.handlers = original_handlers

    physical_lines = stream.getvalue().splitlines()
    assert len(physical_lines) == 1
    event = parse_subprocess_log_event(physical_lines[0])
    assert event is not None
    assert event.message == "header\nrow one\nrow two"


def test_cleanup_subprocess_log_transport_removes_task_lock(tmp_path, monkeypatch):
    lock_file = tmp_path / "task.lock"
    lock_file.write_text("")
    monkeypatch.setattr(
        logger_module, "_subprocess_log_lock_path", lambda _task_id: str(lock_file)
    )

    cleanup_subprocess_log_transport("task-1")
    cleanup_subprocess_log_transport("task-1")

    assert not lock_file.exists()
