"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Tuple, Union

from dotenv import load_dotenv
from loguru import logger

from config.base import LOG_DIR, LOG_TASK_DIR
from utils.engine_identity import resolve_engine_id
from utils.sls_log_sink import SLSLogSink
from utils.sls_settings import get_sls_settings

ENGINE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ENGINE_DIR / ".env")
# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENGINE_ID = resolve_engine_id()
# Get detail task log level from env; fallback to LOG_LEVEL.
# Examples:
#   LOG_LEVEL=INFO   -> detail log keeps INFO/WARNING/ERROR
#   LOG_LEVEL=DEBUG  -> detail log keeps DEBUG and above
#   LOG_LEVEL=TRACE  -> detail log keeps all levels
DETAIL_LOG_LEVEL = os.getenv("DETAIL_LOG_LEVEL", LOG_LEVEL).upper()

SUBPROCESS_LOG_PROTOCOL_ENV = "LMETERX_SUBPROCESS_LOG_PROTOCOL"
SUBPROCESS_LOG_PROTOCOL = "lmeterx.log.v1"


def enable_subprocess_log_transport(env: Dict[str, str]) -> None:
    """Enable the versioned JSONL log transport in a child environment."""
    env[SUBPROCESS_LOG_PROTOCOL_ENV] = SUBPROCESS_LOG_PROTOCOL


def _subprocess_log_lock_path(task_id: str) -> str:
    task_digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:20]
    return os.path.join(tempfile.gettempdir(), f"lmeterx-log-{task_digest}.lock")


def cleanup_subprocess_log_transport(task_id: str) -> None:
    """Remove the process lock left by a completed child process group."""
    try:
        os.remove(_subprocess_log_lock_path(task_id))
    except FileNotFoundError:
        pass
    except OSError:
        # Logging cleanup must never affect task cleanup or task status.
        pass


def _subprocess_log_transport_enabled() -> bool:
    return os.getenv(SUBPROCESS_LOG_PROTOCOL_ENV) == SUBPROCESS_LOG_PROTOCOL


try:
    import fcntl
except ImportError:  # pragma: no cover - engine deployments are Linux based
    fcntl = None  # type: ignore[assignment]


class _ProcessSafeStream:
    """Serialize complete JSONL writes across Locust worker processes."""

    def __init__(self, stream: TextIO):
        self._stream = stream
        self._thread_lock = threading.Lock()
        self._lock_file: Optional[TextIO] = None
        self._lock_pid: Optional[int] = None

        self._lock_path = _subprocess_log_lock_path(os.getenv("TASK_ID", "unknown"))

    def _get_lock_file(self) -> Optional[TextIO]:
        if fcntl is None:
            return None

        current_pid = os.getpid()
        if self._lock_file is not None and self._lock_pid != current_pid:
            # Locust forks workers. Reopen after fork so every process owns a
            # distinct open-file description and flock can serialize them.
            self._lock_file.close()
            self._lock_file = None

        if self._lock_file is None:
            self._lock_file = open(self._lock_path, "a", encoding="utf-8")
            self._lock_pid = current_pid
        return self._lock_file

    def write(self, data: str) -> int:
        if not data:
            return 0

        with self._thread_lock:
            lock_file = self._get_lock_file()
            if lock_file is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                written = self._stream.write(data)
                # Flush while holding the process lock. Otherwise buffered data
                # from different workers could still be interleaved later.
                self._stream.flush()
            finally:
                if lock_file is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return len(data) if written is None else written

    def flush(self) -> None:
        with self._thread_lock:
            self._stream.flush()

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def _encode_subprocess_log_event(
    *,
    level: str,
    message: str,
    logger_name: str,
    event_time: str,
    file_name: str,
    line: int,
    function: str,
    process: int,
    thread: int,
) -> str:
    payload = {
        "protocol": SUBPROCESS_LOG_PROTOCOL,
        "level": level,
        "message": message,
        "logger": logger_name,
        "time": event_time,
        "file": file_name,
        "line": line,
        "function": function,
        "process": process,
        "thread": thread,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _LoguruJsonLineSink:
    """Encode one Loguru record as exactly one JSONL transport record."""

    def __init__(self, stream: TextIO):
        self._stream = _ProcessSafeStream(stream)

    def __call__(self, message: Any) -> None:
        record = message.record
        rendered_message = str(message)
        if rendered_message.endswith("\n"):
            # Loguru's handler format contributes one record terminator. Keep
            # any newline that was part of the original message itself.
            rendered_message = rendered_message[:-1]

        encoded = _encode_subprocess_log_event(
            level=record["level"].name,
            message=rendered_message,
            logger_name=record["name"],
            event_time=record["time"].isoformat(),
            file_name=record["file"].name,
            line=record["line"],
            function=record["function"],
            process=record["process"].id,
            thread=record["thread"].id,
        )
        self._stream.write(f"{encoded}\n")


class _LoggingJsonLineFormatter(logging.Formatter):
    """Encode one stdlib logging record as one JSONL transport record."""

    def __init__(self):
        super().__init__("%(message)s")

    def format(self, record: logging.LogRecord) -> str:
        # logging.Formatter includes exc_info and stack_info in the returned
        # message, keeping the whole traceback inside the same transport event.
        rendered_message = super().format(record)
        event_time = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        event_time = f"{event_time}.{int(record.msecs):03d}"
        return _encode_subprocess_log_event(
            level=record.levelname,
            message=rendered_message,
            logger_name=record.name,
            event_time=event_time,
            file_name=record.filename,
            line=record.lineno,
            function=record.funcName,
            process=record.process,
            thread=record.thread,
        )


@dataclass(frozen=True)
class SubprocessLogEvent:
    """Decoded child log event ready for parent-side forwarding."""

    level: str
    message: str
    extra: Dict[str, Any]
    transported: bool


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_STRUCTURED_SUBPROCESS_LOG_RE = re.compile(
    r"^\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?\s*\|\s*"
    r"(?P<level>INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)\s*\|\s*"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)
_LOCUST_SUBPROCESS_LOG_RE = re.compile(
    r"^\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d{1,6})?\]\s+.+?/"
    r"(?P<level>INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)/"
    r"[^:]+:\s*(?P<message>.*)$",
    re.IGNORECASE,
)

# --- Logger Configuration ---

# Ensure the log directory exists.
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(LOG_TASK_DIR, exist_ok=True)


# Remove the default logger to prevent duplicate output.
logger.remove()


def is_system_log(record):
    """Filter for system logs (not task-related)."""
    return "task_id" not in record["extra"]


# Configure the file logger for system logs
logger.add(
    os.path.join(LOG_DIR, f"engine_{ENGINE_ID}.log"),
    rotation="10 MB",  # Rotates the log file when it reaches 5 MB.
    retention="10 days",  # Retains log files for 10 days.
    compression="zip",  # Compresses rotated log files.
    encoding="utf-8",  # Sets the file encoding.
    level=LOG_LEVEL,  # Minimum log level to be written to the file.
    backtrace=False,  # Do not show the full stack trace.
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
    filter=is_system_log,  # Only log records without 'task_id'
)

# Configure the console logger. Locust subprocesses use a versioned JSONL
# transport so one logical Loguru call always maps to one physical pipe line.
# The parent engine keeps the normal human-readable console format.
if _subprocess_log_transport_enabled():
    logger.add(
        _LoguruJsonLineSink(sys.stdout),
        level=LOG_LEVEL,
        format="{message}",
        colorize=False,
        backtrace=False,
        diagnose=False,
    )
else:
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    )

sls_settings = get_sls_settings()
sls_sink = SLSLogSink(service_name=sls_settings.SLS_SERVICE_NAME or "engine")
if sls_sink.enabled:
    logger.add(
        sls_sink,
        level=DETAIL_LOG_LEVEL,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )
    logger.info(
        f"SLS logging enabled for engine_id={ENGINE_ID}, "
        f"cluster_id={os.getenv('CLUSTER_ID') or 'local'}"
    )


def setup_clean_log_format():
    """Override Locust's default log format to remove hostname and module name.

    Default Locust format:
        [%(asctime)s] %(hostname)s/%(levelname)s/%(name)s: %(message)s

    Clean format matching loguru pipe style for consistency:
        YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | message

    Call this once inside a ``@events.init.add_listener`` callback.
    """
    transport_enabled = _subprocess_log_transport_enabled()
    if transport_enabled:
        log_format = _LoggingJsonLineFormatter()
    else:
        log_format = logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    for handler in logging.root.handlers:
        handler.setFormatter(log_format)
        if (
            transport_enabled
            and isinstance(handler, logging.StreamHandler)
            and handler.stream is not None
            and not isinstance(handler.stream, _ProcessSafeStream)
        ):
            handler.setStream(_ProcessSafeStream(handler.stream))


def _normalize_log_level(level: str, default_level: str = "INFO") -> str:
    normalized = (level or default_level).upper()
    if normalized == "WARN":
        return "WARNING"
    if normalized == "FATAL":
        return "CRITICAL"
    try:
        logger.level(normalized)
    except (TypeError, ValueError):
        return _normalize_log_level(default_level, "INFO")
    return normalized


def parse_subprocess_log_event(
    line: str, default_level: str = "INFO"
) -> Optional[SubprocessLogEvent]:
    """Decode one JSONL child event, with legacy line-format fallback."""
    cleaned = _ANSI_ESCAPE_RE.sub("", line).rstrip("\r\n")

    if cleaned.lstrip().startswith("{"):
        try:
            payload = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            payload = None

        if (
            isinstance(payload, dict)
            and payload.get("protocol") == SUBPROCESS_LOG_PROTOCOL
            and isinstance(payload.get("message"), str)
        ):
            metadata_keys = (
                "logger",
                "time",
                "file",
                "line",
                "function",
                "process",
                "thread",
            )
            extra = {
                f"child_{key}": payload[key]
                for key in metadata_keys
                if payload.get(key) is not None
            }
            extra["log_protocol"] = SUBPROCESS_LOG_PROTOCOL
            return SubprocessLogEvent(
                level=_normalize_log_level(
                    str(payload.get("level") or default_level), default_level
                ),
                message=payload["message"],
                extra=extra,
                transported=True,
            )

    if not cleaned:
        return None

    for pattern in (_STRUCTURED_SUBPROCESS_LOG_RE, _LOCUST_SUBPROCESS_LOG_RE):
        match = pattern.match(cleaned)
        if match:
            return SubprocessLogEvent(
                level=_normalize_log_level(match.group("level"), default_level),
                message=match.group("message"),
                extra={},
                transported=False,
            )

    return SubprocessLogEvent(
        level=_normalize_log_level(default_level),
        message=cleaned,
        extra={},
        transported=False,
    )


def parse_subprocess_log_line(
    line: str, default_level: str = "INFO"
) -> Tuple[str, str]:
    """Extract level/message from JSONL or legacy child console output."""
    event = parse_subprocess_log_event(line, default_level)
    if event is None:
        return _normalize_log_level(default_level), ""
    return event.level, event.message


def forward_subprocess_log_line(
    task_logger,
    line: str,
    default_level: str = "INFO",
    stream: Optional[str] = None,
) -> Optional[SubprocessLogEvent]:
    """Forward one decoded child event as one structured parent record."""
    event = parse_subprocess_log_event(line, default_level)
    if event is None:
        return None

    extra = dict(event.extra)
    if stream:
        extra["subprocess_stream"] = stream
    target_logger = task_logger.bind(**extra) if extra else task_logger
    target_logger.log(event.level, event.message)
    return event


def add_task_log_sink(task_id: str) -> List[int]:
    """
    Adds a specific log sink for a given task ID.
    Returns a list of handler IDs (one for standard log, one for detailed log).
    """
    # Ensure the task log directory exists before creating the log file
    try:
        os.makedirs(LOG_TASK_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create task log directory {LOG_TASK_DIR}: {e}")

    task_log_file = os.path.join(LOG_TASK_DIR, f"task_{task_id}_engine.log")
    detail_log_file = os.path.join(LOG_TASK_DIR, f"task_{task_id}_engine_detail.log")

    def is_current_task_log(record):
        # Allow INFO and above for the standard task log
        return (
            "task_id" in record["extra"]
            and record["extra"]["task_id"] == task_id
            and record["level"].no >= logger.level("INFO").no
        )

    def is_detail_task_log(record):
        # Detail task log follows env level (DETAIL_LOG_LEVEL/LOG_LEVEL)
        target_level_no = logger.level(DETAIL_LOG_LEVEL).no
        return (
            "task_id" in record["extra"]
            and record["extra"]["task_id"] == task_id
            and record["level"].no >= target_level_no
        )

    try:
        # Add a new handler to the existing logger instead of creating a new one
        handler_id = logger.add(
            task_log_file,
            rotation="20 MB",
            retention="10 days",
            compression="zip",
            encoding="utf-8",
            level=LOG_LEVEL,  # follow the global LOG_LEVEL
            backtrace=True,  # Enable backtrace for task logs to help with debugging
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            filter=is_current_task_log,
        )

        detail_handler_id = logger.add(
            detail_log_file,
            rotation="50 MB",
            retention="10 days",
            compression="zip",
            encoding="utf-8",
            level=DETAIL_LOG_LEVEL,
            backtrace=True,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            filter=is_detail_task_log,
            enqueue=True,  # Asynchronous writing.
        )

        # Test the logger to ensure it's working
        test_logger = logger.bind(task_id=task_id)
        test_logger.info(f"Task log initialized for task {task_id}")

        return [handler_id, detail_handler_id]
    except Exception as e:
        logger.error(f"Failed to create task log sink for task {task_id}: {e}")
        # Return a dummy handler ID to prevent downstream errors
        return [-1]


def remove_task_log_sink(handler_ids: Union[int, List[int]]):
    """
    Removes log sinks by their handler IDs.
    """
    if not isinstance(handler_ids, list):
        handler_ids = [handler_ids]

    for handler_id in handler_ids:
        if handler_id > 0:  # Only remove valid handler IDs
            try:
                logger.remove(handler_id)
            except Exception as e:
                logger.warning(
                    f"Failed to remove log sink with handler ID {handler_id}: {e}"
                )
        else:
            logger.warning(f"Skipping removal of invalid handler ID: {handler_id}")
