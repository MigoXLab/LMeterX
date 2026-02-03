"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Path configuration for the stress testing engine.
"""

import os

# === BASE PATHS ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ST_ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# === LOG PATHS ===
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_TASK_DIR = os.path.join(LOG_DIR, "task")

# === DATA PATHS ===
DATA_DIR = os.path.join(ST_ENGINE_DIR, "data")
PROMPTS_DIR = os.path.join(DATA_DIR, "prompts")
IMAGES_DIR = os.path.join(DATA_DIR, "pic")

# === UPLOAD PATHS ===
# Handle different environments: Docker vs local development
if os.path.exists("/app") and os.getcwd().startswith("/app"):
    # Docker environment: use /app/upload_files
    UPLOAD_FOLDER = "/app/upload_files"
else:
    # Local development: use project root upload_files
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "upload_files")

# === TASK STATUS CONSTANTS ===
TASK_STATUS_CREATED = "created"
TASK_STATUS_LOCKED = "locked"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_STOPPING = "stopping"
TASK_STATUS_STOPPED = "stopped"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = (
    "failed"  # General execution failures (Locust exit code >1 or other errors)
)
TASK_STATUS_FAILED_REQUESTS = (
    "failed_requests"  # Test completed but had failed requests (Locust exit code 1)
)

# === HTTP CONSTANTS ===
HTTP_OK = 200
DEFAULT_TIMEOUT = 180
DEFAULT_WAIT_TIME_MIN = 1
DEFAULT_WAIT_TIME_MAX = 3

# === DEFAULT VALUES ===
DEFAULT_PROMPT = "Tell me about the history of Artificial Intelligence."
DEFAULT_API_PATH = "/chat/completions"

# === STREAMING CONSTANTS ===
STREAM_END_MARKERS = ["[DONE]", "[END]", "DONE", "END"]
STREAM_ERROR_MARKERS = ["[ERROR]", "ERROR"]
MAX_CHUNK_SIZE = 1000  # Maximum chunk size to process
MAX_OUTPUT_LENGTH = 1000000  # Maximum output length to prevent memory issues

# === TIMING METRICS NAMES ===
METRIC_TTFOT = "Time_to_first_output_token"
METRIC_TTFRT = "Time_to_first_reasoning_token"
METRIC_TTRC = "Time_to_reasoning_completion"
METRIC_TTOC = "Time_to_output_completion"
METRIC_TTT = "Total_time"

# === LOCUST CONFIGURATION ===
LOCUST_STOP_TIMEOUT = 99
LOCUST_WAIT_TIMEOUT_BUFFER = 30

# === CONTENT TYPE ===
DEFAULT_CONTENT_TYPE = "application/json"

# === SENSITIVE DATA ===
SENSITIVE_KEYS = ["authorization"]

# === TOKENIZATION ===
# Token estimation
DEFAULT_TOKEN_RATIO = 4  # chars per token estimation
TOKENIZER_CACHE_SIZE = 128
TOKEN_COUNT_CACHE_SIZE = 8192

# === DATA VALIDATION ===
MAX_QUEUE_SIZE = 10000
MIN_PROMPT_LENGTH = 1
