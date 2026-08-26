"""Unit tests for backend log service with OSS log transfer support."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from service.log_service import (
    _ensure_engine_logs_from_oss,
    _find_engine_log_files,
    download_task_log_svc,
    get_engine_system_log_svc,
    get_last_n_lines,
    get_task_log_svc,
)


@pytest.mark.asyncio
class TestLogServiceOSS:
    """Tests for log service OSS integration."""

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service.download_file_from_oss",
        new_callable=AsyncMock,
    )
    @patch("service.log_service.list_files_in_oss")
    async def test_ensure_engine_logs_from_oss_latest_only(
        self, mock_list_files, mock_download_file
    ):
        """Test downloading only latest logs (all_files=False)."""
        task_id = "test_task_123"
        resolved_dir = "/tmp/test_logs"

        with patch("os.path.exists", return_value=False):
            await _ensure_engine_logs_from_oss(task_id, resolved_dir, all_files=False)

        # Should download main and detail logs directly without listing OSS
        mock_list_files.assert_not_called()
        assert mock_download_file.call_count == 2
        mock_download_file.assert_any_call(
            f"logs/task_{task_id}_engine.log",
            os.path.join(resolved_dir, f"task_{task_id}_engine.log"),
        )
        mock_download_file.assert_any_call(
            f"logs/task_{task_id}_engine_detail.log",
            os.path.join(resolved_dir, f"task_{task_id}_engine_detail.log"),
        )

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service.download_file_from_oss",
        new_callable=AsyncMock,
    )
    @patch("service.log_service.list_files_in_oss")
    async def test_ensure_engine_logs_from_oss_all_files(
        self, mock_list_files, mock_download_file
    ):
        """Test downloading all logs including rotated files."""
        task_id = "test_task_123"
        resolved_dir = "/tmp/test_logs"

        # Mock OSS file list containing main log, detail log, and rotated zip
        mock_list_files.return_value = [
            f"logs/task_{task_id}_engine.log",
            f"logs/task_{task_id}_engine_detail.log",
            f"logs/task_{task_id}_engine.2026-06-18_16-15-00_000001.log.zip",
        ]

        with patch("os.path.exists", return_value=False):
            await _ensure_engine_logs_from_oss(task_id, resolved_dir, all_files=True)

        mock_list_files.assert_called_once_with(f"logs/task_{task_id}_")
        assert mock_download_file.call_count == 3
        mock_download_file.assert_any_call(
            f"logs/task_{task_id}_engine.log",
            os.path.join(resolved_dir, f"task_{task_id}_engine.log"),
        )
        mock_download_file.assert_any_call(
            f"logs/task_{task_id}_engine.2026-06-18_16-15-00_000001.log.zip",
            os.path.join(
                resolved_dir,
                f"task_{task_id}_engine.2026-06-18_16-15-00_000001.log.zip",
            ),
        )

    @patch("service.log_service.OSS_ENABLED", False)
    @patch(
        "service.log_service.download_file_from_oss",
        new_callable=AsyncMock,
    )
    async def test_ensure_engine_logs_from_oss_disabled(self, mock_download_file):
        """Test that no OSS downloads happen when OSS_ENABLED is False."""
        await _ensure_engine_logs_from_oss("test_task", "/tmp/test_logs")
        mock_download_file.assert_not_called()

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service.download_file_from_oss",
        new_callable=AsyncMock,
        return_value=False,
    )
    async def test_ensure_engine_logs_from_oss_removes_stale_latest_cache(
        self, mock_download_file, tmp_path
    ):
        """Failed OSS refresh should not leave stale task log cache readable."""
        task_id = "test_task_123"
        stale_main = tmp_path / f"task_{task_id}_engine.log"
        stale_detail = tmp_path / f"task_{task_id}_engine_detail.log"
        stale_main.write_text("old main")
        stale_detail.write_text("old detail")

        result = await _ensure_engine_logs_from_oss(task_id, str(tmp_path))

        assert result is False
        assert not stale_main.exists()
        assert not stale_detail.exists()

    @patch("service.log_service.OSS_ENABLED", True)
    @patch("service.log_service.list_files_in_oss", return_value=[])
    async def test_ensure_engine_logs_from_oss_all_files_removes_unlisted_cache(
        self, mock_list_files, tmp_path
    ):
        """Full download mode should trust current OSS listing over local cache."""
        task_id = "test_task_123"
        stale_main = tmp_path / f"task_{task_id}_engine.log"
        stale_main.write_text("old main")

        result = await _ensure_engine_logs_from_oss(
            task_id, str(tmp_path), all_files=True
        )

        assert result is False
        assert not stale_main.exists()


@pytest.mark.asyncio
class TestGetTaskLogSvcOSS:
    """Tests for get_task_log_svc integration with OSS."""

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service._ensure_engine_logs_from_oss",
        new_callable=AsyncMock,
    )
    @patch("service.log_service.read_local_file", return_value="log content")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=100)
    async def test_get_task_log_svc_calls_ensure_oss(
        self, mock_getsize, mock_exists, mock_read, mock_ensure_oss
    ):
        """Test that get_task_log_svc triggers OSS download with False."""
        task_id = "test_task_123"
        result = await get_task_log_svc(task_id, offset=0, tail=100, source="engine")

        assert result.content == "log content"
        mock_ensure_oss.assert_called_once()
        # Verify it called with all_files=False (default)
        args, kwargs = mock_ensure_oss.call_args
        assert args[0] == task_id
        assert "all_files" not in kwargs or kwargs["all_files"] is False

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service._ensure_engine_logs_from_oss",
        new_callable=AsyncMock,
    )
    @patch("os.path.exists", return_value=False)
    async def test_get_task_log_svc_returns_empty_when_remote_log_not_ready(
        self, mock_exists, mock_ensure_oss
    ):
        """Remote engine logs may not be uploaded yet; return empty content."""
        task_id = "test_task_123"

        result = await get_task_log_svc(task_id, offset=0, tail=100, source="engine")

        assert result.content == ""
        assert result.file_size == 0
        assert result.log_url == f"/logs/task/{task_id}/download?source=engine"
        mock_ensure_oss.assert_called_once()

    async def test_get_task_log_svc_reads_backend_task_lines(self, tmp_path):
        """Backend task logs are filtered from backend.log by task id."""
        task_id = "test_task_123"
        (tmp_path / "backend.log").write_text(
            f"line for {task_id}\nline for another-task\nsecond {task_id}\n"
        )

        with patch("service.log_service.LOG_DIR", str(tmp_path)):
            result = await get_task_log_svc(
                task_id, offset=0, tail=100, source="backend"
            )

        assert result.content == f"line for {task_id}\nsecond {task_id}\n"
        assert result.file_size == len(result.content.encode("utf-8"))

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service._ensure_engine_logs_from_oss",
        new_callable=AsyncMock,
    )
    @patch("service.log_service._find_engine_log_files")
    @patch("os.path.exists", return_value=True)
    @patch("os.path.getsize", return_value=100)
    async def test_download_task_log_svc_calls_ensure_oss_all_files(
        self, mock_getsize, mock_exists, mock_find_files, mock_ensure_oss
    ):
        """Test that download_task_log_svc triggers OSS with True."""
        task_id = "test_task_123"
        mock_find_files.return_value = ["/tmp/logs/task/task_test_task_123_engine.log"]

        with patch("service.log_service.FileResponse"):
            await download_task_log_svc(task_id, source="engine")
            mock_ensure_oss.assert_called_once()
            args, kwargs = mock_ensure_oss.call_args
            assert args[0] == task_id
            assert args[1].endswith(os.path.join("logs", "task"))
            assert kwargs == {"all_files": True}


@pytest.mark.asyncio
class TestGetEngineSystemLogSvc:
    """Tests for multi-cluster engine system log retrieval."""

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service.download_file_from_oss",
        new_callable=AsyncMock,
        return_value=False,
    )
    @patch("os.path.exists", return_value=False)
    async def test_returns_empty_response_when_oss_log_missing(
        self, mock_exists, mock_download_file
    ):
        result = await get_engine_system_log_svc(
            "engine_123", "aliyun-public-network", offset=0, tail=100
        )

        assert result.content == ""
        assert result.file_size == 0
        mock_download_file.assert_called_once()
        oss_key, local_cache = mock_download_file.call_args.args
        assert oss_key == "logs/system/aliyun-public-network/engine_123/engine.log"
        assert local_cache.endswith(
            os.path.join(
                "engine_cache",
                "aliyun-public-network_engine_123_engine.log",
            )
        )

    @patch("service.log_service.OSS_ENABLED", True)
    @patch(
        "service.log_service.download_file_from_oss",
        new_callable=AsyncMock,
        return_value=False,
    )
    async def test_uses_cached_engine_log_when_oss_refresh_fails(
        self, mock_download_file, tmp_path
    ):
        cache_dir = tmp_path / "engine_cache"
        cache_dir.mkdir()
        cache_file = cache_dir / "pjlab-internal-network_engine_123_engine.log"
        cache_file.write_text("cached engine log\n")

        with patch("service.log_service.LOG_DIR", str(tmp_path)):
            result = await get_engine_system_log_svc(
                "engine_123", "pjlab-internal-network", offset=0, tail=100
            )

        assert result.content == "cached engine log\n"
        assert result.file_size == len("cached engine log\n")
        assert cache_file.exists()
        mock_download_file.assert_called_once()

    @patch("service.log_service.OSS_ENABLED", False)
    @patch("service.log_service.get_service_log_svc", new_callable=AsyncMock)
    async def test_local_missing_engine_log_returns_empty_response(
        self, mock_get_service_log
    ):
        from utils.error_handler import ErrorResponse

        mock_get_service_log.side_effect = ErrorResponse.not_found(
            "Log file for service 'engine' not found"
        )

        result = await get_engine_system_log_svc(
            "engine_123", "local", offset=0, tail=100
        )

        assert result.content == ""
        assert result.file_size == 0

    @patch("service.log_service.OSS_ENABLED", False)
    async def test_local_engine_log_reads_engine_specific_file(self, tmp_path):
        engine_id = "engine_123"
        log_file = tmp_path / f"engine_{engine_id}.log"
        log_file.write_text("engine specific log\n")

        with patch("service.log_service.LOG_DIR", str(tmp_path)):
            result = await get_engine_system_log_svc(
                engine_id, "local", offset=0, tail=100
            )

        assert result.content == "engine specific log\n"
        assert result.file_size == len("engine specific log\n")


class TestFindEngineLogFiles:
    def test_find_engine_log_files_includes_main_and_detail(self, tmp_path):
        task_id = "test_task_123"
        main_log = tmp_path / f"task_{task_id}_engine.log"
        detail_log = tmp_path / f"task_{task_id}_engine_detail.log"
        rotated_main = tmp_path / f"task_{task_id}_engine.2026.log.zip"
        main_log.write_text("main")
        detail_log.write_text("detail")
        rotated_main.write_text("rotated")

        result = _find_engine_log_files(str(tmp_path), task_id)

        assert str(main_log) in result
        assert str(detail_log) in result
        assert str(rotated_main) in result


class TestGetLastNLines:
    def test_large_file_tail_ignores_trailing_newline_as_extra_line(self, tmp_path):
        log_file = tmp_path / "large.log"
        lines = [f"line-{index:03d} {'x' * 600}\n" for index in range(120)]
        log_file.write_text("".join(lines))

        result = get_last_n_lines(str(log_file), 100)

        result_lines = result.splitlines()
        assert len(result_lines) == 100
        assert result_lines[0].startswith("line-020 ")
        assert result_lines[-1].startswith("line-119 ")

    def test_large_file_tail_without_trailing_newline(self, tmp_path):
        log_file = tmp_path / "large.log"
        lines = [f"line-{index:03d} {'x' * 600}" for index in range(120)]
        log_file.write_text("\n".join(lines))

        result = get_last_n_lines(str(log_file), 100)

        result_lines = result.splitlines()
        assert len(result_lines) == 100
        assert result_lines[0].startswith("line-020 ")
        assert result_lines[-1].startswith("line-119 ")
