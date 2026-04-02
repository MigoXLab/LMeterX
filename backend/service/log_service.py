"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import os.path
import re

from model.log import LogContentResponse
from utils.be_config import LOG_DIR
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger

# Only allow alphanumeric, underscore and hyphen in service/task names
_SAFE_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def get_last_n_lines(file_path: str, n: int = 100) -> str:
    """
    Reads the last N lines from a file by seeking from the end.
    This method is more efficient for large files as it avoids reading the whole file.

    Args:
        file_path: The path to the file.
        n: The number of lines to retrieve.

    Returns:
        A string containing the last N lines. Returns an empty string on failure.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            # For small files, just read all and return last n lines
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            # If file is small (< 50KB), read all lines and return last n
            if file_size < 50 * 1024:
                f.seek(0)
                all_lines = f.readlines()
                return "".join(all_lines[-n:]) if all_lines else ""

            # For larger files, use a more efficient approach
            # Read from end in chunks and collect lines
            lines = list[str]()
            buffer = ""
            position = file_size
            buffer_size = 8192

            while position > 0 and len(lines) < n:
                # Calculate how much to read
                chunk_size = min(buffer_size, position)
                position -= chunk_size

                # Read chunk from current position
                f.seek(position)
                chunk = f.read(chunk_size)

                # Prepend chunk to buffer
                buffer = chunk + buffer

                # Split buffer into lines
                split_lines = buffer.split("\n")

                # If we haven't reached the beginning, keep the first part as incomplete line
                if position > 0:
                    buffer = split_lines[0]
                    # Process complete lines (skip the first incomplete one)
                    complete_lines = split_lines[1:]
                else:
                    # At the beginning of file, all lines are complete
                    buffer = ""
                    complete_lines = split_lines

                # Add complete lines to the front of our lines list
                # (since we're reading backwards)
                for line in reversed(complete_lines):
                    lines.insert(0, line)
                    if len(lines) >= n:
                        break

                # If we have enough lines, break
                if len(lines) >= n:
                    break

            # Take last n lines
            result_lines = lines[-n:] if len(lines) > n else lines

            # Join lines and ensure proper ending
            if not result_lines:
                return ""

            result = "\n".join(result_lines)
            # Add final newline if the original content had one and result doesn't end with one
            if result and not result.endswith("\n"):
                # Check if original file ends with newline
                f.seek(max(0, file_size - 1))
                if f.read(1) == "\n":
                    result += "\n"

            return result

    except Exception as e:
        logger.error("Failed to read log file: {}", e)
        return ""


def read_local_file(log_file_path: str, tail: int, offset: int) -> str:
    """
    Reads content from a local file, either the tail or from a specific offset.

    Args:
        log_file_path: The path to the log file.
        tail: The number of lines to read from the end. If 0, reads from offset.
        offset: The byte offset to start reading from. Used only if tail is 0.

    Returns:
        The content of the file as a string.
    """
    if tail == 0:
        with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
            if offset > 0:
                f.seek(offset)
            content = f.read()
    else:
        content = get_last_n_lines(file_path=log_file_path, n=tail)
    return content


async def get_service_log_svc(service_name: str, offset: int, tail: int):
    """
    Service function to get the log content for a given service name.

    It constructs the log file path, checks for its existence, and reads the content
    based on the offset and tail parameters.

    Args:
        service_name: The name of the service (e.g., "backend").
        offset: The byte offset to start reading from.
        tail: The number of lines to read from the end of the file.

    Returns:
        A `LogContentResponse` object on success, or a `JSONResponse` with an error
        message on failure.
    """
    if not service_name:
        raise ErrorResponse.bad_request(ErrorMessages.SERVICE_NAME_EMPTY)

    if not _SAFE_NAME_PATTERN.match(service_name):
        raise ErrorResponse.bad_request("Invalid service name")

    log_file_path = os.path.join(LOG_DIR, f"{service_name}.log")

    # Ensure resolved path stays within LOG_DIR to prevent path traversal
    resolved_path = os.path.realpath(log_file_path)
    log_dir_real = os.path.realpath(LOG_DIR) + os.sep
    if not resolved_path.startswith(log_dir_real):
        raise ErrorResponse.bad_request("Invalid service name")

    if not os.path.exists(resolved_path):
        logger.warning("Log file not found for service: {}", service_name)
        raise ErrorResponse.not_found(
            f"Log file for service '{service_name}' not found"
        )
    try:
        content = read_local_file(log_file_path, tail, offset)
        file_size = os.path.getsize(log_file_path)
        return LogContentResponse(content=content, file_size=file_size)
    except Exception as e:
        logger.error("Failed to read log file {}: {}", log_file_path, e)
        raise ErrorResponse.internal_server_error(ErrorMessages.LOG_FILE_READ_FAILED)


async def get_task_log_svc(task_id: str, offset: int, tail: int):
    """
    Service function to get the log content for a given task ID.

    It constructs the log file path, checks for its existence, and reads the content
    based on the offset and tail parameters.
    """
    if not task_id:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_ID_EMPTY)

    if not _SAFE_NAME_PATTERN.match(task_id):
        raise ErrorResponse.bad_request("Invalid task ID")

    log_file_path = os.path.join(LOG_DIR, "task", f"task_{task_id}.log")

    # Ensure resolved path stays within LOG_DIR to prevent path traversal
    resolved_path = os.path.realpath(log_file_path)
    log_dir_real = os.path.realpath(LOG_DIR) + os.sep
    if not resolved_path.startswith(log_dir_real):
        raise ErrorResponse.bad_request("Invalid task ID")

    if not os.path.exists(resolved_path):
        logger.warning("Log file not found for task: {}", task_id)
        raise ErrorResponse.not_found(f"Log file for task '{task_id}' not found")

    try:
        content = read_local_file(log_file_path, tail, offset)
        file_size = os.path.getsize(log_file_path)
        return LogContentResponse(content=content, file_size=file_size)
    except Exception as e:
        logger.error("Failed to read log file {}: {}", log_file_path, e)
        raise ErrorResponse.internal_server_error(ErrorMessages.LOG_FILE_READ_FAILED)
