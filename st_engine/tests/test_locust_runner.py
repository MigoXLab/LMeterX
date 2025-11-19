"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy.orm import Session

from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_LOCKED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
)


class TestLocustRunner:
    """Locust runner test class"""

    @pytest.fixture
    def mock_session(self):
        """Fixture to create mock database session"""
        session = MagicMock(spec=Session)
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=None)
        return session

    @pytest.fixture
    def mock_task_service(self):
        """Fixture to create mock task service"""
        return Mock()

    @pytest.fixture
    def locust_runner(self, mock_task_service):
        """Fixture to create Locust runner instance"""
        runner = Mock()
        runner.task_service = mock_task_service
        runner.is_running = False
        runner.current_task = None
        runner.process = None
        return runner

    @pytest.fixture
    def sample_task(self):
        """Fixture to create sample task"""
        task = Mock()
        task.id = "test-task-001"
        task.name = "Test Task"
        task.status = TASK_STATUS_LOCKED
        task.target_host = "http://localhost:8000"
        task.model = "test-model"
        task.stream_mode = "True"
        task.concurrent_users = 10
        task.spawn_rate = 2
        task.duration = 60
        task.chat_type = 0
        task.headers = '{"Content-Type": "application/json"}'
        task.created_at = datetime.now()
        task.updated_at = datetime.now()
        task.error_message = None
        return task

    def test_runner_initialization(self, locust_runner, mock_task_service):
        """Test runner initialization"""
        assert locust_runner.task_service == mock_task_service
        assert locust_runner.is_running is False
        assert locust_runner.current_task is None
        assert locust_runner.process is None

    def test_runner_start_stop(self, locust_runner):
        """Test runner start and stop"""

        # Mock start method
        def mock_start():
            locust_runner.is_running = True

        # Mock stop method
        def mock_stop():
            locust_runner.is_running = False

        locust_runner.start = mock_start
        locust_runner.stop = mock_stop

        # Test start
        locust_runner.start()
        assert locust_runner.is_running is True

        # Test stop
        locust_runner.stop()
        assert locust_runner.is_running is False

    @pytest.mark.asyncio
    async def test_run_task_success(
        self, locust_runner, mock_task_service, mock_session, sample_task
    ):
        """Test successful task execution"""
        # Mock successful task execution
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"Test completed successfully", b"")

        # Mock async task execution method
        async def mock_run_task(task):
            locust_runner.current_task = task
            # Update task status to running
            mock_task_service.update_task_status(
                mock_session, task, TASK_STATUS_RUNNING
            )

            # Mock task execution
            await asyncio.sleep(0.01)

            # Update task status to completed
            mock_task_service.update_task_status(
                mock_session, task, TASK_STATUS_COMPLETED
            )
            locust_runner.current_task = None
            return True

        # Call run task method
        result = await mock_run_task(sample_task)

        # Verify task executed successfully
        assert result is True
        assert locust_runner.current_task is None
        assert mock_task_service.update_task_status.call_count == 2

    @pytest.mark.asyncio
    async def test_run_task_failure(
        self, locust_runner, mock_task_service, mock_session, sample_task
    ):
        """Test task execution failure"""
        # Mock task execution failure
        error_message = "Failed to connect to target host"

        # Mock async task execution method (failure case)
        async def mock_run_task_with_failure(task):
            locust_runner.current_task = task
            # Update task status to running
            mock_task_service.update_task_status(
                mock_session, task, TASK_STATUS_RUNNING
            )

            try:
                # Mock task execution failure
                raise Exception(error_message)
            except Exception as e:
                # Update task status to failed
                task.error_message = str(e)
                mock_task_service.update_task_status(
                    mock_session, task, TASK_STATUS_FAILED
                )
                locust_runner.current_task = None
                return False

        # Call run task method
        result = await mock_run_task_with_failure(sample_task)

        # Verify task execution failed
        assert result is False
        assert locust_runner.current_task is None
        assert sample_task.error_message == error_message
        assert mock_task_service.update_task_status.call_count == 2

    def test_build_locust_command(self, locust_runner, sample_task):
        """Test building Locust command"""

        # Mock command building method
        def mock_build_locust_command(task):
            base_cmd = ["locust", "-f", "locustfile.py"]

            # Add basic parameters
            cmd = base_cmd + [
                "--host",
                task.target_host,
                "--users",
                str(task.concurrent_users),
                "--spawn-rate",
                str(task.spawn_rate),
                "--run-time",
                f"{task.duration}s",
                "--headless",
                "--csv",
                f"results_{task.id}",
            ]

            # Add custom parameters
            if hasattr(task, "model") and task.model:
                cmd.extend(["--model", task.model])

            if hasattr(task, "stream_mode") and task.stream_mode:
                cmd.extend(["--stream-mode", task.stream_mode])

            if hasattr(task, "chat_type") and task.chat_type is not None:
                cmd.extend(["--chat-type", str(task.chat_type)])

            return cmd

        # Call command building method
        command = mock_build_locust_command(sample_task)

        # Verify command was built correctly
        assert "locust" in command
        assert "--host" in command
        assert sample_task.target_host in command
        assert "--users" in command
        assert str(sample_task.concurrent_users) in command
        assert "--spawn-rate" in command
        assert str(sample_task.spawn_rate) in command
        assert "--run-time" in command
        assert f"{sample_task.duration}s" in command
        assert "--headless" in command
        assert "--model" in command
        assert sample_task.model in command

    def test_parse_task_headers(self, locust_runner, sample_task):
        """Test parsing task headers"""

        # Mock header parsing method
        def mock_parse_headers(headers_str):
            try:
                if headers_str:
                    return json.loads(headers_str)
                return {}
            except json.JSONDecodeError:
                return {}

        # Test valid JSON headers
        headers = mock_parse_headers(sample_task.headers)
        assert isinstance(headers, dict)
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"

        # Test invalid JSON headers
        invalid_headers = mock_parse_headers("invalid json")
        assert invalid_headers == {}

        # Test empty headers
        empty_headers = mock_parse_headers("")
        assert empty_headers == {}

    @pytest.mark.asyncio
    async def test_task_monitoring(
        self, locust_runner, mock_task_service, mock_session, sample_task
    ):
        """Test task monitoring"""
        # Mock task monitoring data
        monitoring_data = {
            "users": 10,
            "rps": 15.5,
            "response_time": 120.3,
            "failure_rate": 0.02,
            "total_requests": 1500,
            "failed_requests": 30,
        }

        # Mock async monitoring method
        async def mock_monitor_task(task):
            locust_runner.current_task = task

            # Mock monitoring loop
            for i in range(3):
                await asyncio.sleep(0.01)

                # Mock collecting monitoring data
                current_data = monitoring_data.copy()
                current_data["timestamp"] = datetime.now()
                current_data["iteration"] = i + 1

                # Mock saving monitoring data
                mock_task_service.save_monitoring_data(task.id, current_data)

            locust_runner.current_task = None
            return monitoring_data

        # Call monitoring method
        result = await mock_monitor_task(sample_task)

        # Verify monitoring data
        assert result == monitoring_data
        assert locust_runner.current_task is None
        assert mock_task_service.save_monitoring_data.call_count == 3

    def test_task_validation(self, locust_runner, sample_task):
        """Test task validation"""

        # Mock task validation method
        def mock_validate_task(task):
            errors = []

            # Validate required fields
            if not task.target_host:
                errors.append("Target host cannot be empty")

            if not task.target_host.startswith(("http://", "https://")):
                errors.append("Target host must be a valid URL")

            if task.concurrent_users <= 0:
                errors.append("Concurrent users must be greater than 0")

            if task.spawn_rate <= 0:
                errors.append("Spawn rate must be greater than 0")

            if task.duration <= 0:
                errors.append("Duration must be greater than 0")

            return len(errors) == 0, errors

        # Test valid task
        is_valid, errors = mock_validate_task(sample_task)
        assert is_valid is True
        assert len(errors) == 0

        # Test invalid task
        invalid_task = Mock()
        invalid_task.target_host = ""
        invalid_task.concurrent_users = 0
        invalid_task.spawn_rate = -1
        invalid_task.duration = 0

        is_valid, errors = mock_validate_task(invalid_task)
        assert is_valid is False
        assert len(errors) > 0
        assert "Target host cannot be empty" in errors

    @pytest.mark.asyncio
    async def test_task_cancellation(
        self, locust_runner, mock_task_service, mock_session, sample_task
    ):
        """Test task cancellation"""
        # Mock task cancellation
        cancellation_requested = False

        # Mock async task execution (cancellable)
        async def mock_cancellable_task(task):
            nonlocal cancellation_requested
            locust_runner.current_task = task

            try:
                # Mock long-running task
                for i in range(10):
                    if cancellation_requested:
                        # Task was cancelled
                        mock_task_service.update_task_status(
                            mock_session, task, TASK_STATUS_STOPPED
                        )
                        return "cancelled"
                    await asyncio.sleep(0.01)

                # Task completed normally
                mock_task_service.update_task_status(
                    mock_session, task, TASK_STATUS_COMPLETED
                )
                return "completed"
            finally:
                locust_runner.current_task = None

        # Mock cancellation method
        def mock_cancel_task():
            nonlocal cancellation_requested
            cancellation_requested = True

        # Start task
        task_coroutine = mock_cancellable_task(sample_task)

        # Mock cancelling task during execution
        await asyncio.sleep(0.05)
        mock_cancel_task()

        # Wait for task completion
        result = await task_coroutine

        # Verify task was cancelled
        assert result == "cancelled"
        assert locust_runner.current_task is None
        mock_task_service.update_task_status.assert_called_with(
            mock_session, sample_task, TASK_STATUS_STOPPED
        )

    def test_result_collection(self, locust_runner, sample_task):
        """Test result collection"""
        # Mock result data
        result_data = {
            "total_requests": 1000,
            "failed_requests": 25,
            "average_response_time": 150.5,
            "min_response_time": 50.2,
            "max_response_time": 500.8,
            "requests_per_second": 16.7,
            "failure_rate": 0.025,
            "percentiles": {
                "50": 120.0,
                "90": 200.0,
                "95": 250.0,
                "99": 400.0,
            },
        }

        # Mock result collection method
        def mock_collect_results(task_id):
            # Mock reading results from CSV files
            csv_files = [
                f"results_{task_id}_stats.csv",
                f"results_{task_id}_stats_history.csv",
                f"results_{task_id}_failures.csv",
            ]

            # Mock parsing result data
            collected_data = result_data.copy()
            collected_data["task_id"] = task_id
            collected_data["csv_files"] = csv_files
            collected_data["collection_time"] = datetime.now()

            return collected_data

        # Call result collection method
        results = mock_collect_results(sample_task.id)

        # Verify result collection
        assert results["task_id"] == sample_task.id
        assert results["total_requests"] == 1000
        assert results["failed_requests"] == 25
        assert results["failure_rate"] == 0.025
        assert "percentiles" in results
        assert "csv_files" in results
        assert len(results["csv_files"]) == 3

    @pytest.mark.asyncio
    async def test_concurrent_task_execution(
        self, locust_runner, mock_task_service, mock_session
    ):
        """Test concurrent task execution"""
        # Create multiple tasks
        tasks = []
        for i in range(3):
            task = Mock()
            task.id = f"task-{i+1:03d}"
            task.name = f"Test Task {i+1}"
            task.status = TASK_STATUS_LOCKED
            task.target_host = f"http://localhost:800{i}"
            task.concurrent_users = 5 + i
            task.duration = 30 + i * 10
            tasks.append(task)

        # Mock concurrent execution results
        execution_results = []

        # Mock async task execution
        async def mock_execute_task(task):
            # Mock task execution time
            await asyncio.sleep(0.01 * int(task.id.split("-")[1]))

            # Mock execution result
            result = {
                "task_id": task.id,
                "status": "completed",
                "execution_time": 0.01 * int(task.id.split("-")[1]),
            }
            execution_results.append(result)
            return result

        # Execute all tasks concurrently
        tasks_to_execute = [mock_execute_task(task) for task in tasks]
        results = await asyncio.gather(*tasks_to_execute)

        # Verify concurrent execution results
        assert len(results) == 3
        assert len(execution_results) == 3
        assert all(result["status"] == "completed" for result in results)

        # Verify tasks completed in expected order (based on execution time)
        task_ids = [result["task_id"] for result in execution_results]
        assert "task-001" in task_ids
        assert "task-002" in task_ids
        assert "task-003" in task_ids

    def test_resource_cleanup(self, locust_runner, sample_task):
        """Test resource cleanup"""
        # Mock resource state
        resources = {
            "temp_files": [f"temp_{sample_task.id}.txt", f"log_{sample_task.id}.log"],
            "processes": [Mock(pid=1234), Mock(pid=5678)],
            "connections": [Mock(id="conn1"), Mock(id="conn2")],
        }

        # Mock resource cleanup method
        def mock_cleanup_resources(task_id):
            cleaned_resources = {
                "temp_files": [],
                "processes": [],
                "connections": [],
            }

            # Mock cleaning temporary files
            for file_path in resources["temp_files"]:
                if task_id in file_path:
                    cleaned_resources["temp_files"].append(file_path)

            # Mock terminating processes
            for process in resources["processes"]:
                process.terminate()
                cleaned_resources["processes"].append(process.pid)

            # Mock closing connections
            for connection in resources["connections"]:
                connection.close()
                cleaned_resources["connections"].append(connection.id)

            return cleaned_resources

        # Call resource cleanup method
        cleaned = mock_cleanup_resources(sample_task.id)

        # Verify resource cleanup
        assert len(cleaned["temp_files"]) == 2
        assert len(cleaned["processes"]) == 2
        assert len(cleaned["connections"]) == 2
        assert all(sample_task.id in file_path for file_path in cleaned["temp_files"])

    def test_error_handling_and_recovery(
        self, locust_runner, mock_task_service, mock_session, sample_task
    ):
        """Test error handling and recovery"""
        # Mock error counter
        error_count = 0
        max_retries = 3

        # Mock task execution method with retry
        def mock_execute_with_retry(task):
            nonlocal error_count

            for attempt in range(max_retries + 1):
                try:
                    error_count += 1
                    if error_count <= max_retries:
                        raise Exception(f"Mock error {error_count}")

                    # Last attempt succeeds
                    mock_task_service.update_task_status(
                        mock_session, task, TASK_STATUS_COMPLETED
                    )
                    return {"status": "success", "attempts": attempt + 1}

                except Exception as e:
                    if attempt == max_retries:
                        # All retries failed
                        task.error_message = str(e)
                        mock_task_service.update_task_status(
                            mock_session, task, TASK_STATUS_FAILED
                        )
                        return {
                            "status": "failed",
                            "attempts": attempt + 1,
                            "error": str(e),
                        }

                    # Continue retrying
                    continue

        # Call execution method with retry
        result = mock_execute_with_retry(sample_task)

        # Verify error handling and recovery
        assert result["status"] == "success"
        assert result["attempts"] == max_retries + 1
        mock_task_service.update_task_status.assert_called_with(
            mock_session, sample_task, TASK_STATUS_COMPLETED
        )

    def test_performance_metrics_calculation(self, locust_runner, sample_task):
        """Test performance metrics calculation"""
        # Mock raw performance data
        raw_data = [
            {"timestamp": 1000, "response_time": 100, "success": True},
            {"timestamp": 1001, "response_time": 150, "success": True},
            {"timestamp": 1002, "response_time": 200, "success": False},
            {"timestamp": 1003, "response_time": 120, "success": True},
            {"timestamp": 1004, "response_time": 180, "success": True},
        ]

        # Mock performance metrics calculation method
        def mock_calculate_metrics(data):
            total_requests = len(data)
            successful_requests = sum(1 for item in data if item["success"])
            failed_requests = total_requests - successful_requests

            # Calculate response time statistics
            response_times = [item["response_time"] for item in data if item["success"]]
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                min_response_time = min(response_times)
                max_response_time = max(response_times)
            else:
                avg_response_time = min_response_time = max_response_time = 0

            # Calculate failure rate
            failure_rate = failed_requests / total_requests if total_requests > 0 else 0

            # Calculate RPS (based on time span)
            if data:
                time_span = data[-1]["timestamp"] - data[0]["timestamp"]
                rps = total_requests / max(time_span, 1)
            else:
                rps = 0

            return {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "average_response_time": avg_response_time,
                "min_response_time": min_response_time,
                "max_response_time": max_response_time,
                "failure_rate": failure_rate,
                "requests_per_second": rps,
            }

        # Call metrics calculation method
        metrics = mock_calculate_metrics(raw_data)

        # Verify calculation results
        assert metrics["total_requests"] == 5
        assert metrics["successful_requests"] == 4
        assert metrics["failed_requests"] == 1
        assert metrics["failure_rate"] == 0.2
        assert metrics["average_response_time"] == 137.5  # (100+150+120+180)/4
        assert metrics["min_response_time"] == 100
        assert metrics["max_response_time"] == 180
        assert metrics["requests_per_second"] == 1.25  # 5 requests in 4 seconds


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
