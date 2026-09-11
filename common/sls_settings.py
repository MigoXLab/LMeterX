"""
Shared settings loader for Alibaba Cloud Simple Log Service.
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _env_value(file_values: dict[str, str], key: str, default: str = "") -> str:
    return os.getenv(key, file_values.get(key, default))


def _env_bool(file_values: dict[str, str], key: str, default: bool = False) -> bool:
    value = _env_value(file_values, key, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(file_values: dict[str, str], key: str, default: int) -> int:
    try:
        return int(_env_value(file_values, key, str(default)))
    except ValueError:
        return default


def _env_float(file_values: dict[str, str], key: str, default: float) -> float:
    try:
        return float(_env_value(file_values, key, str(default)))
    except ValueError:
        return default


class SLSSettings:
    """SLS settings loaded from process environment and a service env file."""

    def __init__(self, env_file_path: Path | str | None = None) -> None:
        file_values = _parse_env_file(Path(env_file_path)) if env_file_path else {}
        self.SLS_ENABLED = _env_bool(file_values, "SLS_ENABLED", False)
        self.SLS_ENDPOINT = _env_value(file_values, "SLS_ENDPOINT")
        self.SLS_PROJECT = _env_value(file_values, "SLS_PROJECT")
        self.SLS_LOGSTORE = _env_value(file_values, "SLS_LOGSTORE")
        self.SLS_ACCESS_KEY_ID = _env_value(file_values, "SLS_ACCESS_KEY_ID")
        self.SLS_ACCESS_KEY_SECRET = _env_value(file_values, "SLS_ACCESS_KEY_SECRET")
        self.SLS_TOPIC = _env_value(file_values, "SLS_TOPIC")
        self.SLS_SERVICE_NAME = _env_value(file_values, "SLS_SERVICE_NAME")
        self.SLS_SOURCE = _env_value(file_values, "SLS_SOURCE")
        self.SLS_BATCH_SIZE = _env_int(file_values, "SLS_BATCH_SIZE", 100)
        self.SLS_FLUSH_INTERVAL = _env_float(file_values, "SLS_FLUSH_INTERVAL", 2)
        self.SLS_QUEUE_SIZE = _env_int(file_values, "SLS_QUEUE_SIZE", 10000)

    @property
    def is_configured(self) -> bool:
        """Return whether SLS has the required settings for read/write calls."""
        return all(
            [
                self.SLS_ENABLED,
                self.SLS_ENDPOINT,
                self.SLS_PROJECT,
                self.SLS_LOGSTORE,
                self.SLS_ACCESS_KEY_ID,
                self.SLS_ACCESS_KEY_SECRET,
            ]
        )
