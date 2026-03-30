"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import logging
import os
import sys

from dotenv import load_dotenv
from loguru import logger

from config.base import LOG_DIR, LOG_TASK_DIR

load_dotenv()
# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Logger Configuration ---

# Ensure the log directory exists.
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(LOG_TASK_DIR, exist_ok=True)


# Remove the default logger to prevent duplicate output.
logger.remove()


def is_system_log(record):
    """Filter for system logs (not task-related)."""
    return "task_id" not in record["extra"]


# Configure the file logger for system logs
logger.add(
    os.path.join(LOG_DIR, "engine.log"),  # Path to the log file.
    rotation="10 MB",  # Rotates the log file when it reaches 5 MB.
    retention="10 days",  # Retains log files for 10 days.
    compression="zip",  # Compresses rotated log files.
    encoding="utf-8",  # Sets the file encoding.
    level=LOG_LEVEL,  # Minimum log level to be written to the file.
    backtrace=False,  # Do not show the full stack trace.
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
    filter=is_system_log,  # Only log records without 'task_id'
    # enqueue=True,  # Asynchronous writing.
)

# Configure the console logger.
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
)


def setup_clean_log_format():
    """Override Locust's default log format to remove hostname and module name.

    Default Locust format:
        [%(asctime)s] %(hostname)s/%(levelname)s/%(name)s: %(message)s

    Clean format matching loguru pipe style for consistency:
        YYYY-MM-DD HH:MM:SS.mmm | LEVEL    | message

    Call this once inside a ``@events.init.add_listener`` callback.
    """
    clean_fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for handler in logging.root.handlers:
        handler.setFormatter(clean_fmt)


def add_task_log_sink(task_id: str) -> int:
    """
    Adds a specific log sink for a given task ID.
    """
    # Ensure the task log directory exists before creating the log file
    try:
        os.makedirs(LOG_TASK_DIR, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create task log directory {LOG_TASK_DIR}: {e}")

    task_log_file = os.path.join(LOG_TASK_DIR, f"task_{task_id}.log")

    def is_current_task_log(record):
        return "task_id" in record["extra"] and record["extra"]["task_id"] == task_id

    try:
        # Add a new handler to the existing logger instead of creating a new one
        handler_id = logger.add(
            task_log_file,
            rotation="20 MB",
            retention="10 days",
            compression="zip",
            encoding="utf-8",
            level="INFO",
            backtrace=True,  # Enable backtrace for task logs to help with debugging
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
            filter=is_current_task_log,
            enqueue=False,
        )

        # Test the logger to ensure it's working
        test_logger = logger.bind(task_id=task_id)
        test_logger.info(f"Task log initialized for task {task_id}")

        return handler_id
    except Exception as e:
        logger.error(f"Failed to create task log sink for task {task_id}: {e}")
        # Return a dummy handler ID to prevent downstream errors
        return -1


def remove_task_log_sink(handler_id: int):
    """
    Removes a log sink by its handler ID.
    """
    if handler_id > 0:  # Only remove valid handler IDs
        try:
            logger.remove(handler_id)
        except Exception as e:
            logger.warning(
                f"Failed to remove log sink with handler ID {handler_id}: {e}"
            )
    else:
        logger.warning(f"Skipping removal of invalid handler ID: {handler_id}")
