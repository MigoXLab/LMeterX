"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import os

# === BASE PATHS ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ST_ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Handle different environments: Docker vs local development
if os.path.exists("/app") and os.getcwd().startswith("/app"):
    # Docker environment: use /app/xxx
    LOG_DIR = "/app/logs"
    UPLOAD_FOLDER = "/app/upload_files"
    DATA_DIR = "/app/data"

else:
    # Local development
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "upload_files")
    DATA_DIR = os.path.join(BASE_DIR, "data")

# === LOG PATHS ===
LOG_TASK_DIR = os.path.join(LOG_DIR, "task")
# === IMAGES PATHS ===
IMAGES_DIR = os.path.join(DATA_DIR, "pic")

# === HTTP CONSTANTS ===
HTTP_OK = 200
DEFAULT_TIMEOUT = 120
DEFAULT_WAIT_TIME_MIN = 1
DEFAULT_WAIT_TIME_MAX = 2

# === DEFAULT VALUES ===
DEFAULT_PROMPT = "Tell me about the history of Artificial Intelligence."
DEFAULT_API_PATH = "/v1/chat/completions"
DEFAULT_CONTENT_TYPE = "application/json"

# === LOCUST CONFIGURATION ===
LOCUST_STOP_TIMEOUT = 60
LOCUST_WAIT_TIMEOUT_BUFFER = 30

# === DATA VALIDATION ===
MAX_QUEUE_SIZE = 10000

# === SENSITIVE DATA ===
SENSITIVE_KEYS = ["authorization"]

__all__ = [
    # paths
    "BASE_DIR",
    "ST_ENGINE_DIR",
    "LOG_DIR",
    "LOG_TASK_DIR",
    "DATA_DIR",
    "IMAGES_DIR",
    "UPLOAD_FOLDER",
    # http
    "HTTP_OK",
    "DEFAULT_TIMEOUT",
    "DEFAULT_WAIT_TIME_MIN",
    "DEFAULT_WAIT_TIME_MAX",
    "DEFAULT_PROMPT",
    "DEFAULT_API_PATH",
    "DEFAULT_CONTENT_TYPE",
    # locust
    "LOCUST_STOP_TIMEOUT",
    "LOCUST_WAIT_TIMEOUT_BUFFER",
    # sensitive
    "SENSITIVE_KEYS",
]
