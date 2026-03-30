"""
Tests for HttpTaskService lifecycle management:
  - status updates & error message truncation
  - get_and_lock_task
  - stop_task (process not found / already finished)
  - pipeline: soft-delete check, status resolution, exception handling
  - reconciliation on startup (owned, other-engine, locked, pgrep missing)
"""

from unittest.mock import Mock, patch

import pytest

from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_FAILED_REQUESTS,
    TASK_STATUS_LOCKED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
    TASK_STATUS_STOPPING,
)
from service.http_task_service import HttpTaskService


@pytest.fixture
def task_service():
    with patch("service.http_task_service.HttpLocustRunner"):
        with patch("service.http_task_service.HttpResultService"):
            return HttpTaskService()


# =====================================================================
# update_task_status
# =====================================================================
class TestUpdateTaskStatus:
    def test_basic_status_update(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-status-001"

        task_service.update_task_status(session, task, TASK_STATUS_RUNNING)
        assert task.status == TASK_STATUS_RUNNING
        session.commit.assert_called_once()

    def test_error_message_truncation(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-trunc-001"

        long_error = "x" * 70000
        task_service.update_task_status(session, task, TASK_STATUS_FAILED, long_error)

        assert "truncated" in task.error_message
        assert len(task.error_message) < 66000

    def test_short_error_not_truncated(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-short-err"

        short_error = "Something went wrong"
        task_service.update_task_status(session, task, TASK_STATUS_FAILED, short_error)
        assert task.error_message == short_error


# =====================================================================
# get_and_lock_task
# =====================================================================
class TestGetAndLockTask:
    def test_locks_task(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-lock-001"
        task.status = "created"
        result = Mock()
        result.scalar_one_or_none.return_value = task
        session.execute.return_value = result

        locked = task_service.get_and_lock_task(session)

        assert locked is task
        assert task.status == "locked"
        session.commit.assert_called_once()

    def test_returns_none_when_no_task(self, task_service):
        session = Mock()
        result = Mock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        locked = task_service.get_and_lock_task(session)
        assert locked is None
        session.commit.assert_not_called()

    def test_handles_db_error(self, task_service):
        from sqlalchemy.exc import OperationalError

        session = Mock()
        session.execute.side_effect = OperationalError("conn lost", {}, None)

        locked = task_service.get_and_lock_task(session)
        assert locked is None
        session.rollback.assert_called()


# =====================================================================
# get_stopping_task_ids
# =====================================================================
class TestGetStoppingTaskIds:
    def test_returns_task_ids(self, task_service):
        session = Mock()
        session.execute.return_value.scalars.return_value.all.return_value = [
            "task-stop-1",
            "task-stop-2",
        ]

        result = task_service.get_stopping_task_ids(session)
        assert result == ["task-stop-1", "task-stop-2"]

    def test_handles_exception(self, task_service):
        session = Mock()
        session.execute.side_effect = Exception("db error")

        result = task_service.get_stopping_task_ids(session)
        assert result == []


# =====================================================================
# stop_task
# =====================================================================
class TestStopTask:
    def test_returns_true_when_process_not_found(self, task_service):
        result = task_service.stop_task("missing-task")
        assert result is True

    def test_returns_true_when_process_already_finished(self, task_service):
        process = Mock()
        process.poll.return_value = 0  # Already exited
        task_service.runner._process_dict = {"task-done": process}

        with patch("service.http_task_service.cleanup_task_resources"):
            result = task_service.stop_task("task-done")

        assert result is True


# =====================================================================
# _resolve_task_status
# =====================================================================
class TestResolveTaskStatus:
    def test_completed_with_results(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-resolve-001"
        task.status = TASK_STATUS_RUNNING

        run_result = {
            "status": "COMPLETED",
            "locust_result": {"locust_stats": [{"task_id": "task-resolve-001"}]},
        }

        with patch.object(task_service, "update_task_status") as mock_update:
            task_service._resolve_task_status(session, task, run_result, Mock())

        mock_update.assert_called_with(session, task, TASK_STATUS_COMPLETED)
        task_service.result_service.insert_locust_results.assert_called_once()

    def test_completed_without_results_marks_failed(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-resolve-002"
        task.status = TASK_STATUS_RUNNING

        run_result = {"status": "COMPLETED", "locust_result": {}}

        with patch.object(task_service, "update_task_status") as mock_update:
            task_service._resolve_task_status(session, task, run_result, Mock())

        # Should be called twice: first COMPLETED, then FAILED
        assert mock_update.call_count == 2
        last_call = mock_update.call_args_list[-1]
        assert last_call[0][2] == TASK_STATUS_FAILED

    def test_stopped_by_signal(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-resolve-003"
        task.status = TASK_STATUS_RUNNING

        run_result = {"status": "STOPPED", "locust_result": {}}

        with patch.object(task_service, "update_task_status") as mock_update:
            task_service._resolve_task_status(session, task, run_result, Mock())

        mock_update.assert_called_with(session, task, TASK_STATUS_STOPPED)

    def test_stopping_status_marks_stopped(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-resolve-004"
        task.status = TASK_STATUS_STOPPING

        run_result = {"status": "COMPLETED", "locust_result": {}}

        with patch.object(task_service, "update_task_status") as mock_update:
            task_service._resolve_task_status(session, task, run_result, Mock())

        mock_update.assert_called_with(session, task, TASK_STATUS_STOPPED)

    def test_failed_requests_persists_results(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-resolve-005"
        task.status = TASK_STATUS_RUNNING

        run_result = {
            "status": "FAILED_REQUESTS",
            "locust_result": {"locust_stats": [{"task_id": "task-resolve-005"}]},
        }

        with patch.object(task_service, "update_task_status") as mock_update:
            task_service._resolve_task_status(session, task, run_result, Mock())

        mock_update.assert_called_with(session, task, TASK_STATUS_FAILED_REQUESTS)
        task_service.result_service.insert_locust_results.assert_called_once()

    def test_generic_failure(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-resolve-006"
        task.status = TASK_STATUS_RUNNING

        run_result = {
            "status": "FAILED",
            "locust_result": {},
            "stderr": "Segfault occurred",
        }

        with patch.object(task_service, "update_task_status") as mock_update:
            task_service._resolve_task_status(session, task, run_result, Mock())

        mock_update.assert_called_with(
            session, task, TASK_STATUS_FAILED, "Segfault occurred"
        )


# =====================================================================
# process_task_pipeline
# =====================================================================
class TestProcessTaskPipeline:
    def test_skips_soft_deleted_task(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-pipeline-del"
        task.is_deleted = 1

        with (
            patch("service.http_task_service.add_task_log_sink", return_value=1),
            patch("service.http_task_service.remove_task_log_sink"),
            patch.object(task_service, "update_task_status") as mock_update,
            patch.object(task_service, "start_task") as mock_start,
        ):
            task_service.process_task_pipeline(task, session)

        mock_start.assert_not_called()
        # Should not update status for soft-deleted tasks
        mock_update.assert_not_called()

    def test_runs_normal_task(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-pipeline-normal"
        task.is_deleted = 0
        task.status = TASK_STATUS_RUNNING

        with (
            patch("service.http_task_service.add_task_log_sink", return_value=1),
            patch("service.http_task_service.remove_task_log_sink"),
            patch.object(task_service, "update_task_status"),
            patch.object(task_service, "_resolve_task_status"),
            patch.object(
                task_service,
                "start_task",
                return_value={
                    "status": "COMPLETED",
                    "locust_result": {},
                    "stderr": "",
                    "return_code": 0,
                },
            ) as mock_start,
        ):
            task_service.process_task_pipeline(task, session)

        mock_start.assert_called_once_with(task)

    def test_handles_general_exception(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-pipeline-err"
        task.is_deleted = 0

        with (
            patch("service.http_task_service.add_task_log_sink", return_value=1),
            patch("service.http_task_service.remove_task_log_sink"),
            patch.object(task_service, "update_task_status"),
            patch.object(task_service, "start_task", side_effect=RuntimeError("boom")),
        ):
            # Should not raise
            task_service.process_task_pipeline(task, session)

    def test_log_sink_always_removed(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-pipeline-cleanup"
        task.is_deleted = 0

        with (
            patch(
                "service.http_task_service.add_task_log_sink", return_value=42
            ) as mock_add,
            patch("service.http_task_service.remove_task_log_sink") as mock_remove,
            patch.object(task_service, "update_task_status"),
            patch.object(task_service, "start_task", side_effect=RuntimeError("boom")),
        ):
            task_service.process_task_pipeline(task, session)

        mock_remove.assert_called_once_with(42)


# =====================================================================
# reconcile_tasks_on_startup
# =====================================================================
class TestReconcileTasksOnStartup:
    def test_skips_tasks_owned_by_other_engine(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-other-engine"
        task.status = TASK_STATUS_RUNNING
        task.engine_id = "engine-other-pod"

        result = Mock()
        result.scalars.return_value.all.return_value = [task]
        session.execute.return_value = result

        with (
            patch("service.http_task_service.add_task_log_sink", return_value=1),
            patch("service.http_task_service.remove_task_log_sink"),
            patch.object(task_service, "update_task_status") as mock_update,
        ):
            task_service.reconcile_tasks_on_startup(session)

        mock_update.assert_not_called()

    def test_locked_task_marked_failed(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-locked-restart"
        task.status = TASK_STATUS_LOCKED

        with patch("service.http_task_service.ENGINE_ID", "my-engine"):
            task.engine_id = "my-engine"

            result = Mock()
            result.scalars.return_value.all.return_value = [task]
            session.execute.return_value = result

            with (
                patch("service.http_task_service.add_task_log_sink", return_value=1),
                patch("service.http_task_service.remove_task_log_sink"),
                patch.object(task_service, "update_task_status") as mock_update,
            ):
                task_service.reconcile_tasks_on_startup(session)

            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[0][2] == TASK_STATUS_FAILED
            assert (
                "aborted" in call_args[0][3].lower()
                or "restart" in call_args[0][3].lower()
            )

    def test_keeps_running_when_pgrep_missing(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-pgrep-missing"
        task.status = TASK_STATUS_RUNNING

        with patch("service.http_task_service.ENGINE_ID", "my-engine"):
            task.engine_id = "my-engine"

            result = Mock()
            result.scalars.return_value.all.return_value = [task]
            session.execute.return_value = result

            with (
                patch("service.http_task_service.add_task_log_sink", return_value=1),
                patch("service.http_task_service.remove_task_log_sink"),
                patch.object(task_service, "update_task_status") as mock_update,
                patch(
                    "service.http_task_service.subprocess.check_output",
                    side_effect=FileNotFoundError("pgrep"),
                ),
            ):
                task_service.reconcile_tasks_on_startup(session)

            mock_update.assert_not_called()

    def test_empty_engine_id_skipped(self, task_service):
        session = Mock()
        task = Mock()
        task.id = "task-no-engine"
        task.status = TASK_STATUS_RUNNING
        task.engine_id = None  # empty

        result = Mock()
        result.scalars.return_value.all.return_value = [task]
        session.execute.return_value = result

        with (
            patch("service.http_task_service.add_task_log_sink", return_value=1),
            patch("service.http_task_service.remove_task_log_sink"),
            patch.object(task_service, "update_task_status") as mock_update,
        ):
            task_service.reconcile_tasks_on_startup(session)

        mock_update.assert_not_called()


# =====================================================================
# start_task
# =====================================================================
class TestStartTask:
    def test_returns_runner_result(self, task_service):
        task = Mock()
        task.id = "task-start-001"

        expected = {
            "status": "COMPLETED",
            "locust_result": {},
            "stderr": "",
            "return_code": 0,
        }
        task_service.runner.run_locust_process.return_value = expected

        result = task_service.start_task(task)
        assert result == expected

    def test_catches_exception(self, task_service):
        task = Mock()
        task.id = "task-start-err"
        task_service.runner.run_locust_process.side_effect = RuntimeError("crash")

        result = task_service.start_task(task)
        assert result["status"] == "FAILED"
        assert "crash" in result["stderr"]
