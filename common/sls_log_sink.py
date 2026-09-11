"""
Shared Loguru sink for Alibaba Cloud Simple Log Service.
"""

from __future__ import annotations

import atexit
import socket
import sys
import threading
import time
from collections.abc import Callable, Mapping
from queue import Empty, Queue
from typing import Any, Optional, Union


ExtraFields = Union[Mapping[str, Any], Callable[[dict[str, Any]], Mapping[str, Any]]]


def _format_record_time(record_time: Any) -> str:
    # Keep microseconds for deterministic ordering of adjacent log records.
    # The UI may display milliseconds, but sorting must not discard the extra
    # precision before Locust's summary and percentile tables are assembled.
    return record_time.strftime("%Y-%m-%d %H:%M:%S.%f")


class SLSLogSink:
    """Asynchronous batched sink for Alibaba Cloud SLS."""

    def __init__(
        self,
        *,
        service_name: str,
        enabled: bool,
        endpoint: str,
        project: str,
        logstore: str,
        access_key_id: str,
        access_key_secret: str,
        topic: str = "",
        source: str = "",
        batch_size: int = 100,
        flush_interval: float = 2,
        queue_size: int = 10000,
        extra_fields: Optional[ExtraFields] = None,
    ):
        """Initialize the SLSLogSink with service configuration."""
        self.enabled = enabled
        self.service_name = service_name
        self.endpoint = endpoint
        self.project = project
        self.logstore = logstore
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.topic = topic or service_name
        self.source = source or socket.gethostname()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.queue_size = queue_size
        self.extra_fields = extra_fields
        self._queue: Queue[Optional[dict[str, str]]] = Queue(maxsize=self.queue_size)
        self._thread: Optional[threading.Thread] = None
        self._client: Any = None
        self._sdk: Optional[tuple[Any, Any]] = None

        if self.enabled:
            self._start()

    def _start(self) -> None:
        required = [
            self.endpoint,
            self.project,
            self.logstore,
            self.access_key_id,
            self.access_key_secret,
        ]
        if not all(required):
            self.enabled = False
            print(
                "SLS logging disabled: missing SLS endpoint/project/logstore/credentials",
                file=sys.stderr,
            )
            return

        try:
            from aliyun.log import LogClient, LogItem, PutLogsRequest

            self._client = LogClient(
                self.endpoint,
                self.access_key_id,
                self.access_key_secret,
            )
            self._sdk = (LogItem, PutLogsRequest)
        except Exception as exc:
            self.enabled = False
            print(
                f"SLS logging disabled: failed to import aliyun-log SDK: {exc}",
                file=sys.stderr,
            )
            return

        self._thread = threading.Thread(
            target=self._worker,
            name=f"{self.service_name}-sls-log-sink",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.close)

    def __call__(self, message: Any) -> None:
        """Process incoming log message."""
        if not self.enabled:
            return

        record = message.record
        log = self._record_to_log(record)
        try:
            self._queue.put_nowait(log)
        except Exception:
            # Never let logging backpressure slow or break a load test.
            return

    def close(self) -> None:
        """Close the sink and stop the background thread."""
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(None)
        except Exception:  # nosec B110
            pass
        if self._thread:
            self._thread.join(timeout=5)

    def _worker(self) -> None:
        batch: list[dict[str, str]] = []
        deadline = time.monotonic() + self.flush_interval

        sentinel = object()

        while True:
            timeout = max(0.1, deadline - time.monotonic())
            item: Union[dict[str, str], None, object] = sentinel
            try:
                item = self._queue.get(timeout=timeout)
            except Empty:
                pass

            if item is None:
                if batch:
                    self._send_batch(batch)
                break
            if item is not sentinel:
                batch.append(item)

            if len(batch) >= self.batch_size or time.monotonic() >= deadline:
                if batch:
                    self._send_batch(batch)
                    batch = []
                deadline = time.monotonic() + self.flush_interval

    def _send_batch(self, batch: list[dict[str, str]]) -> None:
        if not self._client or not self._sdk:
            return
        LogItem, PutLogsRequest = self._sdk
        try:
            log_items = []
            now = int(time.time())
            for content in batch:
                item = LogItem()
                item.set_time(now)
                item.set_contents(list(content.items()))
                log_items.append(item)

            request = PutLogsRequest(
                self.project,
                self.logstore,
                self.topic,
                self.source,
                log_items,
            )
            self._client.put_logs(request)
        except Exception as exc:
            print(f"SLS logging batch dropped: {exc}", file=sys.stderr)

    def _resolve_extra_fields(self, record: dict[str, Any]) -> Mapping[str, Any]:
        if self.extra_fields is None:
            return {}
        if callable(self.extra_fields):
            return self.extra_fields(record)
        return self.extra_fields

    def _record_to_log(self, record: dict[str, Any]) -> dict[str, str]:
        extra = record.get("extra", {})
        log = {
            "service": self.service_name,
            "level": record["level"].name,
            "message": record["message"],
            "time": _format_record_time(record["time"]),
            "file": record["file"].name,
            "line": str(record["line"]),
            "function": record["function"],
            "module": record["module"],
            "process": str(record["process"].id),
            "thread": str(record["thread"].id),
        }

        for key, value in self._resolve_extra_fields(record).items():
            if value is not None:
                log[str(key)] = str(value)

        for key, value in extra.items():
            if value is not None:
                log[str(key)] = str(value)

        return log
