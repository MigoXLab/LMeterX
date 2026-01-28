"""
Security configuration and utilities for file upload functionality.
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import mimetypes
import os
import re
from typing import Optional, Set

from utils.be_config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    DANGEROUS_PATTERNS,
    MAX_FILE_SIZE,
    MAX_FILENAME_LENGTH,
    MAX_TASK_ID_LENGTH,
    TASK_ID_PATTERN,
)
from utils.logger import logger


def safe_join(base_path: str, *paths: str) -> str:
    """
    Safely join paths and ensure the result is within the base directory.

    Args:
        base_path: The base directory path
        *paths: Additional path components

    Returns:
        The safely joined path

    Raises:
        ValueError: If the resulting path is outside the base directory
    """
    # Normalize base path
    base_path = os.path.realpath(base_path)

    # Join paths
    joined_path = os.path.join(base_path, *paths)

    # Normalize the joined path
    real_joined_path = os.path.realpath(joined_path)

    # Ensure the result is within the base directory
    if not real_joined_path.startswith(base_path):
        raise ValueError("Path traversal detected")

    return real_joined_path


def validate_task_id(task_id: str) -> str:
    """
    Validate and sanitize task_id to prevent directory traversal.

    Args:
        task_id: The task ID to validate

    Returns:
        Sanitized task ID

    Raises:
        ValueError: If task_id contains invalid characters or is too long
    """
    if not task_id:
        raise ValueError("Task ID is required")

    if len(task_id) > MAX_TASK_ID_LENGTH:
        raise ValueError(f"Task ID too long (max {MAX_TASK_ID_LENGTH} characters)")

    # Check for directory traversal patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, task_id):
            raise ValueError(f"Task ID contains invalid characters: {pattern}")

    # Ensure task_id matches allowed pattern
    if not re.match(TASK_ID_PATTERN, task_id):
        raise ValueError(
            "Task ID must contain only alphanumeric characters, hyphens, and underscores"
        )

    return task_id


def validate_file_size(file_size: int) -> None:
    """
    Validate file size against maximum allowed size.

    Args:
        file_size: Size of the file in bytes

    Raises:
        ValueError: If file size exceeds maximum allowed size
    """
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024*1024*1024):.1f}GB"
        )


def validate_filename(filename: str) -> str:
    """
    Validate and sanitize filename.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename

    Raises:
        ValueError: If filename is invalid
    """
    if not filename:
        raise ValueError("Filename is required")

    if len(filename) > MAX_FILENAME_LENGTH:
        raise ValueError(f"Filename too long (max {MAX_FILENAME_LENGTH} characters)")

    # Check for dangerous patterns in filename
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, filename):
            raise ValueError(f"Filename contains invalid characters: {pattern}")

    return filename


def validate_file_extension(filename: str, allowed_extensions: Set[str]) -> None:
    """
    Validate file extension against allowed extensions.

    Args:
        filename: Filename to validate
        allowed_extensions: Set of allowed file extensions (without leading dot)

    Raises:
        ValueError: If file extension is not allowed
    """
    if not filename or "." not in filename:
        raise ValueError("Invalid filename or missing extension")

    extension = os.path.splitext(filename)[1].lower().lstrip(".")
    if extension not in allowed_extensions:
        allowed_extensions_str = ", ".join(sorted(allowed_extensions))
        raise ValueError(
            f"File extension '{extension}' is not allowed. Allowed extensions: {allowed_extensions_str}"
        )


def validate_mime_type(file_content: bytes, filename: str, file_type: str) -> None:
    """
    Validate file MIME type against allowed types.

    Args:
        file_content: File content bytes
        filename: Original filename
        file_type: Type of file being validated

    Raises:
        ValueError: If MIME type is not allowed
    """
    # Get MIME type from file content
    mime_type: Optional[str] = None
    try:
        import magic  # type: ignore

        mime_type = magic.from_buffer(file_content, mime=True)
    except ImportError:
        # Fallback to mimetypes if python-magic is not available
        mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"

    allowed_mime_types = ALLOWED_MIME_TYPES.get(file_type, set())

    if mime_type not in allowed_mime_types:
        allowed_mime_types_str = ", ".join(sorted(allowed_mime_types))
        raise ValueError(
            f"File MIME type '{mime_type}' is not allowed. Allowed MIME types: {allowed_mime_types_str}"
        )


def validate_upload_path(upload_path: str, base_upload_dir: str) -> None:
    """
    Validate that upload path is within the allowed directory.

    Args:
        upload_path: Path to validate
        base_upload_dir: Base upload directory

    Raises:
        ValueError: If path is outside allowed directory
    """
    real_base_dir = os.path.realpath(base_upload_dir)
    real_upload_path = os.path.realpath(upload_path)

    if not real_upload_path.startswith(real_base_dir):
        raise ValueError("Upload path is outside allowed directory")


def sanitize_path(path: str) -> str:
    """
    Sanitize file path to prevent path traversal.

    Args:
        path: Path to sanitize

    Returns:
        Sanitized path
    """
    # Remove any null bytes
    path = path.replace("\x00", "")

    # Normalize path separators
    path = path.replace("\\", "/")

    # Remove any leading/trailing whitespace
    path = path.strip()

    # Remove any dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        path = re.sub(pattern, "", path)

    return path


def normalize_file_type(
    file_type: Optional[str], default: str, supported: Set[str]
) -> str:
    """
    Normalize and validate file type with a default and supported set.
    """
    normalized = (file_type or default).lower()
    if normalized not in supported:
        raise ValueError(f"Unsupported file type: {file_type or 'unknown'}")
    return normalized


def normalize_relative_upload_path(file_path: str, base_upload_dir: str) -> str:
    """
    Normalize upload file paths to a relative path under base_upload_dir.
    Handles legacy absolute prefixes safely.
    """
    if not file_path or file_path.strip() == "":
        return ""

    normalized_base = os.path.realpath(base_upload_dir).rstrip("/") + "/"
    docker_prefix = "/app/upload_files/"
    root_prefix = "/upload_files/"

    if file_path.startswith(normalized_base):
        return file_path.replace(normalized_base, "", 1)
    if file_path.startswith(docker_prefix):
        return file_path.replace(docker_prefix, "", 1)
    if file_path.startswith(root_prefix):
        return file_path.replace(root_prefix, "", 1)

    logger.debug("Returning original path without normalization: {}", file_path)
    return file_path
