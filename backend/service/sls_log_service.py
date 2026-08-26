"""
Query Alibaba Cloud Simple Log Service for UI log views.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from model.log import SLSLogEntry, SLSLogResponse
from utils.error_handler import ErrorResponse
from utils.logger import logger
from utils.sls_settings import SLSSettings, get_sls_settings

_CLIENT_CACHE: dict[tuple[str, str, str], Any] = {}
_DUPLICATE_WINDOW_SECONDS = 0.25
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_STRUCTURED_MESSAGE_RE = re.compile(
    r"^\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?\s*\|\s*"
    r"(?:INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)\s*\|\s*(.*)$",
    re.IGNORECASE,
)
_LOCUST_MESSAGE_RE = re.compile(
    r"^\s*\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d{1,6})?\]\s+.+?/"
    r"(?:INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)/"
    r"[^:]+:\s*(.*)$",
    re.IGNORECASE,
)


def _format_log_time(value: str | None, fallback_timestamp: int) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(value)
            # Preserve the precision supplied by the sink.  Locust emits its
            # final report as several adjacent multiline records which often
            # share a displayed millisecond; truncating here makes their order
            # depend on the order returned by SLS.
            return parsed.strftime("%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            pass
    fallback_time = datetime.fromtimestamp(fallback_timestamp)
    return fallback_time.strftime("%Y-%m-%d %H:%M:%S.%f")


def _normalize_log_message(value: str) -> str:
    """Remove formatting already supplied by a child process."""
    message = _ANSI_ESCAPE_RE.sub("", value).strip()
    for _ in range(3):
        for pattern in (_STRUCTURED_MESSAGE_RE, _LOCUST_MESSAGE_RE):
            match = pattern.match(message)
            if match:
                message = match.group(1).strip()
                break
        else:
            return message
    return message


def _require_sls_enabled(settings: SLSSettings) -> None:
    if not settings.is_configured:
        raise ErrorResponse(503, "SLS logging is not configured")


def _client(settings: SLSSettings):
    _require_sls_enabled(settings)
    cache_key = (
        settings.SLS_ENDPOINT,
        settings.SLS_ACCESS_KEY_ID,
        settings.SLS_ACCESS_KEY_SECRET,
    )
    if cache_key in _CLIENT_CACHE:
        return _CLIENT_CACHE[cache_key]

    try:
        from aliyun.log import LogClient

        client = LogClient(
            settings.SLS_ENDPOINT,
            settings.SLS_ACCESS_KEY_ID,
            settings.SLS_ACCESS_KEY_SECRET,
        )
        _CLIENT_CACHE[cache_key] = client
        return client
    except Exception as exc:
        logger.error("Failed to initialize SLS client: {}", exc)
        raise ErrorResponse.internal_server_error("Failed to initialize SLS client")


def _escape_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_query(
    *,
    service: str | None = None,
    task_id: str | None = None,
    engine_id: str | None = None,
    cluster_id: str | None = None,
    exclude_task_logs: bool = False,
    keyword: str | None = None,
    level: str | None = None,
) -> str:
    filters = []
    if service:
        filters.append(f'service: "{_escape_query_value(service)}"')
    if task_id:
        filters.append(f'task_id: "{_escape_query_value(task_id)}"')
    if engine_id:
        filters.append(f'engine_id: "{_escape_query_value(engine_id)}"')
    if cluster_id:
        filters.append(f'cluster_id: "{_escape_query_value(cluster_id)}"')
    if exclude_task_logs:
        filters.append("not task_id: *")
    if level:
        filters.append(f'level: "{_escape_query_value(level.upper())}"')
    if keyword:
        filters.append(f'"{_escape_query_value(keyword)}"')
    return " and ".join(filters) if filters else "*"


def _extract_log_entry(item: Any) -> SLSLogEntry:
    contents = item.get_contents()
    timestamp = int(getattr(item, "get_time", lambda: int(time.time()))())
    raw = {str(k): str(v) for k, v in contents.items()}
    raw["time"] = _format_log_time(raw.get("time"), timestamp)
    raw["message"] = _normalize_log_message(raw.get("message", ""))
    return SLSLogEntry(
        timestamp=timestamp,
        level=raw.get("level", ""),
        message=raw.get("message", ""),
        service=raw.get("service", ""),
        task_id=raw.get("task_id"),
        engine_id=raw.get("engine_id"),
        cluster_id=raw.get("cluster_id"),
        raw=raw,
    )


def _entry_sort_key(entry: SLSLogEntry) -> tuple[float, int]:
    raw_time = entry.raw.get("time", "")
    if raw_time:
        try:
            return (datetime.fromisoformat(raw_time).timestamp(), entry.timestamp)
        except ValueError:
            pass
    return (float(entry.timestamp), entry.timestamp)


def _deduplicate_entries(entries: list[SLSLogEntry]) -> list[SLSLogEntry]:
    """Collapse child-direct and parent-forwarded copies of one event."""
    deduplicated: list[SLSLogEntry] = []
    last_seen: dict[tuple[str, ...], float] = {}

    for entry in entries:
        event_time = _entry_sort_key(entry)[0]
        key = (
            entry.service or "",
            entry.task_id or "",
            entry.engine_id or "",
            entry.cluster_id or "",
            entry.level.upper(),
            entry.message,
        )
        previous_time = last_seen.get(key)
        if (
            previous_time is not None
            and 0 <= event_time - previous_time <= _DUPLICATE_WINDOW_SECONDS
        ):
            continue
        deduplicated.append(entry)
        last_seen[key] = event_time

    return deduplicated


def _is_transient_sls_error(error_code: str, error_message: str) -> bool:
    message = error_message.lower()
    transient_markers = (
        "nameresolutionerror",
        "failed to resolve",
        "temporary failure in name resolution",
        "max retries exceeded",
        "connectionpool",
        "connection refused",
        "connect timeout",
        "read timed out",
        "timeout",
    )
    return error_code == "LogRequestError" or any(
        marker in message for marker in transient_markers
    )


async def query_sls_logs_svc(
    *,
    service: str | None = None,
    task_id: str | None = None,
    engine_id: str | None = None,
    cluster_id: str | None = None,
    exclude_task_logs: bool = False,
    keyword: str | None = None,
    level: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 200,
    offset: int = 0,
    reverse: bool = False,
) -> SLSLogResponse:
    try:
        from aliyun.log import GetLogsRequest
    except Exception as exc:
        logger.error("Failed to import SLS SDK: {}", exc)
        raise ErrorResponse.internal_server_error(
            "aliyun-log-python-sdk is not installed"
        )

    now = int(time.time())
    from_time = start_time or max(0, now - 3600)
    to_time = end_time or now
    safe_limit = min(max(limit, 1), 1000)
    safe_offset = max(offset, 0)
    settings = get_sls_settings()
    query = _build_query(
        service=service,
        task_id=task_id,
        engine_id=engine_id,
        cluster_id=cluster_id,
        exclude_task_logs=exclude_task_logs,
        keyword=keyword,
        level=level,
    )

    try:
        response = _client(settings).get_logs(
            GetLogsRequest(
                settings.SLS_PROJECT,
                settings.SLS_LOGSTORE,
                from_time,
                to_time,
                "",
                query,
                safe_limit,
                safe_offset,
                reverse,
            )
        )
        fetched_entries = [_extract_log_entry(item) for item in response.get_logs()]
        fetched_count = len(fetched_entries)
        raw_entries = fetched_entries
        if exclude_task_logs:
            raw_entries = [entry for entry in raw_entries if not entry.task_id]
        raw_entries.sort(key=_entry_sort_key)
        entries = _deduplicate_entries(raw_entries)
        next_cursor = max(
            [entry.timestamp for entry in fetched_entries], default=to_time - 5
        )
        if fetched_entries:
            next_cursor += 1
        return SLSLogResponse(
            logs=entries,
            next_cursor=next_cursor,
            next_offset=(
                safe_offset + fetched_count if fetched_count >= safe_limit else 0
            ),
            has_more=fetched_count >= safe_limit,
        )
    except ErrorResponse:
        raise
    except Exception as exc:
        get_error_code = getattr(exc, "get_error_code", None)
        get_error_message = getattr(exc, "get_error_message", None)
        get_request_id = getattr(exc, "get_request_id", None)
        error_code = get_error_code() if callable(get_error_code) else ""
        error_message = get_error_message() if callable(get_error_message) else str(exc)
        request_id = get_request_id() if callable(get_request_id) else ""
        if error_code == "IndexConfigNotExist":
            logger.error(
                "SLS logstore index is not configured: project={}, logstore={}, request_id={}",
                settings.SLS_PROJECT,
                settings.SLS_LOGSTORE,
                request_id,
            )
            raise ErrorResponse(
                503,
                "SLS logstore index is not configured",
                details=error_message,
                code="sls_index_not_configured",
                extra={
                    "project": settings.SLS_PROJECT,
                    "logstore": settings.SLS_LOGSTORE,
                    "request_id": request_id,
                },
            )
        if _is_transient_sls_error(error_code, error_message):
            logger.warning(
                "SLS is temporarily unavailable: code={}, message={}, request_id={}",
                error_code,
                error_message,
                request_id,
            )
            raise ErrorResponse(
                503,
                "SLS is temporarily unavailable",
                details=error_message,
                code="sls_temporarily_unavailable",
                extra={"request_id": request_id} if request_id else None,
            )
        logger.error(
            "Failed to query SLS logs: code={}, message={}, request_id={}",
            error_code,
            error_message,
            request_id,
        )
        raise ErrorResponse.internal_server_error(
            "Failed to query SLS logs",
            details=error_message,
            extra={"request_id": request_id} if request_id else None,
        )
