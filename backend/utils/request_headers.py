"""Shared helpers for copy-safe request-header handling."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

INHERITED_SECRET_PLACEHOLDER = "•" * 8  # UI redaction mask, not a credential


def merge_headers(
    inherited: Mapping[str, str], overrides: Mapping[str, str]
) -> dict[str, str]:
    """Merge header overrides case-insensitively while preserving display casing."""
    merged = {str(key): str(value) for key, value in inherited.items()}
    existing = {key.lower(): key for key in merged}
    for key, value in overrides.items():
        normalized = str(key).lower()
        previous = existing.get(normalized)
        if previous is not None and previous != key:
            merged.pop(previous, None)
        merged[str(key)] = str(value)
        existing[normalized] = str(key)
    return merged


def redact_headers_for_copy(headers: Mapping[str, str]) -> list[dict[str, Any]]:
    """Return form rows without exposing user-supplied header values.

    ``Content-Type`` is the system-managed row in all task forms and is safe to
    display. Every other header is treated as sensitive instead of relying on
    an incomplete credential-name denylist.
    """
    rows: list[dict[str, Any]] = []
    for key, value in headers.items():
        if str(key).lower() == "content-type":
            rows.append(
                {
                    "key": str(key),
                    "value": str(value),
                    "fixed": True,
                    "sensitive": False,
                    "configured": True,
                }
            )
            continue
        rows.append(
            {
                "key": str(key),
                "value": None,
                "fixed": False,
                "sensitive": True,
                "configured": True,
                "required_on_copy": False,
                "inherited_on_start": True,
            }
        )
    return rows


def redact_header_names_for_copy(header_names: Iterable[str]) -> list[dict[str, Any]]:
    """Redact a collection of custom header names with no system rows."""
    return [
        {
            "key": str(key),
            "value": None,
            "sensitive": True,
            "configured": True,
            "required_on_copy": False,
            "inherited_on_start": True,
        }
        for key in header_names
    ]


def redacted_header_keys(headers: Mapping[str, str] | Iterable[str]) -> list[str]:
    """Return custom header names, excluding the system-managed Content-Type."""
    keys = headers.keys() if isinstance(headers, Mapping) else headers
    return [str(key) for key in keys if str(key).lower() != "content-type"]


def next_rerun_name(name: str, max_length: int = 100) -> str:
    """Increment the conventional ``-N`` rerun suffix."""
    match = re.match(r"^(.*)-(\d+)$", name)
    suffix = f"-{int(match.group(2)) + 1}" if match else "-1"
    base = match.group(1) if match else name
    return f"{base[: max_length - len(suffix)]}{suffix}"
