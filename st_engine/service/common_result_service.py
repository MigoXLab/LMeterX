"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import List

from sqlalchemy.orm import Session

from model.common_task import CommonTaskRealtimeMetric, CommonTaskResult
from utils.logger import logger


class CommonResultService:
    """Handle insertion of common API task results."""

    def insert_locust_results(
        self, session: Session, locust_result: dict, task_id: str
    ):
        """Insert locust statistics for the given task into the database."""
        task_logger = logger.bind(task_id=task_id)
        try:
            locust_stats_list = locust_result.get("locust_stats", [])

            for stat in locust_stats_list:
                if stat and stat.get("task_id"):
                    metric_type = stat.get("metric_type")
                    # Normalize metric_type to string (locust may output list/tuple)
                    if isinstance(metric_type, (list, tuple)):
                        metric_type = str(metric_type[0]) if metric_type else ""
                    else:
                        metric_type = str(metric_type)

                    # Handle None values for fields that cannot be null in the database
                    # When num_requests is 0, some latency fields may be None
                    mapped_stat = {
                        "task_id": stat["task_id"],
                        "metric_type": metric_type,
                        "num_requests": stat.get("num_requests", 0) or 0,
                        "num_failures": stat.get("num_failures", 0) or 0,
                        "avg_latency": (
                            stat.get("avg_latency")
                            if stat.get("avg_latency") is not None
                            else 0.0
                        ),
                        "min_latency": (
                            stat.get("min_latency")
                            if stat.get("min_latency") is not None
                            else 0.0
                        ),
                        "max_latency": (
                            stat.get("max_latency")
                            if stat.get("max_latency") is not None
                            else 0.0
                        ),
                        "median_latency": (
                            stat.get("median_latency")
                            if stat.get("median_latency") is not None
                            else 0.0
                        ),
                        "p95_latency": (
                            stat.get("p95_latency")
                            if stat.get("p95_latency") is not None
                            else 0.0
                        ),
                        "rps": (
                            float(stat.get("rps"))
                            if stat.get("rps") is not None
                            else 0.0
                        ),
                        "avg_content_length": (
                            stat.get("avg_content_length")
                            if stat.get("avg_content_length") is not None
                            else 0.0
                        ),
                    }
                    task_result = CommonTaskResult(**mapped_stat)
                    session.add(task_result)
                    task_logger.debug(
                        f" Inserted stat for {metric_type}: "
                        f"{mapped_stat['num_requests']} requests, {mapped_stat['num_failures']} failures"
                    )
                else:
                    task_logger.warning(f" Skipping invalid stat record: {stat}")

            session.commit()
            task_logger.debug(
                f" Successfully inserted {len(locust_stats_list)} stat entries."
            )
        except Exception as e:
            task_logger.exception(f" Failed to insert test results: {e}")
            session.rollback()
            raise

    def persist_realtime_metrics(
        self, session: Session, task_id: str, data_points: List[dict]
    ) -> int:
        """
        Batch-insert real-time metric data points into MySQL.
        The data is pre-read from the JSONL file by the runner before the
        result directory is cleaned up (see CommonLocustRunner._finalize_task).
        Returns the number of rows inserted.
        """
        task_logger = logger.bind(task_id=task_id)

        if not data_points:
            task_logger.debug("No realtime metric data points to persist.")
            return 0

        inserted = 0
        try:
            for point in data_points:
                metric = CommonTaskRealtimeMetric(
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
