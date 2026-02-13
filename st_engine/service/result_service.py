"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from sqlalchemy.orm import Session

from model.task import TaskResult
from utils.logger import logger


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
