"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
from typing import List

from sqlalchemy.orm import Session

from model.task import TaskRealtimeMetric, TaskResult
from utils.logger import logger

# Maximum number of realtime metric data points persisted per task.
# Mirrors the same cap used by CommonResultService.
_MAX_PERSIST_POINTS = 1080


class ResultService:
    """
    A service class for handling operations related to test results.
    """

    def insert_locust_results(
        self, session: Session, locust_result: dict, task_id: str
    ):
        """
        Parses the results from a Locust test run and inserts them into the database.

        This method handles both standard Locust statistics and custom metrics
        (like token-based throughput).

        Args:
            session (Session): The SQLAlchemy database session.
            locust_result (dict): A dictionary containing the test results from Locust.
            task_id (str): The ID of the task associated with these results.
        """
        task_logger = logger.bind(task_id=task_id)
        try:
            custom_metrics = locust_result.get("custom_metrics", {})
            locust_stats_list = locust_result.get("locust_stats", [])

            # Insert standard Locust statistics with proper field mapping
            for stat in locust_stats_list:
                # Ensure the stat dictionary is not empty and has a task_id
                if stat and stat.get("task_id"):
                    # Map Locust stat fields to database fields
                    mapped_stat = {
                        "task_id": stat["task_id"],
                        "metric_type": stat["metric_type"],
                        "num_requests": stat["num_requests"],
                        "num_failures": stat["num_failures"],
                        "avg_latency": stat["avg_latency"],
                        "min_latency": stat["min_latency"],
                        "max_latency": stat["max_latency"],
                        "median_latency": stat["median_latency"],
                        "p95_latency": stat["p95_latency"],
                        "rps": stat["rps"],
                        "avg_content_length": stat["avg_content_length"],
                        # Initialize token-related fields with default values for standard stats
                        "total_tps": 0.0,
                        "completion_tps": 0.0,
                        "avg_total_tokens_per_req": 0.0,
                        "avg_completion_tokens_per_req": 0.0,
                    }

                    task_result = TaskResult(**mapped_stat)
                    session.add(task_result)

                    task_logger.debug(
                        f"Inserted stat for {stat['metric_type']}: "
                        f"{stat['num_requests']} requests, {stat['num_failures']} failures"
                    )
                else:
                    task_logger.warning(f"Skipping invalid stat record: {stat}")

            # Insert custom token-based metrics if available
            if custom_metrics and task_id:
                # Create a single record for all custom token metrics
                custom_task_result = TaskResult(
                    task_id=task_id,
                    metric_type="token_metrics",
                    num_requests=custom_metrics.get(
                        "reqs_num", 0
                    ),  # Use actual request count
                    num_failures=0,
                    avg_latency=0,
                    min_latency=0,
                    max_latency=0,
                    median_latency=0,
                    p95_latency=0,
                    rps=custom_metrics.get(
                        "req_throughput", 0.0
                    ),  # Use request throughput
                    avg_content_length=0,
                    completion_tps=custom_metrics.get("completion_tps", 0.0),
                    total_tps=custom_metrics.get("total_tps", 0.0),
                    avg_total_tokens_per_req=custom_metrics.get(
                        "avg_total_tokens_per_req", 0.0
                    ),
                    avg_completion_tokens_per_req=custom_metrics.get(
                        "avg_completion_tokens_per_req", 0.0
                    ),
                )
                session.add(custom_task_result)

                task_logger.debug(
                    f"Inserted custom metrics: {custom_metrics.get('reqs_num', 0)} requests, "
                    f"completion_tps: {custom_metrics.get('completion_tps', 0):.2f}, "
                    f"total_tps: {custom_metrics.get('total_tps', 0):.2f}"
                )

            session.commit()
            task_logger.debug(
                f"Successfully inserted {len(locust_stats_list)} stat entries plus custom metrics."
            )
        except Exception as e:
            task_logger.exception(f"Failed to insert test results: {e}")
            session.rollback()
            raise

    @staticmethod
    def _downsample(data_points: List[dict], max_points: int) -> List[dict]:
        """Downsample data points to at most *max_points* using uniform selection.

        The first and last points are always preserved so that the time range
        of the chart remains accurate.  Intermediate points are selected at
        evenly spaced indices to give a representative picture without storing
        every single snapshot.
        """
        n = len(data_points)
        if n <= max_points:
            return data_points

        indices = set()
        indices.add(0)
        indices.add(n - 1)
        step = (n - 1) / (max_points - 1)
        for i in range(1, max_points - 1):
            indices.add(round(i * step))

        sorted_indices = sorted(indices)
        return [data_points[i] for i in sorted_indices]

    def persist_realtime_metrics(
        self, session: Session, task_id: str, data_points: List[dict]
    ) -> int:
        """
        Batch-insert real-time metric data points into MySQL.

        The data is pre-read from the JSONL file by the runner before the
        result directory is cleaned up (see LocustRunner._finalize_task).

        If the number of raw data points exceeds ``_MAX_PERSIST_POINTS``,
        the data is downsampled first to prevent the table from growing
        unboundedly during long-running stability tests.

        Returns the number of rows inserted.
        """
        task_logger = logger.bind(task_id=task_id)

        if not data_points:
            task_logger.debug("No realtime metric data points to persist.")
            return 0

        original_count = len(data_points)
        if original_count > _MAX_PERSIST_POINTS:
            data_points = self._downsample(data_points, _MAX_PERSIST_POINTS)
            task_logger.info(
                f"Downsampled realtime metrics from {original_count} to "
                f"{len(data_points)} points (max={_MAX_PERSIST_POINTS})."
            )

        inserted = 0
        try:
            for point in data_points:
                # Serialize per-metric detail dict to JSON string if present
                metrics_raw = point.get("metrics")
                metrics_detail = (
                    json.dumps(metrics_raw, ensure_ascii=False) if metrics_raw else None
                )
                metric = TaskRealtimeMetric(
                    task_id=task_id,
                    timestamp=point.get("timestamp", 0),
                    current_users=int(point.get("current_users", 0)),
                    current_rps=float(point.get("current_rps", 0)),
                    current_fail_per_sec=float(point.get("current_fail_per_sec", 0)),
                    avg_response_time=float(point.get("avg_response_time", 0)),
                    min_response_time=float(point.get("min_response_time", 0)),
                    max_response_time=float(point.get("max_response_time", 0)),
                    median_response_time=float(point.get("median_response_time", 0)),
                    p95_response_time=float(point.get("p95_response_time", 0)),
                    total_requests=int(point.get("total_requests", 0)),
                    total_failures=int(point.get("total_failures", 0)),
                    metrics_detail=metrics_detail,
                )
                session.add(metric)
                inserted += 1

            session.commit()
            task_logger.info(
                f"Persisted {inserted} realtime metric data points to database."
            )
        except Exception as e:
            task_logger.exception(f"Failed to persist realtime metrics: {e}")
            session.rollback()

        return inserted
