"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import time
from typing import Any, Dict, List

from core import GlobalStateManager, TokenStats

from utils.logger import logger


class StatsManager:
    """Statistics manager"""

    def __init__(self):
        self.global_state = GlobalStateManager()
        self.task_logger = self.global_state.get_task_logger()

    def update_stats(
        self, reqs: int = 1, completion_tokens: int = 0, all_tokens: int = 0
    ):
        """Update statistics"""
        # Update statistics in memory in single process or Master mode
        self.global_state.token_stats.reqs_count += reqs
        self.global_state.token_stats.completion_tokens += completion_tokens
        self.global_state.token_stats.all_tokens += all_tokens

    def send_stats_to_master(
        self, runner, reqs: int = 1, completion_tokens: int = 0, all_tokens: int = 0
    ):
        """Send statistics to master"""
        try:
            if hasattr(runner, "send_message"):
                runner.send_message(
                    "token_stats",
                    {
                        "reqs": reqs,
                        "completion_tokens": completion_tokens,
                        "all_tokens": all_tokens,
                    },
                )
        except Exception as e:
            self.task_logger.error(f"Failed to send stats to master: {e}")

    def get_final_stats(self) -> Dict[str, Any]:
        """Get final statistics"""
        stats = self.global_state.token_stats
        start_time = self.global_state.start_time
        end_time = time.time()

        execution_time = max(end_time - start_time, 0.001) if start_time else 60.0

        return {
            "reqs_count": stats.reqs_count,
            "completion_tokens": stats.completion_tokens,
            "all_tokens": stats.all_tokens,
            "req_throughput": (
                stats.reqs_count / execution_time if execution_time > 0 else 0
            ),
            "completion_tps": (
                stats.completion_tokens / execution_time if execution_time > 0 else 0
            ),
            "total_tps": stats.all_tokens / execution_time if execution_time > 0 else 0,
            "avg_completion_tokens_per_req": (
                stats.completion_tokens / stats.reqs_count
                if stats.reqs_count > 0
                else 0
            ),
            "avg_total_tokens_per_req": (
                stats.all_tokens / stats.reqs_count if stats.reqs_count > 0 else 0
            ),
            "execution_time": execution_time,
        }

    def get_locust_stats(self, task_id: str, environment_stats) -> List[Dict[str, Any]]:
        """Gets and formats Locust statistics for database use.

        Args:
            task_id: Task identifier
            environment_stats: Locust environment statistics

        Returns:
            List of formatted metrics dictionaries
        """
        all_metrics_list = []

        try:
            from datetime import datetime

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Collect all response times for percentile calculation (currently unused)
            # all_response_times: List[float] = []

            for name, endpoint in environment_stats.entries.items():
                # Skip the aggregated entry that Locust automatically creates to avoid duplication
                if name == ("Aggregated", None) or (
                    hasattr(name, "__iter__") and name[0] == "Aggregated"
                ):
                    continue

                raw_params = {
                    "task_id": task_id,
                    "metric_type": endpoint.name,
                    "num_requests": endpoint.num_requests,
                    "num_failures": endpoint.num_failures,
                    "avg_latency": endpoint.avg_response_time,
                    "min_latency": endpoint.min_response_time,
                    "max_latency": endpoint.max_response_time,
                    "median_latency": endpoint.median_response_time,
                    "p90_latency": endpoint.get_response_time_percentile(0.9),
                    "avg_content_length": endpoint.avg_content_length,
                    "rps": endpoint.total_rps,
                    "created_at": current_time,
                }
                all_metrics_list.append(raw_params)

            return all_metrics_list

        except Exception as e:
            self.task_logger.error(f"Failed to get Locust statistics: {e}")
            raise RuntimeError(f"Failed to get Locust statistics: {e}")
