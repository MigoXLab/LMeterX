"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from utils.logger import logger


def safe_isoformat(value) -> Optional[str]:
    """Return isoformat string when value is present, otherwise None."""
    return value.isoformat() if value else None


def truthy(value: Any) -> bool:
    """Normalize different truthy inputs (bool/str/others) into bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def safe_json_loads(value: Any, context: str, default: Any) -> Any:
    """
    Best-effort JSON loader that falls back to default on errors and logs context.
    """
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Could not parse {} JSON: {}", context, value)
        return default


def kv_items_to_dict(items: Sequence[Any]) -> Dict[str, str]:
    """Convert objects with key/value attrs to dict, skipping empties."""
    result: Dict[str, str] = {}
    for item in items:
        key = getattr(item, "key", None)
        value = getattr(item, "value", None)
        if key and value is not None:
            result[str(key)] = value
    return result


def dict_to_kv_list(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert dict to list of {key, value} pairs for API responses."""
    return [{"key": k, "value": v} for k, v in data.items()] if data else []


def enforce_collection_limit(
    items: Sequence[Any], limit: int, error_message: str
) -> None:
    """Raise ValueError when collection exceeds limit."""
    if len(items) > limit:
        raise ValueError(error_message)
