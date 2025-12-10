"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import uuid
from typing import Any, Collection, Dict, List, Optional, Sequence, cast

import aiofiles  # type: ignore[import-untyped]
from fastapi import Request, UploadFile
from werkzeug.utils import secure_filename

from model.upload import UploadedFileInfo, UploadFileRsp
from utils.be_config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, UPLOAD_FOLDER
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger
from utils.security import (
    safe_join,
    validate_file_extension,
    validate_filename,
    validate_mime_type,
    validate_task_id,
    validate_upload_path,
)

# Chunk size for streaming upload (1MB)
CHUNK_SIZE = 1024 * 1024
HEADER_READ_BYTES = 1024
DEFAULT_FILE_TYPE = "dataset"
SUPPORTED_FILE_TYPES = {"cert", "dataset"}

FileInfo = Dict[str, Any]

# In-memory dictionary to store certificate configurations per task.
_task_cert_configs: Dict[str, Dict[str, str]] = {}


def _require_files(files: Sequence[UploadFile]) -> None:
    first_valid = next((file for file in files if file and file.filename), None)
    if not first_valid:
        raise ErrorResponse.bad_request(ErrorMessages.NO_FILES_PROVIDED)
    logger.info("Uploading file: {}", first_valid.filename)


def _normalize_file_type(file_type: Optional[str]) -> str:
    normalized = (file_type or DEFAULT_FILE_TYPE).lower()
    if normalized not in SUPPORTED_FILE_TYPES:
        raise ErrorResponse.bad_request(
            f"{ErrorMessages.UNSupported_FILE_TYPE}: {file_type or 'unknown'}"
        )
    return normalized


def _resolve_task_identifier(task_id: Optional[str]) -> str:
    if not task_id:
        return str(uuid.uuid4())
    try:
        return validate_task_id(task_id)
    except ValueError as exc:
        logger.error("Task ID validation failed: {}", exc)
        raise ErrorResponse.bad_request(str(exc))


def _prepare_upload_directory(task_id: str) -> str:
    try:
        task_upload_dir = safe_join(UPLOAD_FOLDER, task_id)
        validate_upload_path(task_upload_dir, UPLOAD_FOLDER)
        os.makedirs(task_upload_dir, exist_ok=True)
        return task_upload_dir
    except ValueError as exc:
        raise ErrorResponse.bad_request(str(exc)) from exc


async def _validate_and_save_file(
    file: UploadFile,
    upload_dir: str,
    allowed_extensions: Collection[str],
    header_type: str,
    log_label: str,
) -> FileInfo:
    if not file.filename:
        raise ErrorResponse.bad_request(ErrorMessages.NO_FILES_PROVIDED)

    filename_input = cast(str, file.filename)

    try:
        validated_filename = validate_filename(filename_input)
        validate_file_extension(validated_filename, set(allowed_extensions))
        await validate_file_header(file, validated_filename, header_type)

        filename = secure_filename(validated_filename)
        absolute_file_path = safe_join(upload_dir, filename)
        validate_upload_path(absolute_file_path, UPLOAD_FOLDER)

        file_size = await save_file_stream(file, absolute_file_path)
        logger.info(
            "{} file uploaded successfully: {}, size: {} bytes",
            log_label.capitalize(),
            filename,
            file_size,
        )
        return {
            "originalname": filename,
            "path": absolute_file_path,
            "size": file_size,
        }
    except ValueError as exc:
        raise ErrorResponse.bad_request(str(exc)) from exc


async def _collect_uploaded_files(
    files: Sequence[UploadFile],
    upload_dir: str,
    allowed_extensions: Collection[str],
    header_type: str,
    log_label: str,
) -> List[FileInfo]:
    uploaded_files: List[FileInfo] = []
    for file in files:
        if not file or not file.filename:
            continue
        file_info = await _validate_and_save_file(
            file,
            upload_dir,
            allowed_extensions,
            header_type,
            log_label,
        )
        uploaded_files.append(file_info)
    return uploaded_files


def save_task_cert_config(task_id: str, config: Dict[str, str]):
    """Saves the certificate configuration for a specific task."""
    _task_cert_configs[task_id] = config


def get_task_cert_config(task_id: str) -> Dict[str, str]:
    """Retrieves the certificate configuration for a specific task."""
    return _task_cert_configs.get(task_id, {"cert_file": "", "key_file": ""})


async def save_file_stream(file: UploadFile, file_path: str) -> int:
    """
    Process the file stream and save it to the file system.

    Args:
        file: FastAPI UploadFile object
        file_path: target file path

    Returns:
        int: saved file size
    """
    total_size = 0

    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(CHUNK_SIZE):
            await f.write(chunk)
            total_size += len(chunk)

            # Real-time check file size to avoid uploading too large files
            if total_size > MAX_FILE_SIZE:
                # Delete partially uploaded files
                await f.close()
                if os.path.exists(file_path):
                    os.remove(file_path)
                max_size_gb = MAX_FILE_SIZE / (1024 * 1024 * 1024)
                raise ErrorResponse.bad_request(
                    ErrorMessages.VALIDATION_ERROR,
                    details=(
                        f"File size exceeds maximum allowed size of {max_size_gb:.1f}GB"
                    ),
                )

    return total_size


async def validate_file_header(file: UploadFile, filename: str, file_type: str) -> None:
    """
    Validate file header information, only read the beginning part of the file for MIME type check

    Args:
        file: UploadFile object
        filename: filename
        file_type: file type ('cert' or 'dataset')
    """
    # Only read the first HEADER_READ_BYTES of the file for MIME type check
    current_position = file.file.tell()
    header_content = await file.read(HEADER_READ_BYTES)
    await file.seek(current_position)  # Reset file pointer

    # Validate MIME type based on file content and filename
    validate_mime_type(header_content, filename, file_type)


def determine_cert_config(
    files: List[Dict[str, Any]],
    cert_type: Optional[str] = None,
    existing_config: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Determines the certificate configuration based on uploaded files and specified type.
    It preserves existing configurations if not overridden.

    Args:
        files: A list of dictionaries, each representing an uploaded file.
        cert_type: The type of certificate ('combined', 'cert_file', 'key_file').
        existing_config: The existing certificate configuration for the task.

    Returns:
        An updated dictionary with 'cert_file' and 'key_file' paths.
    """
    config = existing_config if existing_config else {"cert_file": "", "key_file": ""}

    if not files:
        return config

    if cert_type == "combined":
        # A combined file (e.g., PEM) overrides both cert and key.
        config["cert_file"] = files[0]["path"]
        config["key_file"] = ""
    elif cert_type == "cert_file":
        # Updates only the certificate file, preserving the key file.
        config["cert_file"] = files[0]["path"]
    elif cert_type == "key_file":
        # Updates only the key file, preserving the certificate file.
        config["key_file"] = files[0]["path"]
    else:
        logger.warning("Certificate type not specified or invalid: {}", cert_type)

    return config


async def process_cert_files(
    task_id: str, files: List[UploadFile], cert_type: Optional[str]
):
    """
    Processes uploaded certificate and key files, saves them, and determines the configuration.

    Args:
        task_id: The ID of the task.
        files: The list of uploaded files.
        cert_type: The type of certificate being uploaded.

    Returns:
        A tuple containing the list of uploaded file info and the certificate configuration.
    """
    try:
        task_upload_dir = _prepare_upload_directory(task_id)
        uploaded_files_info = await _collect_uploaded_files(
            files,
            task_upload_dir,
            ALLOWED_EXTENSIONS["cert"],
            "cert",
            "certificate",
        )

        existing_config = get_task_cert_config(task_id)
        cert_config = determine_cert_config(
            uploaded_files_info, cert_type, existing_config
        )
        save_task_cert_config(task_id, cert_config)

        return uploaded_files_info, cert_config
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Error processing certificate files: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.FILE_UPLOAD_FAILED)


async def process_dataset_files(task_id: str, files: List[UploadFile]):
    """
    Processes uploaded dataset files, saves them, and returns file information.


    Args:
        task_id: The ID of the task.
        files: The list of uploaded files.

    Returns:
        A tuple containing the list of uploaded file info and the file path.
    """
    try:
        task_upload_dir = _prepare_upload_directory(task_id)
        uploaded_files_info = await _collect_uploaded_files(
            files,
            task_upload_dir,
            ALLOWED_EXTENSIONS["dataset"],
            "dataset",
            "dataset",
        )
        file_path = uploaded_files_info[-1]["path"] if uploaded_files_info else None
        return uploaded_files_info, file_path
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Error processing dataset files: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.FILE_UPLOAD_FAILED)


async def upload_file_svc(
    request: Request,
    task_id: Optional[str],
    file_type: Optional[str],
    cert_type: Optional[str],
    files: List[UploadFile],
):
    """
    Main service function for handling file uploads.

    It validates the request, generates a task ID if not provided, and routes
    the processing to the appropriate handler based on the file type.
    """
    _require_files(files)

    normalized_file_type = _normalize_file_type(file_type)
    effective_task_id = _resolve_task_identifier(task_id)

    if normalized_file_type == "cert":
        uploaded_files, cert_config = await process_cert_files(
            effective_task_id, files, cert_type
        )
        return UploadFileRsp(
            message="Files uploaded successfully",
            task_id=effective_task_id,
            files=[UploadedFileInfo(**f) for f in uploaded_files],
            cert_config=cert_config,
        )

    uploaded_files, file_path = await process_dataset_files(effective_task_id, files)
    return UploadFileRsp(
        message="Dataset files uploaded successfully",
        task_id=effective_task_id,
        files=[UploadedFileInfo(**f) for f in uploaded_files],
        test_data=file_path,
    )
