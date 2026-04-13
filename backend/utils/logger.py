"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os
import sys

from loguru import logger

from utils.be_config import LOG_DIR

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- Logger Configuration ---

# Remove the default logger configuration to avoid duplicate output.
logger.remove()

# Check if we're in testing environment
if not os.environ.get("TESTING"):
    # Ensure the log directory exists.
    os.makedirs(LOG_DIR, exist_ok=True)

    # Configure file logging only if not in testing mode.
    logger.add(
        os.path.join(LOG_DIR, "backend.log"),
        rotation="5 MB",
        retention="10 days",
        compression="zip",
        encoding="utf-8",
        level=LOG_LEVEL,
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {message}",
    )

# Configure console logging.
# colorize=None lets loguru auto-detect: colors ON for interactive TTY (local dev),
# colors OFF for non-TTY (Docker/K8S) to avoid ANSI escape codes showing as garbled blocks.
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    colorize=None,
    backtrace=False,
    diagnose=False,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",  # noqa: E501
)
