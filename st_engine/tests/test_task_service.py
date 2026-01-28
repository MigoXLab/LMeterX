"""
Tests for TaskService behaviors.
"""

from unittest.mock import Mock, patch

import pytest

from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_FAILED_REQUESTS,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
)
from service.task_service import TaskService


@pytest.fixture
def task_service():
    return TaskService()


def test_cleanup_task_files_removes_files(task_service, tmp_path):
    test_data_file = tmp_path / "test_data.jsonl"
    cert_file = tmp_path / "cert.pem"
    key_file = tmp_path / "key.pem"
    test_data_file.write_text("test content")
    cert_file.write_text("cert")
    key_file.write_text("key")

    mock_task = Mock()
    mock_task.id = "test_task_123"
    mock_task.test_data = str(test_data_file)
    mock_task.cert_file = str(cert_file)
    mock_task.key_file = str(key_file)

    task_service._cleanup_task_files(mock_task)

    assert not test_data_file.exists()
    assert not cert_file.exists()
    assert not key_file.exists()


def test_cleanup_task_files_ignores_default_dataset(task_service):
    mock_task = Mock()
    mock_task.id = "test_task_default"
    mock_task.test_data = "default"
    mock_task.cert_file = None
    mock_task.key_file = None

    task_service._cleanup_task_files(mock_task)


def test_cleanup_task_files_ignores_jsonl_content(task_service):
    mock_task = Mock()
    mock_task.id = "test_task_jsonl"
    mock_task.test_data = '{"prompt": "test", "completion": "response"}'
    mock_task.cert_file = None
    mock_task.key_file = None

    task_service._cleanup_task_files(mock_task)


def test_update_task_status_truncates_error_message(task_service):
    mock_session = Mock()
    mock_task = Mock()
    mock_task.id = "test_task_1"

    long_error_message = "x" * 70000
    task_service.update_task_status(
        mock_session, mock_task, TASK_STATUS_RUNNING, long_error_message
    )

    assert "truncated" in mock_task.error_message
    mock_session.commit.assert_called_once()


def test_update_task_status_calls_cleanup_for_terminal_states(task_service):
    mock_session = Mock()
    mock_task = Mock()
    mock_task.id = "test_task_terminal"

    terminal_statuses = [
        TASK_STATUS_COMPLETED,
        TASK_STATUS_FAILED,
        TASK_STATUS_STOPPED,
        TASK_STATUS_FAILED_REQUESTS,
    ]

    with patch.object(task_service, "_cleanup_task_files") as mock_cleanup:
        for status in terminal_statuses:
            mock_cleanup.reset_mock()
            task_service.update_task_status(mock_session, mock_task, status)
            mock_cleanup.assert_called_once_with(mock_task)


def test_update_task_status_skips_cleanup_for_non_terminal(task_service):
    mock_session = Mock()
    mock_task = Mock()
    mock_task.id = "test_task_running"

    with patch.object(task_service, "_cleanup_task_files") as mock_cleanup:
        task_service.update_task_status(mock_session, mock_task, TASK_STATUS_RUNNING)
        mock_cleanup.assert_not_called()


def test_get_and_lock_task_locks_task(task_service):
    mock_session = Mock()
    mock_task = Mock()
    mock_task.id = "task-001"
    mock_task.status = "created"

    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_session.execute.return_value = mock_result

    locked_task = task_service.get_and_lock_task(mock_session)

    assert locked_task is mock_task
    assert mock_task.status == "locked"
    mock_session.commit.assert_called_once()


def test_get_and_lock_task_returns_none(task_service):
    mock_session = Mock()
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    locked_task = task_service.get_and_lock_task(mock_session)

    assert locked_task is None
    mock_session.commit.assert_not_called()


def test_get_stopping_task_ids_handles_exception(task_service):
    mock_session = Mock()
    mock_session.execute.side_effect = Exception("db error")

    result = task_service.get_stopping_task_ids(mock_session)

    assert result == []


def test_stop_task_returns_true_when_process_not_found(task_service):
    result = task_service.stop_task("missing_task")
    assert result is True
