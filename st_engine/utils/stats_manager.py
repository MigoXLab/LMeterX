"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import time
from typing import Any, Dict, List

from engine.core import GlobalStateManager


class StatsManager:
    """Statistics manager"""

    def __init__(self):
        """Prepare shared global state handles used for aggregation."""
        self.global_state = GlobalStateManager()
        self.task_logger = self.global_state.get_task_logger()

    def update_stats(
        self, reqs: int = 1, completion_tokens: int = 0, total_tokens: int = 0
    ):
        """Update statistics"""
        # Update statistics in memory in single process or Master mode
        self.global_state.token_stats.reqs_count += reqs
        self.global_state.token_stats.completion_tokens += completion_tokens
        self.global_state.token_stats.total_tokens += total_tokens

    def send_stats_to_master(
        self, runner, reqs: int = 1, completion_tokens: int = 0, total_tokens: int = 0
    ):
        """Send statistics to master"""
        try:
            if hasattr(runner, "send_message"):
                runner.send_message(
                    "token_stats",
                    {
                        "reqs": reqs,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                )
        except Exception as e:
            self.task_logger.error(f"Failed to send stats to master: {e}")

    def get_final_stats(self, environment_stats=None) -> Dict[str, Any]:
        """Get final statistics

        Args:
            environment_stats: Optional Locust environment stats to extract TTFT from
        """
        stats = self.global_state.token_stats
        start_time = self.global_state.start_time
        # test_stop captures this before token draining / worker synchronization,
        # so reporting overhead is not included in throughput denominators.
        end_time = self.global_state.end_time or time.perf_counter()

        # Calculate execution time with fallback strategy
        execution_time = 0.0
        if start_time:
            # Priority 1: Use start_time to calculate actual execution time
            execution_time = max(end_time - start_time, 0.001)
        else:
            # Priority 2: Use task.duration as fallback
            try:
                duration = self.global_state.config.duration
                if duration and duration > 0:
                    execution_time = float(duration)
                else:
                    # Both start_time and duration are invalid
                    execution_time = 0.0
                    self.task_logger.error(
                        "Failed to calculate execution_time: both start_time and task.duration are invalid"
                    )
            except Exception as e:
                # Exception occurred while getting duration
                execution_time = 0.0
                self.task_logger.error(
                    f"Failed to calculate execution_time: start_time is invalid and error getting task.duration: {e}"
                )

        return {
            "reqs_count": stats.reqs_count,
            "completion_tokens": stats.completion_tokens,
            "total_tokens": stats.total_tokens,
            "req_throughput": (
                stats.reqs_count / execution_time if execution_time > 0 else 0
            ),
            "completion_tps": (
                stats.completion_tokens / execution_time if execution_time > 0 else 0
            ),
            "total_tps": (
                stats.total_tokens / execution_time if execution_time > 0 else 0
            ),
            "avg_completion_tokens_per_req": (
                stats.completion_tokens / stats.reqs_count
                if stats.reqs_count > 0
                else 0
            ),
            "avg_total_tokens_per_req": (
                stats.total_tokens / stats.reqs_count if stats.reqs_count > 0 else 0
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
                    "p95_latency": endpoint.get_response_time_percentile(0.95),
                    "avg_content_length": endpoint.avg_content_length,
                    "rps": endpoint.total_rps,
                    "created_at": current_time,
                }
                all_metrics_list.append(raw_params)

            return all_metrics_list

        except Exception as e:
            self.task_logger.error(f"Failed to get Locust statistics: {e}")
            return []

    def get_locust_errors(self, environment_stats) -> List[Dict[str, Any]]:
        """Return bounded, JSON-safe request error summaries for reporting.

        Locust keeps these errors separately from its aggregate stat rows. If
        they are not copied into the result artifact, the UI can show only a
        failure count and loses the reason for failures such as status code 0.
        """
        summaries: List[Dict[str, Any]] = []
        try:
            for stats_error in list(environment_stats.errors.values())[:20]:
                error_text = str(getattr(stats_error, "error", "") or "")
                is_network_error = "Network error (no HTTP response)" in error_text
                summaries.append(
                    {
                        "method": str(getattr(stats_error, "method", "") or ""),
                        "name": str(getattr(stats_error, "name", "") or ""),
                        "error": error_text[:2000],
                        "occurrences": int(getattr(stats_error, "occurrences", 0) or 0),
                        "category": (
                            "network_error" if is_network_error else "request_error"
                        ),
                    }
                )
        except Exception as e:
            self.task_logger.warning(f"Failed to collect Locust errors: {e}")
        return summaries
