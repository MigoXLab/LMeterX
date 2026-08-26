"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

Engine management service: handles registration, heartbeat, task dispatch,
status reporting, and dead-engine reconciliation.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from model.cluster import Cluster
from model.engine import EngineHeartbeat
from utils.logger import logger

HEARTBEAT_STALE_SECONDS = 60
ALLOWED_DEPLOYMENTS_RAW = os.getenv("ALLOWED_DEPLOYMENTS", "")
ALLOWED_DEPLOYMENTS = (
    [d.strip() for d in ALLOWED_DEPLOYMENTS_RAW.split(",") if d.strip()]
    if ALLOWED_DEPLOYMENTS_RAW
    else []
)


async def register_engine(
    db: AsyncSession,
    engine_id: str,
    cluster_id: str,
    capabilities: dict,
    version: Optional[str] = None,
    deployment_name: Optional[str] = None,
    pod_name: Optional[str] = None,
) -> dict:
    if ALLOWED_DEPLOYMENTS and deployment_name not in ALLOWED_DEPLOYMENTS:
        logger.warning(
            f"Rejected engine registration: engine_id={engine_id}, "
            f"deployment_name={deployment_name!r} not in ALLOWED_DEPLOYMENTS={ALLOWED_DEPLOYMENTS}"
        )
        return {"status": "rejected", "reason": "deployment not allowed"}

    existing = await db.get(EngineHeartbeat, engine_id)
    if existing:
        existing.cluster_id = cluster_id
        existing.status = "online"
        existing.last_heartbeat = datetime.utcnow()
        existing.available_slots = capabilities.get("max_concurrent_tasks", 1)
        existing.version = version
        existing.deployment_name = deployment_name
        existing.pod_name = pod_name
    else:
        heartbeat = EngineHeartbeat(
            engine_id=engine_id,
            cluster_id=cluster_id,
            status="online",
            last_heartbeat=datetime.utcnow(),
            available_slots=capabilities.get("max_concurrent_tasks", 1),
            version=version,
            registered_at=datetime.utcnow(),
            deployment_name=deployment_name,
            pod_name=pod_name,
        )
        db.add(heartbeat)

    await db.flush()

    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        cluster = Cluster(id=cluster_id, name=cluster_id, status="active")
        db.add(cluster)
        await db.flush()

    return {
        "status": "registered",
        "heartbeat_interval": 10,
        "task_poll_interval": 3,
    }


async def process_heartbeat(
    db: AsyncSession,
    engine_id: str,
    cluster_id: str,
    running_tasks: List[str],
    cpu_usage: float,
    memory_usage: float,
    available_slots: int,
    deployment_name: Optional[str] = None,
    pod_name: Optional[str] = None,
) -> dict:
    heartbeat = await db.get(EngineHeartbeat, engine_id)
    if not heartbeat:
        return {"status": "not_registered"}

    if ALLOWED_DEPLOYMENTS and deployment_name not in ALLOWED_DEPLOYMENTS:
        logger.warning(
            f"Rejected heartbeat: engine_id={engine_id}, "
            f"deployment_name={deployment_name!r} not in ALLOWED_DEPLOYMENTS"
        )
        return {"status": "rejected", "reason": "deployment not allowed"}

    heartbeat.last_heartbeat = datetime.utcnow()
    heartbeat.cluster_id = cluster_id
    heartbeat.status = "busy" if available_slots == 0 else "online"
    heartbeat.running_tasks = json.dumps(running_tasks) if running_tasks else None
    heartbeat.cpu_usage = cpu_usage
    heartbeat.memory_usage = memory_usage
    heartbeat.available_slots = available_slots
    if deployment_name:
        heartbeat.deployment_name = deployment_name
    if pod_name:
        heartbeat.pod_name = pod_name
    await db.flush()

    return {"status": "ok", "commands": []}


async def claim_task(
    db: AsyncSession,
    engine_id: str,
    cluster_id: str,
    task_types: List[str],
) -> Optional[dict]:
    from model.http_task import HttpTask
    from model.llm_task import Task as LlmTask
    from model.probe_task import ProbeTask
    from model.task_dispatch_queue import TaskDispatchQueue

    supported_task_types = {"probe", "llm", "http"}
    normalized_task_types = [
        task_type.strip().lower()
        for task_type in task_types
        if isinstance(task_type, str) and task_type.strip()
    ]
    unknown_task_types = [
        task_type
        for task_type in normalized_task_types
        if task_type not in supported_task_types
    ]
    if unknown_task_types:
        logger.warning(
            "Engine {} requested unsupported task_types: {}",
            engine_id,
            unknown_task_types,
        )

    task_types = [
        task_type
        for task_type in normalized_task_types
        if task_type in supported_task_types
    ]
    if not task_types:
        return None

    # Priority: claim probe tasks first (time-sensitive, lightweight)
    if "probe" in task_types:
        from service.probe_service import PROBE_EXECUTION_TIMEOUT

        result = await db.execute(
            select(ProbeTask)
            .where(
                and_(
                    ProbeTask.status == "pending",
                    ProbeTask.cluster_id == cluster_id,
                )
            )
            .order_by(ProbeTask.created_at.asc())
            .with_for_update()
            .limit(1)
        )
        probe = result.scalar_one_or_none()
        if probe:
            probe.status = "claimed"
            probe.engine_id = engine_id
            await db.flush()
            return {
                "id": probe.id,
                "type": "probe",
                "config": {
                    "probe_type": probe.probe_type,
                    "request_config": probe.request_config,
                    "execution_timeout": PROBE_EXECUTION_TIMEOUT,
                },
                "test_data_url": None,
                "cert_url": None,
            }

    # Then claim regular tasks from one shared sequence. The caller's task type
    # order is a capability filter only and must never become a priority.
    regular_task_types = list(
        dict.fromkeys(task_type for task_type in task_types if task_type != "probe")
    )
    if not regular_task_types:
        return None

    while True:
        result = await db.execute(
            select(TaskDispatchQueue)
            .where(
                and_(
                    TaskDispatchQueue.status == "queued",
                    TaskDispatchQueue.cluster_id == cluster_id,
                    TaskDispatchQueue.task_type.in_(regular_task_types),
                )
            )
            .order_by(TaskDispatchQueue.queue_seq.asc())
            .with_for_update()
            .limit(1)
        )
        dispatch_entry = result.scalar_one_or_none()
        if not dispatch_entry:
            return None

        task_type = dispatch_entry.task_type
        TaskModel = LlmTask if task_type == "llm" else HttpTask
        task = await db.get(TaskModel, dispatch_entry.task_id)

        # A cancellation/deletion may race with dispatch, or an inconsistent
        # row may remain after an interrupted deployment. Skip it atomically so
        # it cannot block all later tasks in the cluster.
        if (
            not task
            or task.status != "queuing"
            or task.is_deleted != 0
            or task.cluster_id != cluster_id
        ):
            dispatch_entry.status = "cancelled"
            await db.flush()
            continue

        dispatch_entry.status = "claimed"
        dispatch_entry.engine_id = engine_id
        dispatch_entry.claimed_at = datetime.utcnow()
        task.status = "running"
        task.engine_id = engine_id
        await db.flush()

        return _serialize_task(task, task_type)


async def update_task_status(
    db: AsyncSession,
    task_id: str,
    engine_id: str,
    status: str,
    progress: Optional[int] = None,
    message: Optional[str] = None,
) -> bool:
    from model.http_task import HttpTask
    from model.llm_task import Task as LlmTask

    for TaskModel in [LlmTask, HttpTask]:
        task = await db.get(TaskModel, task_id)
        if task:
            if task.engine_id != engine_id:
                logger.warning(
                    f"Engine {engine_id} tried to update task {task_id} "
                    f"owned by {task.engine_id}"
                )
                return False
            task.status = status
            if message:
                task.error_message = message[:65000]
            await db.flush()
            return True

    return False


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_result_fields(
    task_id: str, stat: Dict[str, Any], include_token_fields: bool
) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "task_id": task_id,
        "metric_type": str(stat.get("metric_type") or "locust_stats"),
        "num_requests": _safe_int(stat.get("num_requests")),
        "num_failures": _safe_int(stat.get("num_failures")),
        "avg_latency": _safe_number(stat.get("avg_latency")),
        "min_latency": _safe_number(stat.get("min_latency")),
        "max_latency": _safe_number(stat.get("max_latency")),
        "median_latency": _safe_number(stat.get("median_latency")),
        "p95_latency": _safe_number(stat.get("p95_latency")),
        "rps": _safe_number(stat.get("rps")),
        "avg_content_length": _safe_number(stat.get("avg_content_length")),
    }

    if include_token_fields:
        fields.update(
            {
                "total_tps": _safe_number(stat.get("total_tps")),
                "completion_tps": _safe_number(stat.get("completion_tps")),
                "avg_total_tokens_per_req": _safe_number(
                    stat.get("avg_total_tokens_per_req")
                ),
                "avg_completion_tokens_per_req": _safe_number(
                    stat.get("avg_completion_tokens_per_req")
                ),
            }
        )

    return fields


def _normalize_result_records(
    task_id: str, locust_results: Dict[str, Any], include_token_fields: bool
) -> List[Dict[str, Any]]:
    """Normalize engine-submitted results into DB row dictionaries.

    API-mode engines submit the same structure produced by locustfiles:
    {"locust_stats": [...], "custom_metrics": {...}}.  Older callers may still
    submit a single flat metric row, so both formats are accepted.
    """
    if not locust_results:
        return []

    records: List[Dict[str, Any]] = []

    locust_stats = locust_results.get("locust_stats")
    if isinstance(locust_stats, list):
        for stat in locust_stats:
            if isinstance(stat, dict):
                records.append(
                    _build_result_fields(task_id, stat, include_token_fields)
                )
    elif any(
        key in locust_results
        for key in (
            "num_requests",
            "num_failures",
            "avg_latency",
            "metric_type",
            "rps",
        )
    ):
        records.append(
            _build_result_fields(task_id, locust_results, include_token_fields)
        )

    custom_metrics = locust_results.get("custom_metrics")
    if include_token_fields and isinstance(custom_metrics, dict) and custom_metrics:
        records.append(
            _build_result_fields(
                task_id,
                {
                    "metric_type": "token_metrics",
                    "num_requests": custom_metrics.get("reqs_num", 0),
                    "num_failures": 0,
                    "avg_latency": 0.0,
                    "min_latency": 0.0,
                    "max_latency": 0.0,
                    "median_latency": 0.0,
                    "p95_latency": 0.0,
                    "rps": custom_metrics.get("req_throughput", 0.0),
                    "avg_content_length": 0.0,
                    "total_tps": custom_metrics.get("total_tps", 0.0),
                    "completion_tps": custom_metrics.get("completion_tps", 0.0),
                    "avg_total_tokens_per_req": custom_metrics.get(
                        "avg_total_tokens_per_req", 0.0
                    ),
                    "avg_completion_tokens_per_req": custom_metrics.get(
                        "avg_completion_tokens_per_req", 0.0
                    ),
                },
                include_token_fields,
            )
        )

    return records


async def submit_task_results(
    db: AsyncSession,
    task_id: str,
    engine_id: str,
    locust_results: dict,
    final_status: str,
    error_message: Optional[str] = None,
) -> bool:
    from model.http_task import HttpTask, HttpTaskResult
    from model.llm_task import Task as LlmTask
    from model.llm_task import TaskResult as LlmTaskResult

    for TaskModel, ResultModel in [
        (LlmTask, LlmTaskResult),
        (HttpTask, HttpTaskResult),
    ]:
        task = await db.get(TaskModel, task_id)
        if task:
            if task.engine_id != engine_id:
                logger.warning(
                    f"Engine {engine_id} tried to submit results for task {task_id} "
                    f"owned by {task.engine_id}"
                )
                return False

            task.status = final_status
            if error_message:
                task.error_message = error_message[:65000]

            result_records = _normalize_result_records(
                task_id,
                locust_results,
                include_token_fields=ResultModel is LlmTaskResult,
            )
            for result_fields in result_records:
                db.add(ResultModel(**result_fields))

            await db.flush()
            return True

    return False


async def get_stopping_tasks(
    db: AsyncSession, engine_id: str, cluster_id: str
) -> List[str]:
    from model.http_task import HttpTask
    from model.llm_task import Task as LlmTask

    task_ids = []
    for TaskModel in [LlmTask, HttpTask]:
        result = await db.execute(
            select(TaskModel.id).where(
                and_(
                    TaskModel.status == "stopping",
                    TaskModel.engine_id == engine_id,
                    TaskModel.is_deleted == 0,
                )
            )
        )
        task_ids.extend([row[0] for row in result.all()])

    return task_ids


async def reconcile_dead_engines(db: AsyncSession) -> int:
    from model.http_task import HttpTask
    from model.llm_task import Task as LlmTask

    stale_cutoff = datetime.utcnow() - timedelta(seconds=HEARTBEAT_STALE_SECONDS)

    stale_result = await db.execute(
        select(EngineHeartbeat.engine_id).where(
            EngineHeartbeat.last_heartbeat < stale_cutoff
        )
    )
    stale_ids = [row[0] for row in stale_result.all()]

    if not stale_ids:
        return 0

    count = 0
    for TaskModel in [LlmTask, HttpTask]:
        result = await db.execute(
            update(TaskModel)
            .where(
                and_(
                    TaskModel.status.in_(["running", "stopping"]),
                    TaskModel.engine_id.in_(stale_ids),
                    TaskModel.is_deleted == 0,
                )
            )
            .values(
                status="failed",
                error_message="Engine instance is no longer alive (heartbeat timeout).",
            )
        )
        count += result.rowcount

    await db.execute(
        update(EngineHeartbeat)
        .where(EngineHeartbeat.engine_id.in_(stale_ids))
        .values(status="offline")
    )
    await db.flush()

    if count > 0:
        logger.info(f"Reconciled {count} orphaned tasks from dead engines: {stale_ids}")

    return count


async def unregister_engine(db: AsyncSession, engine_id: str, cluster_id: str) -> dict:
    """Mark an engine as offline immediately (graceful shutdown)."""
    heartbeat = await db.get(EngineHeartbeat, engine_id)
    if not heartbeat:
        return {"status": "not_found"}

    heartbeat.status = "offline"
    heartbeat.available_slots = 0
    heartbeat.running_tasks = None
    heartbeat.last_heartbeat = datetime(1970, 1, 1)
    await db.flush()

    logger.info(
        f"Engine {engine_id} unregistered (graceful shutdown), cluster={cluster_id}"
    )
    return {"status": "ok"}


async def cleanup_stale_engines(
    db: AsyncSession,
    valid_engine_ids: Optional[List[str]] = None,
    cluster_id: Optional[str] = None,
) -> int:
    """
    Mark engines as offline that are not in the valid_engine_ids list.
    If valid_engine_ids is None, cleans all stale engines (heartbeat expired).
    """
    if valid_engine_ids is not None:
        conditions = [EngineHeartbeat.engine_id.notin_(valid_engine_ids)]
        if cluster_id:
            conditions.append(EngineHeartbeat.cluster_id == cluster_id)

        result = await db.execute(
            update(EngineHeartbeat)
            .where(and_(*conditions, EngineHeartbeat.status != "offline"))
            .values(status="offline")
        )
        count = result.rowcount
    else:
        stale_cutoff = datetime.utcnow() - timedelta(seconds=HEARTBEAT_STALE_SECONDS)
        conditions = [EngineHeartbeat.last_heartbeat < stale_cutoff]
        if cluster_id:
            conditions.append(EngineHeartbeat.cluster_id == cluster_id)

        result = await db.execute(
            update(EngineHeartbeat)
            .where(and_(*conditions, EngineHeartbeat.status != "offline"))
            .values(status="offline")
        )
        count = result.rowcount

    await db.flush()

    if count > 0:
        logger.info(
            f"Cleanup: marked {count} engine(s) as offline (cluster={cluster_id})"
        )

    return count


def _serialize_task(task, task_type: str) -> dict:
    import os

    oss_enabled = os.getenv("OSS_ENABLED", "false").lower() == "true"

    data_file = None
    if task_type == "llm":
        data_file = getattr(task, "test_data", None)
    else:
        data_file = getattr(task, "dataset_file", None)

    test_data_url = None
    if data_file and isinstance(data_file, str) and data_file.startswith("/"):
        if oss_enabled:
            from service.oss_service import generate_presigned_url

            test_data_url = generate_presigned_url(data_file)
        else:
            test_data_url = data_file

    config = {
        "id": task.id,
        "name": task.name,
        "target_host": getattr(task, "target_host", "")
        or getattr(task, "target_url", ""),
        "api_path": getattr(task, "api_path", ""),
        "duration": task.duration,
        "concurrent_users": task.concurrent_users,
        "spawn_rate": task.spawn_rate,
        "headers": task.headers,
        "cookies": task.cookies,
        "load_mode": getattr(task, "load_mode", "fixed"),
        "step_start_users": getattr(task, "step_start_users", None),
        "step_increment": getattr(task, "step_increment", None),
        "step_duration": getattr(task, "step_duration", None),
        "step_max_users": getattr(task, "step_max_users", None),
        "step_sustain_duration": getattr(task, "step_sustain_duration", None),
    }

    if task_type == "llm":
        config.update(
            {
                "model": getattr(task, "model", ""),
                "stream_mode": getattr(task, "stream_mode", "True"),
                "request_payload": getattr(task, "request_payload", ""),
                "field_mapping": getattr(task, "field_mapping", ""),
                "api_type": getattr(task, "api_type", "openai-chat"),
                "cert_file": getattr(task, "cert_file", None),
                "key_file": getattr(task, "key_file", None),
                "warmup_enabled": getattr(task, "warmup_enabled", 1),
                "warmup_duration": getattr(task, "warmup_duration", 120),
                "chat_type": getattr(task, "chat_type", 0),
                "test_data": getattr(task, "test_data", ""),
            }
        )
    else:
        config.update(
            {
                "method": getattr(task, "method", "GET"),
                "target_url": getattr(task, "target_url", ""),
                "request_body": getattr(task, "request_body", ""),
                "dataset_file": getattr(task, "dataset_file", ""),
                "curl_command": getattr(task, "curl_command", ""),
                "success_assert": getattr(task, "success_assert", ""),
            }
        )

    return {
        "id": task.id,
        "type": task_type,
        "config": config,
        "test_data_url": test_data_url,
        "cert_url": None,
    }


async def reset_all_engines_heartbeat(db: AsyncSession):
    """
    Reset last_heartbeat of all engines to epoch (1970-01-01) on startup.
    This ensures that offline/dead engines from previous runs are immediately
    excluded from online engine count and slot calculations without waiting
    for the heartbeat stale timeout.
    """
    try:
        epoch = datetime(1970, 1, 1)
        await db.execute(update(EngineHeartbeat).values(last_heartbeat=epoch))
        await db.commit()
        logger.info(
            "Successfully reset all engine last_heartbeat timestamps to epoch on startup."
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to reset engine heartbeats on startup: {e}")
