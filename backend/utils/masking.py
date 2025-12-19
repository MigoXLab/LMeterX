"""
Data masking utilities for sensitive information.
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import re
from typing import Any, Dict, List, Optional, Union

from utils.logger import logger

SENSITIVE_KEYS = [
    "api_key",
    "token",
    "password",
    "secret",
    "key",
    "authorization",
    "auth",
    "credential",
    "private_key",
    "access_key",
    "secret_key",
    "bearer",
    "session",
]


def mask_sensitive_data(data: Union[dict, list]) -> Union[dict, list]:
    """
    Mask sensitive information for safe logging and API responses.

    Args:
        data: The data to mask.

    Returns:
        The masked data.
    """
    if isinstance(data, dict):
        safe_dict: Dict[Any, Any] = {}
        try:
            for key, value in data.items():
                if isinstance(key, str) and _is_sensitive_key(key):
                    safe_dict[key] = "****"
                else:
                    safe_dict[key] = mask_sensitive_data(value)
        except Exception as e:
            logger.warning(f"Error masking sensitive data: {str(e)}")
            return data
        return safe_dict
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    else:
        return data


def _is_sensitive_key(key: str) -> bool:
    """
    Check if the key is a sensitive key.

    Args:
        key: The key to check.

    Returns:
        True if the key is a sensitive key, False otherwise.
    """
    key_lower = key.lower()
    return any(sensitive_key in key_lower for sensitive_key in SENSITIVE_KEYS)


def mask_config_value(config_key: str, config_value: str) -> str:
    """
    Mask sensitive configuration values.

    Args:
        config_key: The configuration key.
        config_value: The configuration value.

    Returns:
        The masked configuration value.
    """
    if _is_sensitive_key(config_key):
        # For sensitive configurations, only show the first 4 and last 4 characters, with asterisks in between
        if len(config_value) <= 8:
            return "****"
        else:
            return config_value[:4] + "*" * 4 + config_value[-4:]
    return config_value


def mask_api_key(api_key: str) -> str:
    """
    Mask sensitive API keys.

    Args:
        api_key: The API key.

    Returns:
        The masked API key.
    """
    if not api_key:
        return ""

    # If the API key is in Bearer token format, keep the Bearer prefix
    if api_key.startswith("Bearer "):
        token_part = api_key[7:]  # Remove the "Bearer " prefix
        if len(token_part) <= 8:
            return "Bearer ****"
        else:
            return "Bearer " + token_part[:4] + "*" * 4 + token_part[-4:]

    # Handle normal API keys
    if len(api_key) <= 8:
        return "****"
    else:
        return api_key[:4] + "*" * 4
