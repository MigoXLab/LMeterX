"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from sqlalchemy.orm import Session

from model.common_task import CommonTaskResult
from utils.logger import logger


class CommonResultService:
    """Handle insertion of common API task results."""

    def insert_locust_results(
        self, session: Session, locust_result: dict, task_id: str
    ):
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
                        "p90_latency": (
                            stat.get("p90_latency")
                            if stat.get("p90_latency") is not None
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
