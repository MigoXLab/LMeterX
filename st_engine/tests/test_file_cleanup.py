"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Test file cleanup functionality for completed/failed tasks.
"""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from config.business import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_FAILED_REQUESTS,
    TASK_STATUS_STOPPED,
)
from service.task_service import TaskService


class TestFileCleanup(unittest.TestCase):
    """Test cases for automatic file cleanup functionality."""

    def setUp(self):
        """Set up test environment."""
        self.task_service = TaskService()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment."""
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_temp_file(self, filename: str) -> str:
        """Create a temporary file for testing."""
        file_path = os.path.join(self.temp_dir, filename)
        with open(file_path, "w") as f:
            f.write("test content")
        return file_path

    def test_cleanup_task_files_with_all_file_types(self):
        """Test file cleanup when task has all types of files."""
        # Create test files
        test_data_file = self.create_temp_file("test_data.jsonl")
        cert_file = self.create_temp_file("cert.pem")
        key_file = self.create_temp_file("key.pem")

        # Create mock task
        mock_task = Mock()
        mock_task.id = "test_task_123"
        mock_task.test_data = test_data_file
        mock_task.cert_file = cert_file
        mock_task.key_file = key_file

        # Verify files exist before cleanup
        self.assertTrue(os.path.exists(test_data_file))
        self.assertTrue(os.path.exists(cert_file))
        self.assertTrue(os.path.exists(key_file))

        # Execute cleanup
        with patch("utils.logger.logger") as mock_logger:
            self.task_service._cleanup_task_files(mock_task)

        # Verify files are removed
        self.assertFalse(os.path.exists(test_data_file))
        self.assertFalse(os.path.exists(cert_file))
        self.assertFalse(os.path.exists(key_file))

    def test_cleanup_task_files_ignores_default_dataset(self):
        """Test that cleanup ignores default dataset and JSONL content."""
        mock_task = Mock()
        mock_task.id = "test_task_456"
        mock_task.test_data = "default"  # Should not attempt to delete
        mock_task.cert_file = None
        mock_task.key_file = None

        # Should not raise any exceptions
        with patch("utils.logger.logger") as mock_logger:
            self.task_service._cleanup_task_files(mock_task)

    def test_cleanup_task_files_ignores_jsonl_content(self):
        """Test that cleanup ignores JSONL content strings."""
        mock_task = Mock()
        mock_task.id = "test_task_789"
        mock_task.test_data = '{"prompt": "test", "completion": "response"}'
        mock_task.cert_file = None
        mock_task.key_file = None

        # Should not raise any exceptions
        with patch("utils.logger.logger") as mock_logger:
            self.task_service._cleanup_task_files(mock_task)

    def test_cleanup_handles_missing_files_gracefully(self):
        """Test that cleanup handles missing files without errors."""
        mock_task = Mock()
        mock_task.id = "test_task_missing"
        mock_task.test_data = "/non/existent/file.jsonl"
        mock_task.cert_file = "/non/existent/cert.pem"
        mock_task.key_file = "/non/existent/key.pem"

        # Should not raise any exceptions
        with patch("utils.logger.logger") as mock_logger:
            self.task_service._cleanup_task_files(mock_task)

    @patch("service.task_service.TaskService._cleanup_task_files")
    def test_cleanup_called_on_terminal_status_update(self, mock_cleanup):
        """Test that file cleanup is called when task reaches terminal status."""
        mock_session = Mock()
        mock_task = Mock()
        mock_task.id = "test_task_terminal"

        terminal_statuses = [
            TASK_STATUS_COMPLETED,
            TASK_STATUS_FAILED,
            TASK_STATUS_STOPPED,
            TASK_STATUS_FAILED_REQUESTS,
        ]

        for status in terminal_statuses:
            with self.subTest(status=status):
                mock_cleanup.reset_mock()
                self.task_service.update_task_status(mock_session, mock_task, status)
                mock_cleanup.assert_called_once_with(mock_task)

    @patch("service.task_service.TaskService._cleanup_task_files")
    def test_cleanup_not_called_on_non_terminal_status(self, mock_cleanup):
        """Test that file cleanup is not called for non-terminal statuses."""
        mock_session = Mock()
        mock_task = Mock()
        mock_task.id = "test_task_running"

        non_terminal_statuses = ["created", "running", "stopping", "locked"]

        for status in non_terminal_statuses:
            with self.subTest(status=status):
                mock_cleanup.reset_mock()
                self.task_service.update_task_status(mock_session, mock_task, status)
                mock_cleanup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
