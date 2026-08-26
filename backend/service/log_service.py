"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import os.path
import re
import tempfile
import zipfile

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from model.log import LogContentResponse
from service.oss_service import OSS_ENABLED, download_file_from_oss, list_files_in_oss
from utils.be_config import LOG_DIR
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger


async def _ensure_engine_logs_from_oss(
    task_id: str, resolved_task_log_dir: str, all_files: bool = False
) -> bool:
    if not OSS_ENABLED:
        return False

    os.makedirs(resolved_task_log_dir, exist_ok=True)

    if not all_files:
        main_log_path = os.path.join(
            resolved_task_log_dir, f"task_{task_id}_engine.log"
        )
        detail_log_path = os.path.join(
            resolved_task_log_dir, f"task_{task_id}_engine_detail.log"
        )

        # Always re-download to get latest content (engine overwrites each cycle)
        main_downloaded = await download_file_from_oss(
            f"logs/task_{task_id}_engine.log", main_log_path
        )
        detail_downloaded = await download_file_from_oss(
            f"logs/task_{task_id}_engine_detail.log", detail_log_path
        )
        if not main_downloaded and os.path.exists(main_log_path):
            os.remove(main_log_path)
        if not detail_downloaded and os.path.exists(detail_log_path):
            os.remove(detail_log_path)
        return main_downloaded
    else:
        # download all files in oss
        prefix = f"logs/task_{task_id}_"
        oss_keys = list_files_in_oss(prefix)
        downloaded_any = False
        expected_filenames = {os.path.basename(key) for key in oss_keys}

        for filename in os.listdir(resolved_task_log_dir):
            if (
                filename.startswith(f"task_{task_id}_")
                and filename not in expected_filenames
            ):
                os.remove(os.path.join(resolved_task_log_dir, filename))

        for key in oss_keys:
            filename = os.path.basename(key)
            local_path = os.path.join(resolved_task_log_dir, filename)

            downloaded = await download_file_from_oss(key, local_path)
            if downloaded:
                downloaded_any = True
            elif os.path.exists(local_path):
                os.remove(local_path)

        return downloaded_any


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
    if n <= 0:
        return ""

    try:
        with open(file_path, "rb") as f:
            # For small files, just read all and return last n lines
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

            # If file is small (< 50KB), read all lines and return last n
            if file_size < 50 * 1024:
                f.seek(0)
                all_lines = f.read().decode("utf-8", errors="replace").splitlines(True)
                return "".join(all_lines[-n:]) if all_lines else ""

            # For larger files, read enough chunks from the end and split with
            # keepends=True so a trailing newline is not counted as an extra line.
            chunks: list[bytes] = []
            newline_count = 0
            position = file_size
            buffer_size = 8192

            while position > 0 and newline_count <= n:
                # Calculate how much to read
                chunk_size = min(buffer_size, position)
                position -= chunk_size

                # Read chunk from current position
                f.seek(position)
                chunk_bytes: bytes = f.read(chunk_size)
                chunks.append(chunk_bytes)
                newline_count += chunk_bytes.count(b"\n")

            if not chunks:
                return ""

            data = b"".join(reversed(chunks))
            result = b"".join(data.splitlines(keepends=True)[-n:])
            return result.decode("utf-8", errors="replace")

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
        with open(log_file_path, "rb") as f:
            if offset > 0:
                f.seek(offset)
            content: str = f.read().decode("utf-8", errors="replace")
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


async def get_engine_system_log_svc(
    engine_id: str, cluster_id: str, offset: int, tail: int
):
    """Get engine system log content for a specific engine.

    When OSS is enabled, downloads the log snapshot pushed by the engine.
    Otherwise falls back to the local engine.log (single-cluster dev mode).
    """
    if not engine_id or not _SAFE_NAME_PATTERN.match(engine_id):
        raise ErrorResponse.bad_request("Invalid engine ID")
    if not cluster_id or not _SAFE_NAME_PATTERN.match(cluster_id):
        raise ErrorResponse.bad_request("Invalid cluster ID")

    if cluster_id == "local":
        log_file_path = os.path.join(LOG_DIR, f"engine_{engine_id}.log")
        resolved_path = os.path.realpath(log_file_path)
        log_dir_real = os.path.realpath(LOG_DIR) + os.sep
        if not resolved_path.startswith(log_dir_real):
            raise ErrorResponse.bad_request("Invalid engine ID")

        if not os.path.exists(resolved_path):
            try:
                return await get_service_log_svc("engine", offset, tail)
            except ErrorResponse as e:
                if e.status_code == 404:
                    return LogContentResponse(content="", file_size=0)
                raise

        try:
            content = read_local_file(resolved_path, tail, offset)
            file_size = os.path.getsize(resolved_path)
            return LogContentResponse(content=content, file_size=file_size)
        except Exception as e:
            logger.error("Failed to read local engine log {}: {}", resolved_path, e)
            raise ErrorResponse.internal_server_error(
                ErrorMessages.LOG_FILE_READ_FAILED
            )

    if OSS_ENABLED:
        cache_dir = os.path.join(LOG_DIR, "engine_cache")
        os.makedirs(cache_dir, exist_ok=True)
        local_cache = os.path.join(cache_dir, f"{cluster_id}_{engine_id}_engine.log")

        oss_key = f"logs/system/{cluster_id}/{engine_id}/engine.log"
        downloaded = await download_file_from_oss(oss_key, local_cache)
        if not downloaded:
            if os.path.exists(local_cache):
                logger.warning(
                    f"Engine log refresh failed for engine '{engine_id}' in cluster "
                    f"'{cluster_id}', serving cached snapshot"
                )
            else:
                logger.warning(
                    f"Engine log not downloaded for engine '{engine_id}' "
                    f"in cluster '{cluster_id}'"
                )
                return LogContentResponse(content="", file_size=0)

        if not os.path.exists(local_cache):
            logger.warning(
                f"Engine log not found for engine '{engine_id}' in cluster '{cluster_id}'"
            )
            return LogContentResponse(content="", file_size=0)

        try:
            content = read_local_file(local_cache, tail, offset)
            file_size = os.path.getsize(local_cache)
            return LogContentResponse(content=content, file_size=file_size)
        except Exception as e:
            logger.error("Failed to read engine log cache {}: {}", local_cache, e)
            raise ErrorResponse.internal_server_error(
                ErrorMessages.LOG_FILE_READ_FAILED
            )
    else:
        try:
            return await get_service_log_svc("engine", offset, tail)
        except ErrorResponse as e:
            if e.status_code == 404:
                return LogContentResponse(content="", file_size=0)
            raise


def _read_backend_task_log(task_id: str, tail: int, offset: int) -> LogContentResponse:
    backend_log_path = os.path.join(LOG_DIR, "backend.log")
    resolved_path = os.path.realpath(backend_log_path)
    log_dir_real = os.path.realpath(LOG_DIR) + os.sep
    if not resolved_path.startswith(log_dir_real):
        raise ErrorResponse.bad_request("Invalid backend log path")

    if not os.path.exists(resolved_path):
        return LogContentResponse(content="", file_size=0)

    with open(resolved_path, "rb") as f:
        raw_content = f.read().decode("utf-8", errors="replace")

    lines = [line for line in raw_content.splitlines(True) if task_id in line]
    filtered_content = "".join(lines)

    if tail > 0:
        filtered_content = "".join(filtered_content.splitlines(True)[-tail:])
    elif offset > 0:
        filtered_content = filtered_content.encode("utf-8")[offset:].decode(
            "utf-8", errors="replace"
        )

    file_size = len(filtered_content.encode("utf-8"))
    log_url = f"/logs/task/{task_id}/download?source=backend"
    return LogContentResponse(
        content=filtered_content, file_size=file_size, log_url=log_url
    )


async def get_task_log_svc(
    task_id: str, offset: int, tail: int, source: str = "engine"
):
    """
    Service function to get the log content for a given task ID.

    It constructs the log file path, checks for its existence, and reads the content
    based on the offset and tail parameters.
    """
    if not task_id:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_ID_EMPTY)

    if not _SAFE_NAME_PATTERN.match(task_id):
        raise ErrorResponse.bad_request("Invalid task ID")

    if source not in ["engine", "backend"]:
        raise ErrorResponse.bad_request("Invalid log source")

    log_file_path = os.path.join(LOG_DIR, "task", f"task_{task_id}_{source}.log")

    # Ensure resolved path stays within LOG_DIR to prevent path traversal
    resolved_path = os.path.realpath(log_file_path)
    log_dir_real = os.path.realpath(LOG_DIR) + os.sep
    if not resolved_path.startswith(log_dir_real):
        raise ErrorResponse.bad_request("Invalid task ID")

    if source == "engine" and OSS_ENABLED:
        downloaded = await _ensure_engine_logs_from_oss(
            task_id, os.path.dirname(resolved_path)
        )
        if not downloaded:
            log_url = f"/logs/task/{task_id}/download?source={source}"
            return LogContentResponse(content="", file_size=0, log_url=log_url)

    if not os.path.exists(resolved_path):
        logger.warning("Log file not found for task: {}", task_id)
        if source == "engine" and OSS_ENABLED:
            log_url = f"/logs/task/{task_id}/download?source={source}"
            return LogContentResponse(content="", file_size=0, log_url=log_url)
        if source == "backend":
            try:
                return _read_backend_task_log(task_id, tail, offset)
            except Exception as e:
                logger.error("Failed to read backend task log for {}: {}", task_id, e)
                raise ErrorResponse.internal_server_error(
                    ErrorMessages.LOG_FILE_READ_FAILED
                )
        raise ErrorResponse.not_found(f"Log file for task '{task_id}' not found")

    try:
        content = read_local_file(log_file_path, tail, offset)
        file_size = os.path.getsize(log_file_path)
        log_url = f"/logs/task/{task_id}/download?source={source}"
        return LogContentResponse(content=content, file_size=file_size, log_url=log_url)
    except Exception as e:
        logger.error("Failed to read log file {}: {}", log_file_path, e)
        raise ErrorResponse.internal_server_error(ErrorMessages.LOG_FILE_READ_FAILED)


def _find_engine_log_files(resolved_task_log_dir: str, task_id: str) -> list[str]:
    related_files = set()
    prefix_detail = f"task_{task_id}_engine_detail.log"
    prefix_detail_rotated = f"task_{task_id}_engine_detail."
    prefix_legacy_detail = f"task_{task_id}_detail.log"
    prefix_legacy_detail_rotated = f"task_{task_id}_detail."

    prefix_main = f"task_{task_id}_engine.log"
    prefix_main_rotated = f"task_{task_id}_engine."
    prefix_legacy_main = f"task_{task_id}.log"
    prefix_legacy_rotated = f"task_{task_id}."

    for filename in os.listdir(resolved_task_log_dir):
        if (
            filename == prefix_detail
            or filename.startswith(prefix_detail_rotated)
            or filename == prefix_legacy_detail
            or filename.startswith(prefix_legacy_detail_rotated)
        ):
            related_files.add(os.path.join(resolved_task_log_dir, filename))

    for filename in os.listdir(resolved_task_log_dir):
        if (
            filename == prefix_main
            or filename.startswith(prefix_main_rotated)
            or filename == prefix_legacy_main
            or (
                filename.startswith(prefix_legacy_rotated)
                and "detail" not in filename
                and "engine" not in filename
                and "backend" not in filename
            )
        ):
            related_files.add(os.path.join(resolved_task_log_dir, filename))

    return sorted(related_files)


def _find_backend_log_files(resolved_task_log_dir: str, task_id: str) -> list[str]:
    related_files = []
    prefix_main = f"task_{task_id}_backend.log"
    prefix_main_rotated = f"task_{task_id}_backend."

    for filename in os.listdir(resolved_task_log_dir):
        if filename == prefix_main or filename.startswith(prefix_main_rotated):
            related_files.append(os.path.join(resolved_task_log_dir, filename))
    return related_files


def _find_task_log_files(
    resolved_task_log_dir: str, task_id: str, source: str
) -> list[str]:
    if source == "engine":
        return _find_engine_log_files(resolved_task_log_dir, task_id)
    if source == "backend":
        return _find_backend_log_files(resolved_task_log_dir, task_id)
    return []


def _cleanup_temp_path(temp_path: str, description: str):
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception as e:
        logger.error("Failed to delete temp {} {}: {}", description, temp_path, e)


def _backend_task_log_download_response(task_id: str):
    backend_log = _read_backend_task_log(task_id, tail=0, offset=0)
    if not backend_log.content:
        return None

    temp_fd, temp_log_path = tempfile.mkstemp(
        suffix=".log", prefix=f"task_{task_id}_backend_"
    )
    os.close(temp_fd)

    with open(temp_log_path, "w", encoding="utf-8") as f:
        f.write(backend_log.content)

    return FileResponse(
        path=temp_log_path,
        filename=f"task_{task_id}_backend.log",
        media_type="text/plain",
        background=BackgroundTask(
            lambda: _cleanup_temp_path(temp_log_path, "backend log file")
        ),
    )


def _zip_task_log_files(task_id: str, related_files: list[str]):
    temp_fd, temp_zip_path = tempfile.mkstemp(
        suffix=".zip", prefix=f"task_{task_id}_logs_"
    )
    os.close(temp_fd)

    try:
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in related_files:
                zipf.write(file_path, arcname=os.path.basename(file_path))

        return FileResponse(
            path=temp_zip_path,
            filename=f"task_{task_id}_logs.zip",
            media_type="application/zip",
            background=BackgroundTask(
                lambda: _cleanup_temp_path(temp_zip_path, "zip file")
            ),
        )
    except Exception as e:
        _cleanup_temp_path(temp_zip_path, "zip file")
        logger.error("Failed to create zip file for task {}: {}", task_id, e)
        raise ErrorResponse.internal_server_error(
            "Failed to package log files for download"
        )


async def download_task_log_svc(task_id: str, source: str = "engine"):
    """
    Download the full log file for a given task ID based on the log source.
    If logs have rotated or detail logs exist, package all of them into a zip file.
    """
    if not task_id:
        raise ErrorResponse.bad_request(ErrorMessages.TASK_ID_EMPTY)

    if not _SAFE_NAME_PATTERN.match(task_id):
        raise ErrorResponse.bad_request("Invalid task ID")

    if source not in ["engine", "backend"]:
        raise ErrorResponse.bad_request("Invalid log source")

    task_log_dir = os.path.join(LOG_DIR, "task")
    log_dir_real = os.path.realpath(LOG_DIR) + os.sep
    resolved_task_log_dir = os.path.realpath(task_log_dir)

    if not resolved_task_log_dir.startswith(log_dir_real):
        raise ErrorResponse.bad_request("Invalid task ID")

    if source == "engine" and OSS_ENABLED:
        await _ensure_engine_logs_from_oss(
            task_id, resolved_task_log_dir, all_files=True
        )

    if not os.path.exists(resolved_task_log_dir):
        logger.warning("Task log directory not found")
        raise ErrorResponse.not_found(f"Log directory for task '{task_id}' not found")

    related_files = _find_task_log_files(resolved_task_log_dir, task_id, source)

    if not related_files:
        if source == "backend":
            response = _backend_task_log_download_response(task_id)
            if response is not None:
                return response

        logger.warning("Log files not found for task: {}", task_id)
        raise ErrorResponse.not_found(f"Log file for task '{task_id}' not found")

    # If there's only one file and it's a plain log, return it directly
    if len(related_files) == 1 and related_files[0].endswith(".log"):
        return FileResponse(
            path=related_files[0],
            filename=os.path.basename(related_files[0]),
            media_type="text/plain",
        )

    return _zip_task_log_files(task_id, related_files)
