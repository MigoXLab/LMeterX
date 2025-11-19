"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

# base
from .base import *

# business
from .business import *

# multiprocess
from .multiprocess import *

# backward compatibility
__all__ = [
    # base
    "BASE_DIR",
    "ST_ENGINE_DIR",
    "LOG_DIR",
    "LOG_TASK_DIR",
    "DATA_DIR",
    "IMAGES_DIR",
    "UPLOAD_FOLDER",
    "HTTP_OK",
    "DEFAULT_TIMEOUT",
    "DEFAULT_WAIT_TIME_MIN",
    "DEFAULT_WAIT_TIME_MAX",
    "DEFAULT_PROMPT",
    "DEFAULT_API_PATH",
    "DEFAULT_CONTENT_TYPE",
    "LOCUST_STOP_TIMEOUT",
    "LOCUST_WAIT_TIMEOUT_BUFFER",
    "MAX_QUEUE_SIZE",
    "SENSITIVE_KEYS",
    # multiprocess
    "get_cpu_count",
    "get_multiprocessing_config",
    "should_enable_multiprocess",
    "should_use_multiprocessing_manager",
    "get_process_count",
    "get_fallback_queue_type",
    "DEFAULT_ENABLE_MULTIPROCESS",
    "DEFAULT_PROCESS_COUNT",
    "MULTIPROCESS_THRESHOLD",
    "MIN_USERS_PER_PROCESS",
    # business
    "TASK_STATUS_CREATED",
    "TASK_STATUS_LOCKED",
    "TASK_STATUS_RUNNING",
    "TASK_STATUS_STOPPING",
    "TASK_STATUS_STOPPED",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_FAILED",
    "TASK_STATUS_FAILED_REQUESTS",
]
