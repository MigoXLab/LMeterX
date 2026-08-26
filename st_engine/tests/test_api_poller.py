"""
API poller end-to-end tests: TaskProxy, execute flows, startup registration.

The api_poller module imports LlmTaskService/HttpTaskService which pull in
Locust runner code and gevent. When those modules are loaded before other
test files that also import real Locust classes, gevent monkey-patching
conflicts cause hangs at collection time. We temporarily stub the two
service modules in sys.modules while importing api_poller, then restore
them so later modules can load the real code cleanly.
"""

import asyncio
import sys
import types
from unittest.mock import MagicMock, Mock, patch

import pytest

# =====================================================================
# Temporarily stub service modules, import api_poller, then restore.
# =====================================================================
_STUB_NAMES = ["service.llm_task_service", "service.http_task_service"]
_saved = {}
_SENTINEL = object()

for _name in _STUB_NAMES:
    _saved[_name] = sys.modules.get(_name, _SENTINEL)
    mod = types.ModuleType(_name)
    if "llm" in _name:
        mod.LlmTaskService = MagicMock()  # type: ignore[attr-defined]
    if "http" in _name:
        mod.HttpTaskService = MagicMock()  # type: ignore[attr-defined]
    sys.modules[_name] = mod

from service.api_poller import (  # noqa: E402
    TaskProxy,
    _execute_http_task,
    _execute_llm_task,
    _execute_probe,
    _probe_capacity_available,
    _probe_http,
    _probe_llm,
    _regular_task_is_running,
    _start_probe_thread,
    _start_regular_task_thread,
    api_log_push_loop,
    api_task_poller,
    startup_register,
)

# Restore sys.modules so downstream test files get the real modules
for _name in _STUB_NAMES:
    prev = _saved[_name]
    if prev is _SENTINEL:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = prev  # type: ignore[assignment]


# =====================================================================
# TaskProxy
# =====================================================================
class TestTaskProxy:
    def test_attribute_access(self):
        config = {
            "id": "task-001",
            "name": "Test Task",
            "model": "gpt-4",
            "duration": 60,
        }
        proxy = TaskProxy(config)

        assert proxy.id == "task-001"
        assert proxy.name == "Test Task"
        assert proxy.model == "gpt-4"
        assert proxy.duration == 60

    def test_missing_attribute(self):
        proxy = TaskProxy({"id": "task-001"})
        assert proxy.nonexistent_field is None

    def test_is_deleted_default(self):
        proxy = TaskProxy({"id": "task-001"})
        assert proxy.is_deleted == 0

    def test_dict_preserved(self):
        config = {"id": "t1", "model": "gpt-4"}
        proxy = TaskProxy(config)
        assert proxy._config is config


class TestApiLogPushLoop:
    @patch("client.oss_client.OSS_ENABLED", True)
    @patch("client.oss_client.is_oss_live_log_sync_enabled", return_value=False)
    @patch("client.oss_client.is_oss_system_log_snapshot_enabled", return_value=True)
    @patch("service.api_poller.upload_system_log_to_oss", side_effect=KeyboardInterrupt)
    def test_system_snapshot_upload_runs_when_sls_handles_realtime(
        self, mock_upload, mock_system_snapshot, mock_live_sync
    ):
        with pytest.raises(KeyboardInterrupt):
            api_log_push_loop()

        mock_system_snapshot.assert_called_once()
        mock_live_sync.assert_called_once()
        mock_upload.assert_called_once()

    @patch("client.oss_client.OSS_ENABLED", True)
    @patch("client.oss_client.is_oss_system_log_snapshot_enabled", return_value=False)
    @patch("service.api_poller.upload_system_log_to_oss")
    def test_system_snapshot_upload_skips_when_forced_off(
        self, mock_upload, mock_system_snapshot
    ):
        api_log_push_loop()

        mock_system_snapshot.assert_called_once()
        mock_upload.assert_not_called()


# =====================================================================
# _execute_llm_task
# =====================================================================
class TestExecuteLlmTask:
    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=42)
    def test_completed_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.return_value = {
            "status": "COMPLETED",
            "locust_result": {"num_requests": 100, "rps": 10.0},
        }
        task_proxy = TaskProxy({"id": "task-001", "name": "test"})

        _execute_llm_task(service, task_proxy, "task-001")

        mock_bc.submit_results.assert_called_once()
        call_kwargs = mock_bc.submit_results.call_args[1]
        assert call_kwargs["final_status"] == "completed"
        assert call_kwargs["task_id"] == "task-001"
        mock_rm_sink.assert_called_once_with(42)

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=42)
    def test_failed_requests_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.return_value = {
            "status": "FAILED_REQUESTS",
            "locust_result": {"num_requests": 50, "num_failures": 50},
            "error_message": "All requests failed",
        }
        task_proxy = TaskProxy({"id": "task-002", "name": "test"})

        _execute_llm_task(service, task_proxy, "task-002")

        call_kwargs = mock_bc.submit_results.call_args[1]
        assert call_kwargs["final_status"] == "failed_requests"

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=42)
    def test_stopped_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.return_value = {"status": "STOPPED", "locust_result": {}}
        task_proxy = TaskProxy({"id": "task-003", "name": "test"})

        _execute_llm_task(service, task_proxy, "task-003")

        mock_bc.update_task_status.assert_called_once()
        call_kwargs = mock_bc.update_task_status.call_args[1]
        assert call_kwargs["status"] == "stopped"

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=42)
    def test_exception_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.side_effect = RuntimeError("Locust crashed")
        task_proxy = TaskProxy({"id": "task-004", "name": "test"})

        _execute_llm_task(service, task_proxy, "task-004")

        call_kwargs = mock_bc.submit_results.call_args[1]
        assert call_kwargs["final_status"] == "failed"
        assert "Pipeline error" in call_kwargs["error_message"]
        mock_rm_sink.assert_called_once_with(42)

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=42)
    def test_generic_failure_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.return_value = {
            "status": "UNKNOWN",
            "locust_result": {"num_requests": 10},
            "return_code": 1,
        }
        task_proxy = TaskProxy({"id": "task-005", "name": "test"})

        _execute_llm_task(service, task_proxy, "task-005")

        call_kwargs = mock_bc.submit_results.call_args[1]
        assert call_kwargs["final_status"] == "failed"


# =====================================================================
# _execute_http_task
# =====================================================================
class TestExecuteHttpTask:
    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=10)
    def test_completed_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.return_value = {
            "status": "COMPLETED",
            "locust_result": {"num_requests": 200, "rps": 20.0},
        }
        task_proxy = TaskProxy({"id": "http-001", "name": "http test"})

        _execute_http_task(service, task_proxy, "http-001")

        call_kwargs = mock_bc.submit_results.call_args[1]
        assert call_kwargs["final_status"] == "completed"
        mock_rm_sink.assert_called_once_with(10)

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=10)
    def test_failed_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.return_value = {
            "status": "FAILED",
            "locust_result": {},
            "return_code": 1,
        }
        task_proxy = TaskProxy({"id": "http-002", "name": "http test"})

        _execute_http_task(service, task_proxy, "http-002")

        call_kwargs = mock_bc.submit_results.call_args[1]
        assert call_kwargs["final_status"] == "failed"
        assert "exit code" in call_kwargs["error_message"]

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=10)
    def test_stopped_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.return_value = {"status": "STOPPED", "locust_result": {}}
        task_proxy = TaskProxy({"id": "http-003", "name": "http test"})

        _execute_http_task(service, task_proxy, "http-003")

        mock_bc.update_task_status.assert_called_once()
        call_kwargs = mock_bc.update_task_status.call_args[1]
        assert call_kwargs["status"] == "stopped"

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller.remove_task_log_sink")
    @patch("service.api_poller.add_task_log_sink", return_value=10)
    def test_exception_flow(self, mock_add_sink, mock_rm_sink, mock_bc):
        service = Mock()
        service.start_task.side_effect = ValueError("bad config")
        task_proxy = TaskProxy({"id": "http-004", "name": "http test"})

        _execute_http_task(service, task_proxy, "http-004")

        call_kwargs = mock_bc.submit_results.call_args[1]
        assert call_kwargs["final_status"] == "failed"
        assert "Pipeline error" in call_kwargs["error_message"]


# =====================================================================
# Regular task threading
# =====================================================================
class TestRegularTaskThreading:
    def test_regular_task_is_running_false_without_thread(self, monkeypatch):
        import service.api_poller as api_poller

        monkeypatch.setattr(api_poller, "_regular_task_thread", None)

        assert _regular_task_is_running() is False

    def test_start_regular_task_thread_guards_single_regular_task(self, monkeypatch):
        import service.api_poller as api_poller

        created_threads = []

        class FakeThread:
            def __init__(self, target, args, daemon, name):
                self.target = target
                self.args = args
                self.daemon = daemon
                self.name = name
                self.started = False
                self.alive = False
                created_threads.append(self)

            def start(self):
                self.started = True
                self.alive = True

            def is_alive(self):
                return self.alive

        monkeypatch.setattr(api_poller, "_regular_task_thread", None)
        monkeypatch.setattr(api_poller.threading, "Thread", FakeThread)

        task_data = {"id": "task-001", "type": "llm", "config": {}}
        llm_service = Mock()
        http_service = Mock()

        assert _start_regular_task_thread(task_data, llm_service, http_service) is True

        thread = created_threads[0]
        assert thread.started is True
        assert thread.daemon is True
        assert thread.name == "RegularTaskThread-task-001"
        assert thread.args == (task_data, llm_service, http_service)

        assert _start_regular_task_thread(task_data, llm_service, http_service) is False

    @patch("service.api_poller.time.sleep", side_effect=KeyboardInterrupt)
    @patch("service.api_poller._regular_task_is_running", return_value=True)
    @patch("service.api_poller.get_multiprocess_manager")
    @patch("service.api_poller.backend_client")
    def test_poller_keeps_probe_claims_while_regular_task_runs(
        self,
        mock_bc,
        mock_pm_factory,
        mock_regular_running,
        mock_sleep,
    ):
        pm = Mock()
        pm.get_all_process_groups.return_value = {}
        mock_pm_factory.return_value = pm
        mock_bc.claim_task.return_value = None

        with pytest.raises(KeyboardInterrupt):
            api_task_poller()

        import service.api_poller as api_poller

        mock_bc.claim_task.assert_called_once_with(
            engine_id=api_poller.ENGINE_ID,
            cluster_id=api_poller.CLUSTER_ID,
            task_types=["probe"],
        )


# =====================================================================
# Probe execution and threading
# =====================================================================
class TestProbeExecution:
    def test_streaming_llm_probe_collects_all_chunks_until_stream_ends(
        self, monkeypatch
    ):
        import service.api_poller as api_poller

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/event-stream"}

            async def aiter_text(self):
                yield ""
                yield 'data: {"choices": []}\n\n'
                yield "data: [DONE]\n\n"

        class FakeStreamContext:
            async def __aenter__(self):
                return FakeResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def stream(self, *args, **kwargs):
                return FakeStreamContext()

        monkeypatch.setattr(api_poller.httpx, "AsyncClient", FakeClient)

        result = _probe_llm(
            {
                "target_host": "https://model.example.com",
                "api_path": "/chat/completions",
                "model": "test-model",
                "stream_mode": True,
            },
            execution_timeout=1,
        )

        assert result["status"] == "success"
        assert result["response"]["data"] == [
            'data: {"choices": []}\n\n',
            "data: [DONE]\n\n",
        ]
        assert "completed within" in result["response"]["test_note"]

    def test_streaming_llm_probe_returns_all_chunks_collected_before_timeout(
        self, monkeypatch
    ):
        import service.api_poller as api_poller

        class SlowResponse:
            status_code = 200
            headers = {"content-type": "text/event-stream"}

            async def aiter_text(self):
                yield "event: response.created\n\n"
                yield "event: response.in_progress\n\n"
                await asyncio.sleep(1)

        class FakeStreamContext:
            async def __aenter__(self):
                return SlowResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def stream(self, *args, **kwargs):
                return FakeStreamContext()

        monkeypatch.setattr(api_poller.httpx, "AsyncClient", FakeClient)

        result = _probe_llm(
            {
                "target_host": "https://model.example.com",
                "stream_mode": True,
            },
            execution_timeout=0.01,
        )

        assert result["status"] == "success"
        assert result["response"]["data"] == [
            "event: response.created\n\n",
            "event: response.in_progress\n\n",
        ]
        assert (
            "showing all data received before the timeout"
            in result["response"]["test_note"]
        )

    def test_non_streaming_llm_probe_has_hard_total_timeout(self, monkeypatch):
        import service.api_poller as api_poller

        class SlowClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                await asyncio.sleep(1)

        monkeypatch.setattr(api_poller.httpx, "AsyncClient", SlowClient)

        with pytest.raises(TimeoutError):
            _probe_llm(
                {
                    "target_host": "https://model.example.com",
                    "stream_mode": False,
                },
                execution_timeout=0.01,
            )

    def test_non_streaming_llm_probe_preserves_response_shape(self, monkeypatch):
        import service.api_poller as api_poller

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/json"}
            text = '{"answer": "ok"}'

            def json(self):
                return {"answer": "ok"}

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return FakeResponse()

        monkeypatch.setattr(api_poller.httpx, "AsyncClient", FakeClient)

        result = _probe_llm(
            {
                "target_host": "https://model.example.com",
                "stream_mode": False,
                "request_payload": '{"model": "test-model"}',
            },
            execution_timeout=1,
        )

        assert result == {
            "status": "success",
            "response": {
                "status_code": 200,
                "headers": {"content-type": "application/json"},
                "data": {"answer": "ok"},
                "is_stream": False,
            },
            "error": None,
        }

    def test_http_probe_preserves_response_shape_and_payload(self, monkeypatch):
        import service.api_poller as api_poller

        captured = {}

        class FakeResponse:
            status_code = 204
            headers = {"x-probe": "ok"}
            text = "accepted"

        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def request(self, method, url, **kwargs):
                captured.update({"method": method, "url": url, **kwargs})
                return FakeResponse()

        monkeypatch.setattr(api_poller.httpx, "AsyncClient", FakeClient)

        result = _probe_http(
            {
                "method": "post",
                "target_url": "https://api.example.com/health",
                "request_body": '{"ping": true}',
            },
            execution_timeout=1,
        )

        assert result == {
            "status": "success",
            "http_status": 204,
            "headers": {"x-probe": "ok"},
            "body": "accepted",
        }
        assert captured["method"] == "POST"
        assert captured["json"] == {"ping": True}
        assert captured["content"] is None

    @patch("service.api_poller.logger")
    @patch("service.api_poller.backend_client")
    @patch("service.api_poller._probe_llm")
    def test_execute_probe_reports_submission_failure(
        self, mock_probe_llm, mock_bc, mock_logger
    ):
        mock_probe_llm.return_value = {"status": "success", "response": {}}
        mock_bc.submit_probe_result.return_value = False

        _execute_probe(
            {
                "id": "probe-submit-fail",
                "config": {
                    "probe_type": "llm",
                    "request_config": {},
                    "execution_timeout": 12,
                },
            }
        )

        mock_probe_llm.assert_called_once_with({}, 12.0)
        submitted_result = mock_bc.submit_probe_result.call_args.kwargs["result"]
        assert submitted_result["status"] == "success"
        assert "submission failed" in mock_logger.error.call_args.args[0]

    @patch("service.api_poller.backend_client")
    @patch("service.api_poller._probe_llm", side_effect=TimeoutError)
    def test_execute_probe_submits_total_timeout_error(self, mock_probe_llm, mock_bc):
        mock_bc.submit_probe_result.return_value = True

        _execute_probe(
            {
                "id": "probe-timeout",
                "config": {
                    "probe_type": "llm",
                    "request_config": {},
                    "execution_timeout": 7,
                },
            }
        )

        result = mock_bc.submit_probe_result.call_args.kwargs["result"]
        assert result == {
            "status": "error",
            "error": "Request exceeded the 7 second timeout.",
            "response": None,
        }

    def test_probe_worker_capacity_prevents_local_queueing(self, monkeypatch):
        import service.api_poller as api_poller

        created_threads = []

        class FakeThread:
            def __init__(self, target, args, daemon, name):
                self.target = target
                self.args = args
                self.daemon = daemon
                self.name = name
                self.alive = False
                created_threads.append(self)

            def start(self):
                self.alive = True

            def is_alive(self):
                return self.alive

        monkeypatch.setattr(api_poller, "_probe_task_threads", {})
        monkeypatch.setattr(api_poller, "PROBE_MAX_WORKERS", 1)
        monkeypatch.setattr(api_poller.threading, "Thread", FakeThread)

        assert _start_probe_thread({"id": "probe-1"}) is True
        assert _probe_capacity_available() is False
        assert created_threads[0].daemon is True
        assert created_threads[0].name == "ProbeThread-probe-1"


# =====================================================================
# startup_register
# =====================================================================
class TestStartupRegister:
    @patch("service.api_poller.time.sleep")
    @patch("service.api_poller.backend_client")
    @patch("service.api_poller._register_engine")
    def test_register_success_first_attempt(self, mock_reg, mock_bc, mock_sleep):
        mock_bc.heartbeat.return_value = {"status": "ok"}

        result = startup_register()

        assert result is True
        mock_sleep.assert_not_called()

    @patch("service.api_poller.time.sleep")
    @patch("service.api_poller.backend_client")
    @patch("service.api_poller._register_engine")
    def test_register_retries_on_failure(self, mock_reg, mock_bc, mock_sleep):
        mock_bc.heartbeat.side_effect = [
            {"status": "not_registered"},
            {"status": "not_registered"},
            {"status": "ok"},
        ]

        result = startup_register()

        assert result is True
        assert mock_sleep.call_count == 2

    @patch("service.api_poller.time.sleep")
    @patch("service.api_poller.backend_client")
    @patch("service.api_poller._register_engine")
    def test_register_fails_after_retries(self, mock_reg, mock_bc, mock_sleep):
        mock_bc.heartbeat.return_value = {"status": "not_registered"}

        result = startup_register()

        assert result is False
        assert mock_sleep.call_count == 10
