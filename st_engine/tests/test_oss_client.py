"""OSS client unit tests: download, local path pass-through, cleanup."""

import os
import sys
from unittest.mock import MagicMock, patch

import httpx

from client.oss_client import cleanup_task_files, download_test_data, ensure_temp_dir


class TestEnsureTempDir:
    """Tests for ensure_temp_dir helper."""

    def test_creates_directory(self, tmp_path):
        """Test that ensure_temp_dir creates the task directory."""
        with patch("client.oss_client.TEMP_DIR", str(tmp_path)):
            result = ensure_temp_dir("task-123")

        expected = os.path.join(str(tmp_path), "task-123")
        assert result == expected
        assert os.path.isdir(expected)


class TestDownloadTestData:
    """Tests for download_test_data function."""

    def test_none_url(self):
        """Test that None URL returns None."""
        result = download_test_data("task-001", None)
        assert result is None

    def test_empty_url(self):
        """Test that empty URL returns None."""
        result = download_test_data("task-001", "")
        assert result is None

    def test_local_path_passthrough(self, tmp_path):
        """Test that local path is returned directly if file exists."""
        test_file = tmp_path / "data.csv"
        test_file.write_text("col1,col2\n1,2\n")

        result = download_test_data("task-001", str(test_file))
        assert result == str(test_file)

    def test_local_path_not_found(self):
        """Test that non-existent local path returns None."""
        result = download_test_data("task-001", "/nonexistent/path/data.csv")
        assert result is None

    def test_download_http_url(self, tmp_path):
        """Test downloading a valid HTTP URL."""
        url = "https://oss.example.com/bucket/file.csv?sign=abc"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = [b"col1,col2\n", b"1,2\n"]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("client.oss_client.TEMP_DIR", str(tmp_path)):
            with patch("client.oss_client.httpx.stream", return_value=mock_response):
                result = download_test_data("task-001", url)

        assert result is not None
        assert result.endswith("file.csv")
        assert os.path.exists(result)
        with open(result) as f:
            assert f.read() == "col1,col2\n1,2\n"

    def test_download_failure(self, tmp_path):
        """Test download failure due to network error."""
        url = "https://oss.example.com/bucket/file.csv"

        with patch("client.oss_client.TEMP_DIR", str(tmp_path)):
            with patch(
                "client.oss_client.httpx.stream",
                side_effect=httpx.ConnectError("network error"),
            ):
                result = download_test_data("task-001", url)

        assert result is None


class TestCleanupTaskFiles:
    """Tests for cleanup_task_files function."""

    def test_cleanup_existing_dir(self, tmp_path):
        """Test that existing task directory is deleted."""
        task_dir = tmp_path / "task-001"
        task_dir.mkdir()
        (task_dir / "data.csv").write_text("test")

        with patch("client.oss_client.TEMP_DIR", str(tmp_path)):
            cleanup_task_files("task-001")

        assert not task_dir.exists()

    def test_cleanup_nonexistent_dir(self, tmp_path):
        """Test that cleanup does not fail for non-existent directory."""
        with patch("client.oss_client.TEMP_DIR", str(tmp_path)):
            cleanup_task_files("nonexistent-task")


class TestOssLiveLogSyncPolicy:
    @patch("client.oss_client.OSS_ENABLED", False)
    def test_live_log_sync_disabled_when_oss_disabled(self):
        from client.oss_client import is_oss_live_log_sync_enabled

        assert is_oss_live_log_sync_enabled() is False

    @patch("client.oss_client.OSS_ENABLED", True)
    @patch("client.oss_client.SLS_ENABLED", True)
    @patch("client.oss_client.OSS_LIVE_LOG_SYNC_ENABLED", "")
    def test_live_log_sync_auto_disabled_when_sls_enabled(self):
        from client.oss_client import is_oss_live_log_sync_enabled

        assert is_oss_live_log_sync_enabled() is False

    @patch("client.oss_client.OSS_ENABLED", True)
    @patch("client.oss_client.SLS_ENABLED", False)
    @patch("client.oss_client.OSS_LIVE_LOG_SYNC_ENABLED", "")
    def test_live_log_sync_auto_enabled_as_sls_fallback(self):
        from client.oss_client import is_oss_live_log_sync_enabled

        assert is_oss_live_log_sync_enabled() is True

    @patch("client.oss_client.OSS_ENABLED", True)
    @patch("client.oss_client.SLS_ENABLED", True)
    @patch("client.oss_client.OSS_LIVE_LOG_SYNC_ENABLED", "true")
    def test_live_log_sync_can_be_forced_on(self):
        from client.oss_client import is_oss_live_log_sync_enabled

        assert is_oss_live_log_sync_enabled() is True


class TestOssSystemLogSnapshotPolicy:
    @patch("client.oss_client.OSS_ENABLED", False)
    def test_system_snapshot_disabled_when_oss_disabled(self):
        from client.oss_client import is_oss_system_log_snapshot_enabled

        assert is_oss_system_log_snapshot_enabled() is False

    @patch("client.oss_client.OSS_ENABLED", True)
    @patch("client.oss_client.SLS_ENABLED", True)
    @patch("client.oss_client.OSS_LIVE_LOG_SYNC_ENABLED", "")
    def test_system_snapshot_auto_enabled_as_backend_fallback(self):
        from client.oss_client import is_oss_system_log_snapshot_enabled

        assert is_oss_system_log_snapshot_enabled() is True

    @patch("client.oss_client.OSS_ENABLED", True)
    @patch("client.oss_client.SLS_ENABLED", False)
    @patch("client.oss_client.OSS_LIVE_LOG_SYNC_ENABLED", "false")
    def test_system_snapshot_can_be_forced_off(self):
        from client.oss_client import is_oss_system_log_snapshot_enabled

        assert is_oss_system_log_snapshot_enabled() is False


class TestUploadSystemLogToOss:
    """Tests for upload_system_log_to_oss function."""

    @patch("client.oss_client.OSS_ENABLED", True)
    def test_upload_system_log_uses_engine_specific_file(self, tmp_path):
        mock_boto3 = MagicMock()
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        sys.modules["boto3"] = mock_boto3
        sys.modules["botocore"] = MagicMock()
        sys.modules["botocore.config"] = MagicMock()

        engine_id = "engine-123"
        cluster_id = "local"
        log_file = tmp_path / f"engine_{engine_id}.log"
        log_file.write_text("engine specific log")

        with patch("config.base.LOG_DIR", str(tmp_path)):
            with patch("client.oss_client.os.remove"):
                from client.oss_client import OSS_BUCKET, upload_system_log_to_oss

                result = upload_system_log_to_oss(engine_id, cluster_id)

        assert result is True
        args = mock_s3.upload_file.call_args.args
        assert args[1] == OSS_BUCKET
        assert args[2] == f"logs/system/{cluster_id}/{engine_id}/engine.log"

        with open(args[0], "rb") as f:
            assert f.read() == b"engine specific log"

        sys.modules.pop("boto3", None)
        sys.modules.pop("botocore", None)
        sys.modules.pop("botocore.config", None)


class TestUploadTaskLogsToOss:
    """Tests for upload_task_logs_to_oss function."""

    @patch("client.oss_client.OSS_ENABLED", True)
    def test_upload_task_logs_to_oss_success(self, tmp_path):
        """Test uploading both main and detail logs, plus rotated logs."""
        mock_boto3 = MagicMock()
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        # Mock boto3 and botocore in sys.modules
        sys.modules["boto3"] = mock_boto3
        sys.modules["botocore"] = MagicMock()
        sys.modules["botocore.config"] = MagicMock()

        # Create a mock LOG_TASK_DIR
        log_task_dir = tmp_path / "task"
        log_task_dir.mkdir(parents=True)

        task_id = "task-999"

        # Create some mock log files for this task
        main_log = log_task_dir / f"task_{task_id}_engine.log"
        main_log.write_text("main log content")

        detail_log = log_task_dir / f"task_{task_id}_engine_detail.log"
        detail_log.write_text("detail log content")

        rotated_log = (
            log_task_dir / f"task_{task_id}_engine.2026-06-18_16-15-00_000001.log.zip"
        )
        rotated_log.write_text("rotated log zip content")

        # Create a log file for another task (should not be uploaded)
        other_log = log_task_dir / "task_task-other_engine.log"
        other_log.write_text("other log content")

        with patch("config.base.LOG_TASK_DIR", str(log_task_dir)):
            from client.oss_client import OSS_BUCKET, upload_task_logs_to_oss

            result = upload_task_logs_to_oss(task_id)

        assert result is True
        assert mock_s3.upload_file.call_count == 3

        # Verify correct files were uploaded to correct keys
        mock_s3.upload_file.assert_any_call(
            str(main_log), OSS_BUCKET, f"logs/task_{task_id}_engine.log"
        )
        mock_s3.upload_file.assert_any_call(
            str(detail_log),
            OSS_BUCKET,
            f"logs/task_{task_id}_engine_detail.log",
        )
        mock_s3.upload_file.assert_any_call(
            str(rotated_log),
            OSS_BUCKET,
            f"logs/task_{task_id}_engine.2026-06-18_16-15-00_000001.log.zip",
        )

        # Clean up sys.modules
        sys.modules.pop("boto3", None)
        sys.modules.pop("botocore", None)
        sys.modules.pop("botocore.config", None)

    @patch("client.oss_client.OSS_ENABLED", True)
    def test_upload_task_logs_to_oss_skips_archives_for_live_sync(self, tmp_path):
        """Live sync should upload current .log files only."""
        mock_boto3 = MagicMock()
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        sys.modules["boto3"] = mock_boto3
        sys.modules["botocore"] = MagicMock()
        sys.modules["botocore.config"] = MagicMock()

        log_task_dir = tmp_path / "task"
        log_task_dir.mkdir(parents=True)
        task_id = "task-999"

        main_log = log_task_dir / f"task_{task_id}_engine.log"
        main_log.write_text("main log content")
        detail_log = log_task_dir / f"task_{task_id}_engine_detail.log"
        detail_log.write_text("detail log content")
        rotated_log = (
            log_task_dir / f"task_{task_id}_engine.2026-06-18_16-15-00_000001.log.zip"
        )
        rotated_log.write_text("rotated log zip content")

        with patch("config.base.LOG_TASK_DIR", str(log_task_dir)):
            from client.oss_client import OSS_BUCKET, upload_task_logs_to_oss

            result = upload_task_logs_to_oss(task_id, include_archives=False)

        assert result is True
        assert mock_s3.upload_file.call_count == 2
        mock_s3.upload_file.assert_any_call(
            str(main_log), OSS_BUCKET, f"logs/task_{task_id}_engine.log"
        )
        mock_s3.upload_file.assert_any_call(
            str(detail_log),
            OSS_BUCKET,
            f"logs/task_{task_id}_engine_detail.log",
        )

        sys.modules.pop("boto3", None)
        sys.modules.pop("botocore", None)
        sys.modules.pop("botocore.config", None)

    @patch("client.oss_client.OSS_ENABLED", False)
    def test_upload_task_logs_to_oss_disabled(self):
        """Test that upload does nothing when OSS_ENABLED is False."""
        from client.oss_client import upload_task_logs_to_oss

        result = upload_task_logs_to_oss("task-123")
        assert result is False
