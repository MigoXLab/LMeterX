"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

# === TASK STATUS CONSTANTS ===
TASK_STATUS_CREATED = "created"
TASK_STATUS_QUEUING = "queuing"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_STOPPING = "stopping"
TASK_STATUS_STOPPED = "stopped"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_FAILED_REQUESTS = (
    "failed_requests"  # Test completed but had failed requests (Locust exit code 1)
)

# === TIMING METRICS NAMES ===
METRIC_TTFOT = "Time_to_first_output_token"
METRIC_TTFRT = "Time_to_first_reasoning_token"
METRIC_TTRC = "Time_to_reasoning_completion"
METRIC_TTOC = "Time_to_output_completion"
METRIC_TTT = "Total_time"

__all__ = [
    # task status
    "TASK_STATUS_CREATED",
    "TASK_STATUS_QUEUING",
    "TASK_STATUS_RUNNING",
    "TASK_STATUS_STOPPING",
    "TASK_STATUS_STOPPED",
    "TASK_STATUS_COMPLETED",
    "TASK_STATUS_FAILED",
    "TASK_STATUS_FAILED_REQUESTS",
    # metrics
    "METRIC_TTFOT",
    "METRIC_TTFRT",
    "METRIC_TTRC",
    "METRIC_TTOC",
    "METRIC_TTT",
]
