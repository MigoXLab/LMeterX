"""
Shared engine identity helpers.
"""

from __future__ import annotations

import os

_ENGINE_ID_ENV_KEYS = (
    "ENGINE_ID",
    "ENGINE_POD_NAME",
    "ENGINE_ID_FALLBACK",
    "HOSTNAME",
)
_MAX_ENGINE_ID_LENGTH = 64


def resolve_engine_id() -> str:
    """Resolve the unique engine instance id used by control-plane services."""
    for key in _ENGINE_ID_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if not value:
            continue
        if len(value) > _MAX_ENGINE_ID_LENGTH:
            raise ValueError(
                f"{key} must not exceed {_MAX_ENGINE_ID_LENGTH} characters"
            )
        return value

    return "engine-local"


def resolve_cluster_id() -> str:
    """Resolve the stable cluster id used by heartbeat, metrics, and logs."""
    return os.getenv("CLUSTER_ID") or "local"
