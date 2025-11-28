"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import base64
import os
import re
from typing import Any, Dict, Union

from config.base import SENSITIVE_KEYS
from utils.logger import logger


# === SECURITY UTILITIES ===
def mask_sensitive_data(data: Union[dict, list]) -> Union[dict, list]:
    """Masks sensitive information for safe logging.

    Args:
        data (Union[dict, list]): The data to mask.

    Returns:
        Union[dict, list]: The masked data.
    """
    if isinstance(data, dict):
        safe_dict: Dict[Any, Any] = {}
        try:
            for key, value in data.items():
                if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
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


def mask_sensitive_command(command_list: list) -> list:
    """Masks sensitive command for safe logging.

    Args:
        command_list (list): The list of commands to mask.

    Returns:
        list: The masked command list.
    """
    if not isinstance(command_list, list):
        return command_list

    safe_list = []
    try:
        for item in command_list:
            new_item = re.sub(
                r'("Authorization"\s*:\s*").*?(")',
                r"\1********\2",
                item,
                flags=re.IGNORECASE,
            )
            safe_list.append(new_item)
        return safe_list
    except Exception as e:
        logger.warning(f"Error masking sensitive command: {str(e)}")
        return command_list


# === IMAGE UTILITIES ===
def encode_image(image_path: str) -> str:
    """Encodes an image file into a base64 string.

    Args:
        image_path (str): The path to the image file to encode.

    Returns:
        str: The base64 encoded image string.

    Raises:
        FileNotFoundError: If the image file doesn't exist.
        IOError: If there's an issue reading the file.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except IOError as e:
        raise IOError(f"Failed to read image file {image_path}: {e}")


def is_url(text: str) -> bool:
    """Check if a string is a valid URL.

    Args:
        text: String to check

    Returns:
        bool: True if text is a URL, False otherwise
    """
    if not isinstance(text, str):
        return False
    return text.startswith(("http://", "https://", "ftp://", "ftps://"))


# === STATISTICS UTILITIES ===
def wait_time_for_stats_sync(runner, concurrent_users: int) -> float:
    """
    Calculates wait time to ensure that all worker statistics are reported to the master.

    Formula:
        wait_time = base_delay +  user_count * user_factor

    Parameters can be adjusted, suitable for different scale stress tests.
    """
    # ⚙️ Adjustable parameters (based on your system and network)
    BASE_DELAY = 10.0  # Base delay, ensure last batch of data has time to be sent
    USER_FACTOR = 0.1  # Add 10 second for each additional 100 users
    # Calculate wait time
    wait_time = BASE_DELAY + (concurrent_users * USER_FACTOR)

    # Set upper limit, avoid extreme cases (e.g. 10000 users → wait too long)
    MAX_WAIT_TIME = 60.0  # Avoid extreme cases (e.g. 10000 users → wait too long)
    wait_time = min(
        wait_time, MAX_WAIT_TIME
    )  # Avoid extreme cases (e.g. 10000 users → wait too long)

    # Set lower limit, ensure at least 2 seconds
    MIN_WAIT_TIME = 2.0  # Ensure at least 2 seconds
    wait_time = max(wait_time, MIN_WAIT_TIME)
    return wait_time


# === TYPE CONVERSION UTILITIES ===
def safe_int_convert(value):
    """Safely convert value to integer.

    Args:
        value: Value to convert

    Returns:
        int: Converted integer value, or 0 if conversion fails
    """
    if value is None:
        return 0
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return 0
        try:
            return int(value)
        except ValueError:
            return 0
    elif isinstance(value, (int, float)):
        return int(value)
    return 0
