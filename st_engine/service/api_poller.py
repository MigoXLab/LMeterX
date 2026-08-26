"""
API-based polling service for Engine.

Replaces the direct DB polling (service/poller.py) with HTTP REST calls
to the central Backend. This module is used when ENGINE_MODE=api.
"""

import asyncio
import os
import threading
import time
from typing import Optional

import httpx

from client.backend_client import backend_client
from client.oss_client import (
    cleanup_task_files,
    download_test_data,
    upload_system_log_to_oss,
    upload_task_logs_to_oss,
)
from config.base import LOCUST_STOP_TIMEOUT
from engine.process_manager import get_multiprocess_manager
from service.http_task_service import HttpTaskService
from service.llm_task_service import LlmTaskService
from utils.engine_identity import resolve_cluster_id, resolve_engine_id
from utils.logger import add_task_log_sink, logger, remove_task_log_sink

ENGINE_ID = resolve_engine_id()
CLUSTER_ID = resolve_cluster_id()
ENGINE_DEPLOYMENT = os.getenv("ENGINE_DEPLOYMENT", "")
ENGINE_POD_NAME = os.getenv("ENGINE_POD_NAME") or os.getenv("HOSTNAME", "")
TASK_POLL_INTERVAL = int(os.getenv("TASK_POLL_INTERVAL", "3"))
STOP_POLL_INTERVAL = int(os.getenv("STOP_POLL_INTERVAL", "5"))
LOG_PUSH_INTERVAL = int(os.getenv("LOG_PUSH_INTERVAL", "30"))
TASK_LOG_PUSH_INTERVAL = max(1, int(os.getenv("TASK_LOG_PUSH_INTERVAL", "10")))
HEARTBEAT_INTERVAL = int(os.getenv("ENGINE_HEARTBEAT_INTERVAL", "10"))
PROBE_EXECUTION_TIMEOUT = float(os.getenv("PROBE_EXECUTION_TIMEOUT", "30"))
PROBE_MAX_WORKERS = max(1, int(os.getenv("PROBE_MAX_WORKERS", "4")))
PROBE_MAX_STREAM_RESPONSE_CHARS = max(
    1, int(os.getenv("PROBE_MAX_STREAM_RESPONSE_CHARS", "1000000"))
)
STOPPING_TIMEOUT_SECONDS = LOCUST_STOP_TIMEOUT * 2
_regular_task_lock = threading.Lock()
_regular_task_thread: Optional[threading.Thread] = None
_probe_task_lock = threading.Lock()
_probe_task_threads: dict[str, threading.Thread] = {}


class TaskProxy:
    """
    Lightweight proxy that wraps a task config dict to behave like a SQLAlchemy
    Task ORM object. This allows reuse of existing LlmTaskService/HttpTaskService
    execution logic without modification.
    """

    def __init__(self, config: dict):
        self._config = config
        for key, value in config.items():
            setattr(self, key, value)
        self.is_deleted = 0

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._config.get(name)


def api_heartbeat_loop():
    """Background thread: sends heartbeat to Backend at regular intervals."""
    logger.info(
        f"[API] Heartbeat loop started. engine_id={ENGINE_ID}, cluster_id={CLUSTER_ID}"
    )

    while True:
        try:
            pm = get_multiprocess_manager()
            running_tasks = list(pm.get_all_process_groups().keys())
            available_slots = 0 if running_tasks or _regular_task_is_running() else 1

            cpu_usage = _get_cpu_usage()
            memory_usage = _get_memory_usage()

            result = backend_client.heartbeat(
                engine_id=ENGINE_ID,
                cluster_id=CLUSTER_ID,
                running_tasks=running_tasks,
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                available_slots=available_slots,
                deployment_name=ENGINE_DEPLOYMENT,
                pod_name=ENGINE_POD_NAME,
            )

            if result:
                status = result.get("status")
                if status == "not_registered":
                    logger.warning("[API] Engine not registered, re-registering...")
                    _register_engine()
                elif status == "rejected":
                    logger.error(
                        f"[API] Heartbeat rejected: {result.get('reason')}. "
                        f"deployment_name={ENGINE_DEPLOYMENT!r}. "
                        "Check ALLOWED_DEPLOYMENTS on backend."
                    )

        except Exception as e:
            logger.warning(f"[API] Heartbeat error: {e}")

        time.sleep(HEARTBEAT_INTERVAL)


def api_task_poller():
    """
    Background thread: polls Backend for tasks to execute.
    Handles probe, LLM, and HTTP tasks in a unified loop.
    Probes bypass regular-task slot limits and use their own bounded workers.
    """
    logger.info(
        f"[API] Task poller started. engine_id={ENGINE_ID}, cluster_id={CLUSTER_ID}"
    )

    llm_service = LlmTaskService()
    http_service = HttpTaskService()

    while True:
        try:
            pm = get_multiprocess_manager()
            running_tasks = list(pm.get_all_process_groups().keys())

            # Probe workers are independent from regular-task capacity. Do not
            # claim more probes than can be started immediately, otherwise their
            # Backend result deadline would elapse while queued in this process.
            if _probe_capacity_available():
                task_data = backend_client.claim_task(
                    engine_id=ENGINE_ID,
                    cluster_id=CLUSTER_ID,
                    task_types=["probe"],
                )
                if task_data and task_data.get("type") == "probe":
                    if not _start_probe_thread(task_data):
                        # Capacity is checked before claiming and this branch is
                        # only a defensive race fallback. Never orphan a probe
                        # that Backend has already marked as claimed.
                        _execute_probe(task_data)
                    continue

            # Skip regular task claim if slots are full. Probe claims above must
            # keep working while a long-running load test occupies the engine.
            if running_tasks or _regular_task_is_running():
                time.sleep(TASK_POLL_INTERVAL)
                continue

            task_data = backend_client.claim_task(
                engine_id=ENGINE_ID,
                cluster_id=CLUSTER_ID,
                task_types=["llm", "http"],
            )

            if task_data:
                _start_regular_task_thread(task_data, llm_service, http_service)

        except Exception as e:
            logger.exception(f"[API] Task poller error: {e}")
            time.sleep(10)
            continue

        time.sleep(TASK_POLL_INTERVAL)


def _regular_task_is_running() -> bool:
    with _regular_task_lock:
        return _regular_task_thread is not None and _regular_task_thread.is_alive()


def _prune_probe_threads_locked() -> None:
    finished_ids = [
        probe_id
        for probe_id, thread in _probe_task_threads.items()
        if not thread.is_alive()
    ]
    for probe_id in finished_ids:
        _probe_task_threads.pop(probe_id, None)


def _probe_capacity_available() -> bool:
    with _probe_task_lock:
        _prune_probe_threads_locked()
        return len(_probe_task_threads) < PROBE_MAX_WORKERS


def _start_probe_thread(task_data: dict) -> bool:
    """Start a claimed probe without blocking the task polling loop."""
    probe_id = task_data["id"]

    with _probe_task_lock:
        _prune_probe_threads_locked()
        if len(_probe_task_threads) >= PROBE_MAX_WORKERS:
            logger.error(
                f"[API] No probe worker available for already claimed probe {probe_id}"
            )
            return False

        thread = threading.Thread(
            target=_run_probe_thread,
            args=(task_data,),
            daemon=True,
            name=f"ProbeThread-{probe_id}",
        )
        _probe_task_threads[probe_id] = thread
        try:
            thread.start()
        except Exception:
            _probe_task_threads.pop(probe_id, None)
            raise

    return True


def _run_probe_thread(task_data: dict) -> None:
    probe_id = task_data["id"]
    try:
        _execute_probe(task_data)
    finally:
        with _probe_task_lock:
            _probe_task_threads.pop(probe_id, None)


def _start_regular_task_thread(
    task_data: dict,
    llm_service: LlmTaskService,
    http_service: HttpTaskService,
) -> bool:
    global _regular_task_thread

    task_id = task_data["id"]
    task_type = task_data["type"]

    with _regular_task_lock:
        if _regular_task_thread is not None and _regular_task_thread.is_alive():
            logger.warning(
                f"[API] Already running a regular task; "
                f"cannot start {task_type} task {task_id}"
            )
            return False

        thread = threading.Thread(
            target=_run_regular_task_pipeline,
            args=(task_data, llm_service, http_service),
            daemon=True,
            name=f"RegularTaskThread-{task_id}",
        )
        _regular_task_thread = thread
        thread.start()

    return True


def _run_regular_task_pipeline(
    task_data: dict,
    llm_service: LlmTaskService,
    http_service: HttpTaskService,
):
    global _regular_task_thread

    task_id = task_data["id"]
    task_type = task_data["type"]
    config = task_data["config"]
    test_data_url = task_data.get("test_data_url")

    logger.info(f"[API] Claimed {task_type} task: {task_id}")

    try:
        local_test_data = download_test_data(task_id, test_data_url)
        if local_test_data and config.get("test_data", "").startswith("/"):
            config["test_data"] = local_test_data

        task_proxy = TaskProxy(config)

        if task_type == "llm":
            _execute_llm_task(llm_service, task_proxy, task_id)
        else:
            _execute_http_task(http_service, task_proxy, task_id)
    finally:
        cleanup_task_files(task_id)
        with _regular_task_lock:
            if _regular_task_thread is threading.current_thread():
                _regular_task_thread = None


def api_stop_poller():
    """Background thread: checks for tasks that need to be stopped."""
    logger.info("[API] Stop poller started.")

    llm_service = LlmTaskService()
    http_service = HttpTaskService()

    while True:
        try:
            task_ids = backend_client.get_stopping_tasks(
                engine_id=ENGINE_ID, cluster_id=CLUSTER_ID
            )

            for task_id in task_ids:
                logger.info(f"[API] Stopping task: {task_id}")
                time.sleep(1)

                stopped = llm_service.stop_task(task_id) or http_service.stop_task(
                    task_id
                )
                if stopped:
                    backend_client.update_task_status(
                        task_id=task_id,
                        engine_id=ENGINE_ID,
                        status="stopped",
                    )
                    logger.info(f"[API] Task {task_id} stopped successfully.")
                else:
                    logger.warning(f"[API] Could not stop task {task_id}, will retry.")

        except Exception as e:
            logger.warning(f"[API] Stop poller error: {e}")

        time.sleep(STOP_POLL_INTERVAL)


def api_log_push_loop():
    """Periodically push engine.log tail to OSS for fallback/download views."""
    from client.oss_client import (
        OSS_ENABLED,
        is_oss_live_log_sync_enabled,
        is_oss_system_log_snapshot_enabled,
    )

    if not OSS_ENABLED:
        logger.info("[API] Log push loop skipped (OSS not enabled).")
        return

    if not is_oss_system_log_snapshot_enabled():
        logger.info("[API] Log push loop skipped (OSS log snapshots disabled).")
        return

    live_log_sync_enabled = is_oss_live_log_sync_enabled()
    if not live_log_sync_enabled:
        logger.info(
            "[API] SLS handles realtime logs; OSS system snapshots remain enabled "
            "for fallback/download views."
        )

    logger.info(
        f"[API] Log push loop started. interval={LOG_PUSH_INTERVAL}s, "
        f"engine_id={ENGINE_ID}, cluster_id={CLUSTER_ID}, "
        f"live_sync={live_log_sync_enabled}"
    )

    while True:
        try:
            upload_system_log_to_oss(ENGINE_ID, CLUSTER_ID)
        except Exception as e:
            logger.debug(f"[API] Log push error: {e}")

        time.sleep(LOG_PUSH_INTERVAL)


def _start_task_log_upload_loop(task_id: str):
    """Periodically upload live task logs only when OSS is the realtime fallback."""
    from client.oss_client import OSS_ENABLED, is_oss_live_log_sync_enabled

    if not OSS_ENABLED:
        return None
    if not is_oss_live_log_sync_enabled():
        logger.info(
            f"[API] Task log live upload skipped for task {task_id} "
            "(SLS handles realtime logs)."
        )
        return None

    stop_event = threading.Event()

    def upload_loop():
        logger.info(
            f"[API] Task log upload loop started for task {task_id}. "
            f"interval={TASK_LOG_PUSH_INTERVAL}s"
        )
        while not stop_event.is_set():
            try:
                upload_task_logs_to_oss(task_id, include_archives=False)
            except Exception as e:
                logger.debug(f"[API] Task log upload error for task {task_id}: {e}")

            if stop_event.wait(TASK_LOG_PUSH_INTERVAL):
                break

    thread = threading.Thread(
        target=upload_loop,
        daemon=True,
        name=f"TaskLogUploadThread-{task_id}",
    )
    thread.start()
    return stop_event, thread


def _stop_task_log_upload_loop(upload_loop):
    if upload_loop is None:
        return

    stop_event, thread = upload_loop
    stop_event.set()
    thread.join(timeout=2)


def _execute_llm_task(service: LlmTaskService, task_proxy: TaskProxy, task_id: str):
    """Execute an LLM task and report results back to Backend."""
    handler_id = None
    log_upload_loop = None
    try:
        handler_id = add_task_log_sink(task_id)
        log_upload_loop = _start_task_log_upload_loop(task_id)
        run_result = service.start_task(task_proxy)
        run_status = run_result.get("status")
        locust_result = run_result.get("locust_result", {})

        if run_status == "COMPLETED":
            backend_client.submit_results(
                task_id=task_id,
                engine_id=ENGINE_ID,
                locust_results=locust_result,
                final_status="completed",
            )
        elif run_status == "FAILED_REQUESTS":
            backend_client.submit_results(
                task_id=task_id,
                engine_id=ENGINE_ID,
                locust_results=locust_result,
                final_status="failed_requests",
                error_message=run_result.get("error_message", ""),
            )
        elif run_status == "STOPPED":
            backend_client.update_task_status(
                task_id=task_id,
                engine_id=ENGINE_ID,
                status="stopped",
            )
        else:
            error_msg = (
                f"Task execution failed (exit code: {run_result.get('return_code')})"
            )
            backend_client.submit_results(
                task_id=task_id,
                engine_id=ENGINE_ID,
                locust_results=locust_result if locust_result else None,
                final_status="failed",
                error_message=error_msg,
            )
    except Exception as e:
        logger.exception(f"[API] LLM task {task_id} pipeline failed: {e}")
        backend_client.submit_results(
            task_id=task_id,
            engine_id=ENGINE_ID,
            final_status="failed",
            error_message=f"Pipeline error: {str(e)[:500]}",
        )
    finally:
        _stop_task_log_upload_loop(log_upload_loop)
        if handler_id is not None:
            remove_task_log_sink(handler_id)
        upload_task_logs_to_oss(task_id, include_archives=True)


def _execute_http_task(service: HttpTaskService, task_proxy: TaskProxy, task_id: str):
    """Execute an HTTP task and report results back to Backend."""
    handler_id = None
    log_upload_loop = None
    try:
        handler_id = add_task_log_sink(task_id)
        log_upload_loop = _start_task_log_upload_loop(task_id)
        run_result = service.start_task(task_proxy)
        run_status = run_result.get("status")
        locust_result = run_result.get("locust_result", {})

        if run_status == "COMPLETED":
            backend_client.submit_results(
                task_id=task_id,
                engine_id=ENGINE_ID,
                locust_results=locust_result,
                final_status="completed",
            )
        elif run_status == "FAILED_REQUESTS":
            backend_client.submit_results(
                task_id=task_id,
                engine_id=ENGINE_ID,
                locust_results=locust_result,
                final_status="failed_requests",
                error_message=run_result.get("error_message", ""),
            )
        elif run_status == "STOPPED":
            backend_client.update_task_status(
                task_id=task_id,
                engine_id=ENGINE_ID,
                status="stopped",
            )
        else:
            error_msg = (
                f"Task execution failed (exit code: {run_result.get('return_code')})"
            )
            backend_client.submit_results(
                task_id=task_id,
                engine_id=ENGINE_ID,
                locust_results=locust_result if locust_result else None,
                final_status="failed",
                error_message=error_msg,
            )
    except Exception as e:
        logger.exception(f"[API] HTTP task {task_id} pipeline failed: {e}")
        backend_client.submit_results(
            task_id=task_id,
            engine_id=ENGINE_ID,
            final_status="failed",
            error_message=f"Pipeline error: {str(e)[:500]}",
        )
    finally:
        _stop_task_log_upload_loop(log_upload_loop)
        if handler_id is not None:
            remove_task_log_sink(handler_id)
        upload_task_logs_to_oss(task_id, include_archives=True)


def _execute_probe(task_data: dict):
    """Execute a lightweight connectivity probe and submit result to Backend."""
    import ssl

    probe_id = task_data["id"]
    config = task_data["config"]
    probe_type = config["probe_type"]
    request_config = config["request_config"]
    execution_timeout = float(config.get("execution_timeout", PROBE_EXECUTION_TIMEOUT))

    logger.info(f"[API] Executing {probe_type} probe: {probe_id}")

    try:
        if probe_type == "llm":
            result = _probe_llm(request_config, execution_timeout)
        else:
            result = _probe_http(request_config, execution_timeout)
    except ssl.SSLError as e:
        msg = str(e)
        hint = ""
        if "PEM lib" in msg or "PEM routines" in msg:
            hint = (
                " Client certificate/private key format error: only PEM is supported."
            )
        elif "no certificate or crl found" in msg:
            hint = " No valid certificate content found."
        result = {
            "status": "error",
            "error": f"SSL error: {msg}.{hint}",
            "response": None,
        }
    except (TimeoutError, httpx.TimeoutException):
        result = {
            "status": "error",
            "error": f"Request exceeded the {execution_timeout:g} second timeout.",
            "response": None,
        }
    except httpx.ConnectError as e:
        result = {
            "status": "error",
            "error": f"Connection error: {str(e)}",
            "response": None,
        }
    except Exception as e:
        result = {
            "status": "error",
            "error": f"Probe execution error: {str(e)[:500]}",
            "response": None,
        }

    submitted = backend_client.submit_probe_result(
        probe_id=probe_id, engine_id=ENGINE_ID, result=result
    )
    if submitted:
        logger.info(
            f"[API] Probe {probe_id} completed and submitted: "
            f"{result.get('status')}"
        )
    else:
        logger.error(
            f"[API] Probe {probe_id} completed locally but result submission failed: "
            f"{result.get('status')}"
        )


def _probe_llm(config: dict, execution_timeout: float) -> dict:
    """Execute LLM connectivity probe. Returns same format as backend test_llm_api_svc."""
    return asyncio.run(
        asyncio.wait_for(
            _probe_llm_async(config, execution_timeout),
            timeout=execution_timeout,
        )
    )


async def _probe_llm_async(config: dict, execution_timeout: float) -> dict:
    import json as json_mod

    target_host = config["target_host"].rstrip("/")
    api_path = config.get("api_path", "/chat/completions")
    full_url = f"{target_host}{api_path}"

    headers = {h["key"]: h["value"] for h in config.get("headers", []) if h.get("key")}
    cookies = {c["key"]: c["value"] for c in config.get("cookies", []) if c.get("key")}

    # Build payload
    payload_str = config.get("request_payload", "")
    if payload_str:
        try:
            payload = json_mod.loads(payload_str)
        except (json_mod.JSONDecodeError, TypeError):
            payload = {
                "model": config.get("model", ""),
                "messages": [{"role": "user", "content": "hi"}],
            }
    else:
        payload = {
            "model": config.get("model", ""),
            "messages": [{"role": "user", "content": "hi"}],
        }

    stream_mode = config.get("stream_mode", True)
    if stream_mode:
        payload["stream"] = True

    timeout = httpx.Timeout(execution_timeout, connect=min(10.0, execution_timeout))

    stream_data = []
    stream_status_code = None
    stream_headers = {}
    stream_truncated = False

    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=False
        ) as client:  # nosec B501
            if stream_mode:
                async with client.stream(
                    "POST", full_url, json=payload, headers=headers, cookies=cookies
                ) as response:
                    stream_status_code = response.status_code
                    stream_headers = dict(response.headers)
                    collected_chars = 0

                    # Preserve every fragment received during the execution
                    # window. A character limit prevents an unbounded endpoint
                    # from exhausting engine/DB memory.
                    async for chunk in response.aiter_text():
                        if not chunk:
                            continue

                        remaining = PROBE_MAX_STREAM_RESPONSE_CHARS - collected_chars
                        if remaining <= 0:
                            stream_truncated = True
                            break

                        stream_data.append(chunk[:remaining])
                        collected_chars += min(len(chunk), remaining)
                        if len(chunk) > remaining:
                            stream_truncated = True
                            break

                    return _build_stream_probe_result(
                        status_code=stream_status_code,
                        headers=stream_headers,
                        stream_data=stream_data,
                        execution_timeout=execution_timeout,
                        truncated=stream_truncated,
                    )

            response = await client.post(
                full_url, json=payload, headers=headers, cookies=cookies
            )
            try:
                data = response.json()
            except Exception:
                data = response.text[:2000]
            return {
                "status": "success" if response.status_code == 200 else "error",
                "response": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "data": data,
                    "is_stream": False,
                },
                "error": (
                    None
                    if response.status_code == 200
                    else f"HTTP {response.status_code}. {response.text[:500]}"
                ),
            }
    except asyncio.CancelledError:
        # asyncio.wait_for cancels this coroutine at the hard deadline. If the
        # stream already produced data, return everything collected so far
        # instead of discarding a valid partial response as a timeout error.
        if stream_mode and stream_status_code is not None and stream_data:
            return _build_stream_probe_result(
                status_code=stream_status_code,
                headers=stream_headers,
                stream_data=stream_data,
                execution_timeout=execution_timeout,
                timed_out=True,
            )
        raise


def _build_stream_probe_result(
    status_code: int,
    headers: dict,
    stream_data: list[str],
    execution_timeout: float,
    timed_out: bool = False,
    truncated: bool = False,
) -> dict:
    test_successful = status_code == 200 and len(stream_data) > 0
    if timed_out:
        test_note = (
            f"Streaming response collection reached the {execution_timeout:g} "
            "second limit; showing all data received before the timeout"
        )
    elif truncated:
        test_note = (
            "Streaming response reached the configured preview size limit; "
            "showing the collected prefix"
        )
    else:
        test_note = "Streaming response completed within the API test time limit"

    return {
        "status": "success" if test_successful else "error",
        "response": {
            "status_code": status_code,
            "headers": headers,
            "data": stream_data,
            "is_stream": True,
            "test_note": test_note,
        },
        "error": (
            None
            if test_successful
            else f"HTTP {status_code}. {' '.join(stream_data)[:500] if stream_data else 'No streaming data received'}"
        ),
    }


def _probe_http(config: dict, execution_timeout: float) -> dict:
    """Execute HTTP connectivity probe. Returns same format as backend test_http_api_svc."""
    return asyncio.run(
        asyncio.wait_for(
            _probe_http_async(config, execution_timeout),
            timeout=execution_timeout,
        )
    )


async def _probe_http_async(config: dict, execution_timeout: float) -> dict:
    import json as json_mod

    method = config.get("method", "GET").upper()
    target_url = config["target_url"]
    headers = {h["key"]: h["value"] for h in config.get("headers", []) if h.get("key")}
    cookies = {c["key"]: c["value"] for c in config.get("cookies", []) if c.get("key")}
    request_body = config.get("request_body")

    no_body_methods = {"GET", "HEAD", "OPTIONS"}
    json_payload = None
    text_payload = None

    if method not in no_body_methods and request_body:
        try:
            json_payload = json_mod.loads(request_body)
        except (json_mod.JSONDecodeError, TypeError):
            text_payload = request_body

    timeout = httpx.Timeout(execution_timeout, connect=min(10.0, execution_timeout))

    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:  # nosec B501
        response = await client.request(
            method,
            target_url,
            headers=headers,
            cookies=cookies,
            json=json_payload,
            content=text_payload,
        )
        return {
            "status": "success",
            "http_status": response.status_code,
            "headers": dict(response.headers),
            "body": response.text[:10000],
        }


def _register_engine():
    """Register this engine with the Backend. Returns the result dict or None."""
    import psutil

    capabilities = {
        "cpu_cores": float(os.getenv("LOCUST_CPU_CORES", str(psutil.cpu_count() or 2))),
        "memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "max_concurrent_tasks": 1,
    }

    result = backend_client.register(
        engine_id=ENGINE_ID,
        cluster_id=CLUSTER_ID,
        capabilities=capabilities,
        version=os.getenv("ENGINE_VERSION", "1.0.0"),
        deployment_name=ENGINE_DEPLOYMENT,
        pod_name=ENGINE_POD_NAME,
    )

    if result:
        if result.get("status") == "rejected":
            logger.error(
                f"[API] Engine registration rejected: {result.get('reason')}. "
                f"deployment_name={ENGINE_DEPLOYMENT!r}"
            )
        else:
            logger.info(f"[API] Engine registered successfully: {result}")
    else:
        logger.error("[API] Engine registration failed")

    return result


def _get_cpu_usage() -> float:
    try:
        import psutil

        return psutil.cpu_percent(interval=None)
    except Exception:
        return 0.0


def _get_memory_usage() -> float:
    try:
        import psutil

        return psutil.virtual_memory().percent
    except Exception:
        return 0.0


def startup_register():
    """Called once at Engine startup to register with Backend."""
    max_retries = 10
    for attempt in range(max_retries):
        reg_result = _register_engine()
        if reg_result and reg_result.get("status") == "rejected":
            logger.error(
                f"[API] Engine registration rejected: {reg_result.get('reason')}. "
                f"deployment_name={ENGINE_DEPLOYMENT!r}. Giving up."
            )
            return False

        result = backend_client.heartbeat(
            engine_id=ENGINE_ID,
            cluster_id=CLUSTER_ID,
            running_tasks=[],
            cpu_usage=0.0,
            memory_usage=0.0,
            available_slots=1,
            deployment_name=ENGINE_DEPLOYMENT,
            pod_name=ENGINE_POD_NAME,
        )
        if result:
            status = result.get("status")
            if status == "rejected":
                logger.error(
                    f"[API] Startup heartbeat rejected: {result.get('reason')}. Giving up."
                )
                return False
            if status != "not_registered":
                logger.info("[API] Engine startup registration successful.")
                return True

        logger.warning(
            f"[API] Registration attempt {attempt+1}/{max_retries} failed, retrying..."
        )
        time.sleep(5)

    logger.error("[API] Engine failed to register after all retries.")
    return False


def shutdown_unregister():
    """Called on Engine shutdown to immediately unregister and free slots."""
    logger.info(f"[API] Graceful shutdown: unregistering engine_id={ENGINE_ID}")
    result = backend_client.unregister(engine_id=ENGINE_ID, cluster_id=CLUSTER_ID)
    if result and result.get("status") == "ok":
        logger.info("[API] Engine unregistered successfully.")
    else:
        logger.warning(f"[API] Failed to unregister engine during shutdown: {result}")
    backend_client.close()
