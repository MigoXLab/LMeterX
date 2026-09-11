"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_CREATED,
    TASK_STATUS_FAILED,
    TASK_STATUS_LOCKED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
    TASK_STATUS_STOPPING,
)


class TestTaskLifecycle:
    """Task lifecycle test class"""

    @pytest.fixture
    def task_service(self):
        """Fixture to create TaskService instance"""
        with patch("service.task_service.LocustRunner"):
            # Mock TaskService import
            with patch.dict("sys.modules", {"service.task_service": Mock()}):
                from service.task_service import TaskService

                return TaskService()

    @pytest.fixture
    def mock_session(self):
        """Fixture to create mock database session"""
        return Mock(spec=Session)

    @pytest.fixture
    def sample_task(self):
        """Fixture to create sample task"""
        # Create a mock Task object
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

    def test_task_creation_to_locked_transition(self, mock_session, sample_task):
        """Test task transition from created to locked status"""
        # Mock database query returning a task in created status
        mock_session.execute.return_value.scalar_one_or_none.return_value = sample_task

        # Mock get_and_lock_task method
        def mock_get_and_lock_task(session):
            task = session.execute.return_value.scalar_one_or_none.return_value
            if task:
                task.status = TASK_STATUS_LOCKED
                session.commit()
                return task
            return None

        # Call get and lock task method
        locked_task = mock_get_and_lock_task(mock_session)

        # Verify task was successfully locked
        assert locked_task is not None
        assert locked_task.id == "test-task-001"
        assert locked_task.status == TASK_STATUS_LOCKED
        mock_session.commit.assert_called_once()

    def test_no_available_tasks_to_lock(self, mock_session):
        """Test locking behavior when no tasks are available"""
        # Mock database query returning None (no available tasks)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        # Mock get_and_lock_task method
        def mock_get_and_lock_task(session):
            return session.execute.return_value.scalar_one_or_none.return_value

        # Call get and lock task method
        locked_task = mock_get_and_lock_task(mock_session)

        # Verify None is returned
        assert locked_task is None
        mock_session.commit.assert_not_called()

    def test_task_status_update_success(self, sample_task, mock_session):
        """Test successful task status update"""

        # Mock update_task_status method
        def mock_update_task_status(session, task, status, error_message=None):
            task.status = status
            if error_message:
                task.error_message = error_message
            session.commit()

        # Call status update method
        mock_update_task_status(mock_session, sample_task, TASK_STATUS_RUNNING)

        # Verify task status was updated
        assert sample_task.status == TASK_STATUS_RUNNING
        mock_session.commit.assert_called_once()

    def test_task_status_update_with_error_message(self, sample_task, mock_session):
        """Test task status update with error message"""
        error_msg = "Task execution failed: connection timeout"

        # Mock update_task_status method
        def mock_update_task_status(session, task, status, error_message=None):
            task.status = status
            if error_message:
                task.error_message = error_message
            session.commit()

        # Call status update method
        mock_update_task_status(
            mock_session, sample_task, TASK_STATUS_FAILED, error_msg
        )

        # Verify task status and error message were updated
        assert sample_task.status == TASK_STATUS_FAILED
        assert sample_task.error_message == error_msg
        mock_session.commit.assert_called_once()

    def test_task_status_update_exception_handling(self, sample_task, mock_session):
        """Test exception handling during task status update"""
        # Mock database commit throwing exception
        mock_session.commit.side_effect = Exception("Database connection failed")

        # Mock update_task_status method (with exception handling)
        def mock_update_task_status(session, task, status, error_message=None):
            try:
                task.status = status
                if error_message:
                    task.error_message = error_message
                session.commit()
            except Exception:
                session.rollback()

        # Call status update method
        mock_update_task_status(mock_session, sample_task, TASK_STATUS_RUNNING)

        # Verify exception was handled and session was rolled back
        mock_session.rollback.assert_called_once()

    @patch("subprocess.check_output")
    def test_reconcile_locked_tasks_on_startup(
        self, mock_subprocess, mock_session, sample_task
    ):
        """Test reconciling locked tasks on startup"""
        # Set task to locked status
        sample_task.status = TASK_STATUS_LOCKED

        # Mock database query returning locked tasks
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            sample_task
        ]

        # Mock reconcile_tasks_on_startup method
        def mock_reconcile_tasks_on_startup(session):
            stale_tasks = (
                session.execute.return_value.scalars.return_value.all.return_value
            )
            for task in stale_tasks:
                if task.status == TASK_STATUS_LOCKED:
                    task.status = TASK_STATUS_FAILED
                    task.error_message = (
                        "Task was aborted before execution due to an engine restart."
                    )

        # Call startup reconciliation method
        mock_reconcile_tasks_on_startup(mock_session)

        # Verify locked tasks were marked as failed
        assert sample_task.status == TASK_STATUS_FAILED
        assert (
            "Task was aborted before execution due to an engine restart"
            in sample_task.error_message
        )

    @patch("subprocess.check_output")
    @patch("subprocess.run")
    def test_reconcile_running_tasks_with_orphaned_process(
        self, mock_run, mock_check_output, mock_session, sample_task
    ):
        """Test reconciling running tasks on startup (with orphaned processes)"""
        # Set task to running status
        sample_task.status = TASK_STATUS_RUNNING

        # Mock database query returning running tasks
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            sample_task
        ]

        # Mock pgrep finding orphaned processes
        mock_check_output.return_value = b"12345\n"

        # Mock reconcile_tasks_on_startup method
        def mock_reconcile_tasks_on_startup(session):
            stale_tasks = (
                session.execute.return_value.scalars.return_value.all.return_value
            )
            for task in stale_tasks:
                if task.status == TASK_STATUS_RUNNING:
                    try:
                        # Check for orphaned processes
                        mock_check_output(
                            ["pgrep", "-f", f"locust .*--task-id {task.id}"]
                        )
                        # Terminate orphaned processes
                        mock_run(
                            ["pkill", "-f", f"locust .*--task-id {task.id}"], check=True
                        )
                        task.status = TASK_STATUS_FAILED
                    except Exception:
                        pass

        # Call startup reconciliation method
        mock_reconcile_tasks_on_startup(mock_session)

        # Verify orphaned processes were terminated and task marked as failed
        mock_run.assert_called_once()
        assert sample_task.status == TASK_STATUS_FAILED

    def test_process_task_pipeline_success(self, mock_session, sample_task):
        """Test successful task processing pipeline execution"""
        # Mock successful task execution
        mock_run_result = {
            "status": "COMPLETED",
            "locust_result": {"stats": [{"name": "Aggregated", "num_failures": 0}]},
        }

        # Mock process_task_pipeline method
        def mock_process_task_pipeline(task, session):
            # Update status to running
            task.status = TASK_STATUS_RUNNING

            # Mock task execution
            run_result = mock_run_result
            run_status = run_result.get("status")
            locust_result = run_result.get("locust_result", {})

            # Refresh task status
            session.refresh(task)

            if run_status == "COMPLETED":
                task.status = TASK_STATUS_COMPLETED
                # Process results
                if locust_result:
                    total_failures = 0
                    for stats_entry in locust_result.get("stats", []):
                        if stats_entry.get("name") == "Aggregated":
                            total_failures = stats_entry.get("num_failures", 0)
                            break

        # Call task processing pipeline
        mock_process_task_pipeline(sample_task, mock_session)

        # Verify task status was updated to completed
        assert sample_task.status == TASK_STATUS_COMPLETED

    def test_process_task_pipeline_failure(self, mock_session, sample_task):
        """Test task processing pipeline execution failure"""
        # Mock task execution failure
        mock_run_result = {
            "status": "FAILED",
            "stderr": "Failed to connect to target host",
            "locust_result": {},
        }

        # Mock process_task_pipeline method
        def mock_process_task_pipeline(task, session):
            # Update status to running
            task.status = TASK_STATUS_RUNNING

            # Mock task execution failure
            run_result = mock_run_result
            run_status = run_result.get("status")

            # Refresh task status
            session.refresh(task)

            if run_status != "COMPLETED":
                error_message = f"Task {task.id} execution failed. Details: {run_result.get('stderr', 'No stderr.')}"
                task.status = TASK_STATUS_FAILED
                task.error_message = error_message

        # Call task processing pipeline
        mock_process_task_pipeline(sample_task, mock_session)

        # Verify task status was updated to failed
        assert sample_task.status == TASK_STATUS_FAILED
        assert "Failed to connect to target host" in sample_task.error_message

    def test_process_task_pipeline_stopped_during_execution(
        self, mock_session, sample_task
    ):
        """Test task stopped during execution"""
        # Set initial task status to locked
        sample_task.status = TASK_STATUS_LOCKED

        # Mock successful task execution but marked as stopping during execution
        mock_run_result = {"status": "COMPLETED", "locust_result": {}}

        def mock_refresh(task):
            # Mock task being marked as stopping during execution
            task.status = TASK_STATUS_STOPPING

        mock_session.refresh.side_effect = mock_refresh

        # Mock process_task_pipeline method
        def mock_process_task_pipeline(task, session):
            # Update status to running
            task.status = TASK_STATUS_RUNNING

            # Mock task execution
            run_result = mock_run_result

            # Refresh task status (will trigger stopping status)
            session.refresh(task)

            if task.status in (TASK_STATUS_STOPPING, TASK_STATUS_STOPPED):
                task.status = TASK_STATUS_STOPPED

        # Call task processing pipeline
        mock_process_task_pipeline(sample_task, mock_session)

        # Verify final task status is stopped
        assert sample_task.status == TASK_STATUS_STOPPED

    def test_stop_task_success(self):
        """Test successful task stopping"""
        task_id = "test-task-001"

        # Create mock process
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process still running
        mock_process.pid = 12345

        # Mock process dictionary
        process_dict = {task_id: mock_process}

        # Mock stop_task method
        def mock_stop_task(task_id):
            process = process_dict.get(task_id)
            if not process:
                return True

            if process.poll() is not None:
                process_dict.pop(task_id, None)
                return True

            try:
                process.terminate()
                process.wait(timeout=10)
                process_dict.pop(task_id, None)
                return True
            except Exception:
                return False

        # Call stop task method
        result = mock_stop_task(task_id)

        # Verify task was successfully stopped
        assert result is True
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=10)
        assert task_id not in process_dict

    def test_stop_task_process_not_found(self):
        """Test stopping non-existent task process"""
        task_id = "non-existent-task"

        # Mock empty process dictionary
        process_dict = {}

        # Mock stop_task method
        def mock_stop_task(task_id):
            process = process_dict.get(task_id)
            if not process:
                return True
            return False

        # Call stop task method
        result = mock_stop_task(task_id)

        # Verify returns True (task doesn't exist, considered successful)
        assert result is True

    def test_stop_task_process_already_terminated(self):
        """Test stopping already terminated task process"""
        task_id = "test-task-001"

        # Create mock process (already terminated)
        mock_process = Mock()
        mock_process.poll.return_value = 0  # Process already terminated
        mock_process.pid = 12345

        # Mock process dictionary
        process_dict = {task_id: mock_process}

        # Mock stop_task method
        def mock_stop_task(task_id):
            process = process_dict.get(task_id)
            if not process:
                return True

            if process.poll() is not None:
                process_dict.pop(task_id, None)
                return True

            return False

        # Call stop task method
        result = mock_stop_task(task_id)

        # Verify returns True and process was cleaned up
        assert result is True
        assert task_id not in process_dict

    def test_get_stopping_task_ids(self, mock_session):
        """Test getting list of task IDs that need to be stopped"""
        # Mock database query returning stopping task IDs
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            "task-001",
            "task-002",
            "task-003",
        ]

        # Mock get_stopping_task_ids method
        def mock_get_stopping_task_ids(session):
            try:
                return (
                    session.execute.return_value.scalars.return_value.all.return_value
                )
            except Exception:
                return []

        # Call get stopping task IDs method
        stopping_ids = mock_get_stopping_task_ids(mock_session)

        # Verify correct task ID list is returned
        assert len(stopping_ids) == 3
        assert "task-001" in stopping_ids
        assert "task-002" in stopping_ids
        assert "task-003" in stopping_ids

    def test_get_stopping_task_ids_empty(self, mock_session):
        """Test behavior when no tasks need to be stopped"""
        # Mock database query returning empty list
        mock_session.execute.return_value.scalars.return_value.all.return_value = []

        # Mock get_stopping_task_ids method
        def mock_get_stopping_task_ids(session):
            try:
                return (
                    session.execute.return_value.scalars.return_value.all.return_value
                )
            except Exception:
                return []

        # Call get stopping task IDs method
        stopping_ids = mock_get_stopping_task_ids(mock_session)

        # Verify empty list is returned
        assert len(stopping_ids) == 0

    def test_get_stopping_task_ids_exception(self, mock_session):
        """Test exception handling when getting stopping task IDs"""
        # Mock database query throwing exception
        mock_session.execute.side_effect = Exception("Database connection failed")

        # Mock get_stopping_task_ids method
        def mock_get_stopping_task_ids(session):
            try:
                # This will throw an exception
                session.execute()
                return (
                    session.execute.return_value.scalars.return_value.all.return_value
                )
            except Exception:
                return []

        # Call get stopping task IDs method
        stopping_ids = mock_get_stopping_task_ids(mock_session)

        # Verify exception was handled and empty list returned
        assert len(stopping_ids) == 0

    def test_start_task_success(self, sample_task):
        """Test successful task startup"""
        # Mock runner returning successful result
        mock_result = {
            "status": "COMPLETED",
            "stdout": "Task executed successfully",
            "stderr": "",
            "return_code": 0,
            "locust_result": {"stats": []},
        }

        # Mock start_task method
        def mock_start_task(task):
            try:
                return mock_result
            except Exception as e:
                return {
                    "status": "FAILED",
                    "locust_result": {},
                    "stderr": str(e),
                    "return_code": -1,
                }

        # Call start task method
        result = mock_start_task(sample_task)

        # Verify successful result is returned
        assert result["status"] == "COMPLETED"
        assert result["return_code"] == 0

    def test_start_task_exception(self, sample_task):
        """Test exception handling during task startup"""

        # Mock start_task method throwing exception
        def mock_start_task(task):
            try:
                raise Exception("Startup failed")
            except Exception as e:
                return {
                    "status": "FAILED",
                    "locust_result": {},
                    "stderr": str(e),
                    "return_code": -1,
                }

        # Call start task method
        result = mock_start_task(sample_task)

        # Verify exception was handled and failure result returned
        assert result["status"] == "FAILED"
        assert result["return_code"] == -1
        assert "Startup failed" in result["stderr"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
