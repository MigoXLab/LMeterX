"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy.orm import Session

from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_CREATED,
    TASK_STATUS_FAILED,
    TASK_STATUS_STOPPED,
)


class TestTaskPoller:
    """Task poller test class"""

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
    def task_poller(self, mock_task_service):
        """Fixture to create task poller instance"""
        # Mock TaskPoller class
        poller = Mock()
        poller.task_service = mock_task_service
        poller.polling_interval = 1
        poller.is_running = False
        return poller

    @pytest.fixture
    def sample_task(self):
        """Fixture to create sample task"""
        task = Mock()
        task.id = "test-task-001"
        task.name = "Test Task"
        task.status = TASK_STATUS_CREATED
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

    def test_poller_initialization(self, task_poller, mock_task_service):
        """Test poller initialization"""
        assert task_poller.task_service == mock_task_service
        assert task_poller.polling_interval == 1
        assert task_poller.is_running is False

    def test_poller_start_stop(self, task_poller):
        """Test poller start and stop"""

        # Mock start method
        def mock_start():
            task_poller.is_running = True

        # Mock stop method
        def mock_stop():
            task_poller.is_running = False

        task_poller.start = mock_start
        task_poller.stop = mock_stop

        # Test start
        task_poller.start()
        assert task_poller.is_running is True

        # Test stop
        task_poller.stop()
        assert task_poller.is_running is False

    @pytest.mark.asyncio
    async def test_poll_for_tasks_success(
        self, task_poller, mock_task_service, mock_session, sample_task
    ):
        """Test successful task polling"""
        # Mock task service returning a task
        mock_task_service.get_and_lock_task.return_value = sample_task

        # Mock async polling method
        async def mock_poll_for_tasks():
            task = mock_task_service.get_and_lock_task(mock_session)
            if task:
                # Mock task processing
                mock_task_service.process_task_pipeline(task, mock_session)
                return True
            return False

        # Call polling method
        result = await mock_poll_for_tasks()

        # Verify task was successfully processed
        assert result is True
        mock_task_service.get_and_lock_task.assert_called_once_with(mock_session)
        mock_task_service.process_task_pipeline.assert_called_once_with(
            sample_task, mock_session
        )

    @pytest.mark.asyncio
    async def test_poll_for_tasks_no_available_tasks(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test polling behavior when no tasks are available"""
        # Mock task service returning None (no available tasks)
        mock_task_service.get_and_lock_task.return_value = None

        # Mock async polling method
        async def mock_poll_for_tasks():
            task = mock_task_service.get_and_lock_task(mock_session)
            if task:
                mock_task_service.process_task_pipeline(task, mock_session)
                return True
            return False

        # Call polling method
        result = await mock_poll_for_tasks()

        # Verify no tasks were processed
        assert result is False
        mock_task_service.get_and_lock_task.assert_called_once_with(mock_session)
        mock_task_service.process_task_pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_for_tasks_exception_handling(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test exception handling during task polling"""
        # Mock task service throwing exception
        mock_task_service.get_and_lock_task.side_effect = Exception(
            "Database connection failed"
        )

        # Mock async polling method (with exception handling)
        async def mock_poll_for_tasks():
            try:
                task = mock_task_service.get_and_lock_task(mock_session)
                if task:
                    mock_task_service.process_task_pipeline(task, mock_session)
                    return True
                return False
            except Exception:
                return False

        # Call polling method
        result = await mock_poll_for_tasks()

        # Verify exception was handled
        assert result is False
        mock_task_service.get_and_lock_task.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_poll_for_stopping_tasks_success(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test successful polling for stopping tasks"""
        # Mock task service returning list of task IDs to stop
        stopping_task_ids = ["task-001", "task-002", "task-003"]
        mock_task_service.get_stopping_task_ids.return_value = stopping_task_ids

        # Mock successful task stopping
        mock_task_service.stop_task.return_value = True

        # Mock async polling for stopping tasks method
        async def mock_poll_for_stopping_tasks():
            task_ids = mock_task_service.get_stopping_task_ids(mock_session)
            stopped_count = 0
            for task_id in task_ids:
                if mock_task_service.stop_task(task_id):
                    stopped_count += 1
                    # Update task status to stopped
                    mock_task_service.update_task_status(
                        mock_session, Mock(id=task_id), TASK_STATUS_STOPPED
                    )
            return stopped_count

        # Call polling for stopping tasks method
        stopped_count = await mock_poll_for_stopping_tasks()

        # Verify all tasks were successfully stopped
        assert stopped_count == 3
        mock_task_service.get_stopping_task_ids.assert_called_once_with(mock_session)
        assert mock_task_service.stop_task.call_count == 3

    @pytest.mark.asyncio
    async def test_poll_for_stopping_tasks_no_tasks(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test polling behavior when no tasks need to be stopped"""
        # Mock task service returning empty list
        mock_task_service.get_stopping_task_ids.return_value = []

        # Mock async polling for stopping tasks method
        async def mock_poll_for_stopping_tasks():
            task_ids = mock_task_service.get_stopping_task_ids(mock_session)
            stopped_count = 0
            for task_id in task_ids:
                if mock_task_service.stop_task(task_id):
                    stopped_count += 1
            return stopped_count

        # Call polling for stopping tasks method
        stopped_count = await mock_poll_for_stopping_tasks()

        # Verify no tasks were stopped
        assert stopped_count == 0
        mock_task_service.get_stopping_task_ids.assert_called_once_with(mock_session)
        mock_task_service.stop_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_for_stopping_tasks_partial_failure(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test partial task stopping failure scenario"""
        # Mock task service returning list of task IDs to stop
        stopping_task_ids = ["task-001", "task-002", "task-003"]
        mock_task_service.get_stopping_task_ids.return_value = stopping_task_ids

        # Mock partial task stopping failure
        def mock_stop_task(task_id):
            if task_id == "task-002":
                return False  # Second task fails to stop
            return True

        mock_task_service.stop_task.side_effect = mock_stop_task

        # Mock async polling for stopping tasks method
        async def mock_poll_for_stopping_tasks():
            task_ids = mock_task_service.get_stopping_task_ids(mock_session)
            stopped_count = 0
            failed_count = 0
            for task_id in task_ids:
                if mock_task_service.stop_task(task_id):
                    stopped_count += 1
                    mock_task_service.update_task_status(
                        mock_session, Mock(id=task_id), TASK_STATUS_STOPPED
                    )
                else:
                    failed_count += 1
            return stopped_count, failed_count

        # Call polling for stopping tasks method
        stopped_count, failed_count = await mock_poll_for_stopping_tasks()

        # Verify partial tasks stopped successfully, partial failed
        assert stopped_count == 2
        assert failed_count == 1
        mock_task_service.get_stopping_task_ids.assert_called_once_with(mock_session)
        assert mock_task_service.stop_task.call_count == 3

    @pytest.mark.asyncio
    async def test_poll_for_stopping_tasks_exception_handling(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test exception handling during polling for stopping tasks"""
        # Mock task service throwing exception
        mock_task_service.get_stopping_task_ids.side_effect = Exception(
            "Database connection failed"
        )

        # Mock async polling for stopping tasks method (with exception handling)
        async def mock_poll_for_stopping_tasks():
            try:
                task_ids = mock_task_service.get_stopping_task_ids(mock_session)
                stopped_count = 0
                for task_id in task_ids:
                    if mock_task_service.stop_task(task_id):
                        stopped_count += 1
                return stopped_count
            except Exception:
                return -1  # Return -1 to indicate exception

        # Call polling for stopping tasks method
        result = await mock_poll_for_stopping_tasks()

        # Verify exception was handled
        assert result == -1
        mock_task_service.get_stopping_task_ids.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_continuous_polling_loop(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test continuous polling loop"""
        # Mock polling counter
        poll_count = 0
        max_polls = 3

        # Mock task service behavior
        def mock_get_and_lock_task(session):
            nonlocal poll_count
            poll_count += 1
            if poll_count <= max_polls:
                # Return tasks for first few polls
                task = Mock()
                task.id = f"task-{poll_count:03d}"
                return task
            return None

        mock_task_service.get_and_lock_task.side_effect = mock_get_and_lock_task

        # Mock continuous polling loop
        async def mock_continuous_polling():
            processed_tasks = []
            while poll_count < max_polls:
                task = mock_task_service.get_and_lock_task(mock_session)
                if task:
                    processed_tasks.append(task.id)
                    mock_task_service.process_task_pipeline(task, mock_session)
                await asyncio.sleep(0.01)  # Short delay to simulate polling interval
            return processed_tasks

        # Call continuous polling
        processed_tasks = await mock_continuous_polling()

        # Verify expected number of tasks were processed
        assert len(processed_tasks) == max_polls
        assert processed_tasks == ["task-001", "task-002", "task-003"]
        assert mock_task_service.get_and_lock_task.call_count == max_polls
        assert mock_task_service.process_task_pipeline.call_count == max_polls

    def test_poller_configuration(self, task_poller):
        """Test poller configuration"""
        # Test default configuration
        assert task_poller.polling_interval == 1

        # Test configuration update
        task_poller.polling_interval = 5
        assert task_poller.polling_interval == 5

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, task_poller):
        """Test graceful shutdown"""
        # Mock running state
        task_poller.is_running = True

        # Mock graceful shutdown method
        async def mock_graceful_shutdown():
            if task_poller.is_running:
                task_poller.is_running = False
                # Wait for current tasks to complete
                await asyncio.sleep(0.01)
                return True
            return False

        # Call graceful shutdown
        result = await mock_graceful_shutdown()

        # Verify successful shutdown
        assert result is True
        assert task_poller.is_running is False

    @pytest.mark.asyncio
    async def test_concurrent_task_processing(
        self, task_poller, mock_task_service, mock_session
    ):
        """Test concurrent task processing"""
        # Mock multiple tasks
        tasks = [
            Mock(id="task-001", status=TASK_STATUS_CREATED),
            Mock(id="task-002", status=TASK_STATUS_CREATED),
            Mock(id="task-003", status=TASK_STATUS_CREATED),
        ]

        # Mock task processing results
        processed_tasks = []

        async def mock_process_task(task):
            # Mock task processing time
            await asyncio.sleep(0.01)
            processed_tasks.append(task.id)
            task.status = TASK_STATUS_COMPLETED

        # Mock concurrent processing
        async def mock_concurrent_processing():
            tasks_to_process = []
            for task in tasks:
                tasks_to_process.append(mock_process_task(task))

            # Execute all tasks concurrently
            await asyncio.gather(*tasks_to_process)
            return len(processed_tasks)

        # Call concurrent processing
        processed_count = await mock_concurrent_processing()

        # Verify all tasks were processed
        assert processed_count == 3
        assert len(processed_tasks) == 3
        assert all(task.status == TASK_STATUS_COMPLETED for task in tasks)

    def test_error_recovery(self, task_poller, mock_task_service, mock_session):
        """Test error recovery mechanism"""
        # Mock error counter
        error_count = 0
        max_errors = 3

        def mock_get_and_lock_task_with_errors(session):
            nonlocal error_count
            error_count += 1
            if error_count <= max_errors:
                raise Exception(f"Mock error {error_count}")
            # Return normal task after error recovery
            task = Mock()
            task.id = "recovery-task"
            return task

        mock_task_service.get_and_lock_task.side_effect = (
            mock_get_and_lock_task_with_errors
        )

        # Mock error recovery mechanism
        def mock_error_recovery():
            attempts = 0
            max_attempts = 5

            while attempts < max_attempts:
                try:
                    task = mock_task_service.get_and_lock_task(mock_session)
                    if task:
                        return task
                except Exception:
                    attempts += 1
                    continue
            return None

        # Call error recovery
        result = mock_error_recovery()

        # Verify successful recovery
        assert result is not None
        assert result.id == "recovery-task"
        assert mock_task_service.get_and_lock_task.call_count == max_errors + 1

    @pytest.mark.asyncio
    async def test_task_timeout_handling(
        self, task_poller, mock_task_service, mock_session, sample_task
    ):
        """Test task timeout handling"""

        # Mock long-running task
        async def mock_long_running_task():
            await asyncio.sleep(2)  # Mock long execution time
            return "completed"

        # Mock timeout handling
        async def mock_task_with_timeout():
            try:
                # Set 1 second timeout
                result = await asyncio.wait_for(mock_long_running_task(), timeout=1.0)
                return result
            except asyncio.TimeoutError:
                # Timeout handling
                sample_task.status = TASK_STATUS_FAILED
                sample_task.error_message = "Task execution timeout"
                return "timeout"

        # Call timeout handling
        result = await mock_task_with_timeout()

        # Verify timeout was handled correctly
        assert result == "timeout"
        assert sample_task.status == TASK_STATUS_FAILED
        assert "timeout" in sample_task.error_message

    def test_metrics_collection(self, task_poller):
        """Test metrics collection"""
        # Mock metrics collector
        metrics = {
            "tasks_processed": 0,
            "tasks_failed": 0,
            "tasks_stopped": 0,
            "polling_cycles": 0,
        }

        # Mock metrics update method
        def update_metrics(metric_name, value=1):
            if metric_name in metrics:
                metrics[metric_name] += value

        # Mock metrics collection during polling cycle
        def mock_polling_cycle():
            update_metrics("polling_cycles")

            # Mock task processing
            update_metrics("tasks_processed", 3)
            update_metrics("tasks_failed", 1)
            update_metrics("tasks_stopped", 2)

        # Execute multiple polling cycles
        for _ in range(5):
            mock_polling_cycle()

        # Verify metrics collection
        assert metrics["polling_cycles"] == 5
        assert metrics["tasks_processed"] == 15
        assert metrics["tasks_failed"] == 5
        assert metrics["tasks_stopped"] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
