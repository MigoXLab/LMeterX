"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Utility functions for cleaning up uploaded files associated with tasks.
"""

import os
from typing import List, Optional

from utils.be_config import UPLOAD_FOLDER
from utils.logger import logger


def cleanup_task_files(
    task_id: str,
    test_data_path: Optional[str] = None,
    cert_file_path: Optional[str] = None,
    key_file_path: Optional[str] = None,
) -> List[str]:
    """
    Clean up uploaded files associated with a task.

    Args:
        task_id: The ID of the task for logging purposes.
        test_data_path: Path to the test data file (dataset).
        cert_file_path: Path to the certificate file.
        key_file_path: Path to the private key file.

    Returns:
        List of successfully removed file paths.
    """
    task_logger = logger.bind(task_id=task_id)
    files_to_remove = []
    successfully_removed = []

    # Collect all file paths associated with this task
    if test_data_path and test_data_path.strip():
        # Only add actual file paths, not default dataset or JSONL content
        if test_data_path not in ["default", ""]:
            if not test_data_path.strip().startswith("{"):  # Not JSONL content
                files_to_remove.append(test_data_path)

    if cert_file_path and cert_file_path.strip():
        files_to_remove.append(cert_file_path)

    if key_file_path and key_file_path.strip():
        files_to_remove.append(key_file_path)

    # Remove each file if it exists
    for file_path in files_to_remove:
        try:
            # Ensure we're working with absolute paths
            if not os.path.isabs(file_path):
                file_path = os.path.join(UPLOAD_FOLDER, file_path)

            if os.path.exists(file_path):
                os.remove(file_path)
                successfully_removed.append(file_path)
                task_logger.info(f"Successfully removed file: {file_path}")
            else:
                task_logger.debug(f"File not found for cleanup: {file_path}")

        except Exception as e:
            task_logger.warning(f"Failed to remove file {file_path}: {e}")

    if successfully_removed:
        task_logger.info(
            f"File cleanup completed for task {task_id}. Removed {len(successfully_removed)} files."
        )
    else:
        task_logger.debug(f"No files to clean up for task {task_id}.")

    return successfully_removed


def cleanup_task_files_by_temp_id(temp_task_id: str) -> List[str]:
    """
    Clean up uploaded files associated with a temporary task ID.
    This is useful for cleaning up files when task creation fails.

    Args:
        temp_task_id: The temporary task ID used during file upload.

    Returns:
        List of successfully removed file paths.
    """
    logger_context = logger.bind(temp_task_id=temp_task_id)
    successfully_removed = []

    try:
        # Look for files in the upload directory that match the temp task ID pattern
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if temp_task_id in filename:
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            successfully_removed.append(file_path)
                            logger_context.info(
                                f"Successfully removed temp file: {file_path}"
                            )
                    except Exception as e:
                        logger_context.warning(
                            f"Failed to remove temp file {file_path}: {e}"
                        )

        if successfully_removed:
            logger_context.info(
                f"Temp file cleanup completed for {temp_task_id}. Removed {len(successfully_removed)} files."
            )
        else:
            logger_context.debug(f"No temp files found to clean up for {temp_task_id}.")

    except Exception as e:
        logger_context.error(f"Error during temp file cleanup for {temp_task_id}: {e}")

    return successfully_removed
