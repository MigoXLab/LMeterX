"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from pydantic import BaseModel


class LogContentResponse(BaseModel):
    """
    Represents the response model for log content.

    Attributes:
        content: The content of the log file as a string.
        file_size: The size of the log file in bytes.
        log_url: Optional URL to download the full log file.
    """

    content: str
    file_size: int
    log_url: str | None = None


class SLSLogEntry(BaseModel):
    timestamp: int
    level: str = ""
    message: str = ""
    service: str = ""
    task_id: str | None = None
    engine_id: str | None = None
    cluster_id: str | None = None
    raw: dict[str, str] = {}


class SLSLogResponse(BaseModel):
    logs: list[SLSLogEntry]
    next_cursor: int
    next_offset: int = 0
    has_more: bool = False
