"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from model.system import (
    AIServiceConfig,
    BatchSystemConfigRequest,
    BatchSystemConfigResponse,
    SystemConfig,
    SystemConfigListResponse,
    SystemConfigRequest,
    SystemConfigResponse,
)
from utils.error_handler import ErrorMessages, ErrorResponse
from utils.logger import logger
from utils.masking import mask_api_key, mask_config_value

AI_CONFIG_KEYS = ("ai_service_host", "ai_service_model", "ai_service_api_key")

# Optional AI config keys with their default values.
# These configs are not required and will use defaults if not set in database.
_AI_CONFIG_OPTIONAL_DEFAULTS = {
    "ai_service_ssl_verify": "true",
}


def _to_string(value: Optional[Any]) -> str:
    return str(value) if value is not None else ""


def _build_config_response(
    config: SystemConfig, *, mask_sensitive: bool = True
) -> SystemConfigResponse:
    config_key = _to_string(config.config_key)
    raw_value = _to_string(config.config_value)
    config_value = (
        mask_config_value(config_key, raw_value) if mask_sensitive else raw_value
    )

    return SystemConfigResponse(
        config_key=config_key,
        config_value=config_value,
        description=(
            _to_string(config.description) if config.description is not None else None
        ),
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else "",
    )


async def _fetch_all_configs(db: AsyncSession) -> List[SystemConfig]:
    config_query = select(SystemConfig)
    config_result = await db.execute(config_query)
    configs = config_result.scalars().all()
    return list(configs)


async def _fetch_configs_by_keys(
    db: AsyncSession, keys: Sequence[str]
) -> Dict[str, SystemConfig]:
    config_query = select(SystemConfig).where(SystemConfig.config_key.in_(keys))
    config_result = await db.execute(config_query)
    config_objects = config_result.scalars().all()
    return {_to_string(config.config_key): config for config in config_objects}


async def _resolve_ai_service_configs(db: AsyncSession) -> Dict[str, str]:
    all_keys = list(AI_CONFIG_KEYS) + list(_AI_CONFIG_OPTIONAL_DEFAULTS.keys())
    configs = await _fetch_configs_by_keys(db, all_keys)

    resolved: Dict[str, str] = {}
    missing_configs = []

    for key in AI_CONFIG_KEYS:
        config = configs.get(key)
        value = (
            _to_string(config.config_value) if config and config.config_value else ""
        )
        if not value:
            missing_configs.append(key)
        else:
            resolved[key] = value

    if missing_configs:
        raise ErrorResponse.bad_request(
            f"{ErrorMessages.MISSING_AI_CONFIG}: {', '.join(missing_configs)}"
        )

    # Resolve optional keys with defaults
    for key, default in _AI_CONFIG_OPTIONAL_DEFAULTS.items():
        config = configs.get(key)
        value = (
            _to_string(config.config_value)
            if config and config.config_value
            else default
        )
        resolved[key] = value

    return resolved


async def get_system_configs_svc(request: Request) -> SystemConfigListResponse:
    """
    Get all system configurations for System Configuration page (with masked API keys).

    Args:
        request: The incoming request.

    Returns:
        SystemConfigListResponse: The system configurations with masked sensitive values.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _fetch_all_configs(db)
        config_responses = [
            _build_config_response(config, mask_sensitive=True) for config in configs
        ]

        return SystemConfigListResponse(
            data=config_responses,
            status="success",
            error=None,
        )

    except Exception as e:
        logger.warning("Failed to get system configs: {}", e)
        return SystemConfigListResponse(
            data=[],
            status="success",
            error=ErrorMessages.DATABASE_ERROR,
        )


async def get_system_configs_internal_svc(request: Request) -> SystemConfigListResponse:
    """
    Get all system configurations for internal use (with real values, no masking).

    Args:
        request: The incoming request.

    Returns:
        SystemConfigListResponse: The system configurations with real values.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _fetch_all_configs(db)
        config_responses = [
            _build_config_response(config, mask_sensitive=False) for config in configs
        ]

        return SystemConfigListResponse(
            data=config_responses,
            status="success",
            error=None,
        )

    except Exception as e:
        logger.error("Failed to get system configs: {}", e)
        return SystemConfigListResponse(
            data=[],
            status="error",
            error=ErrorMessages.DATABASE_ERROR,
        )


async def create_system_config_svc(
    request: Request, config_request: SystemConfigRequest
) -> SystemConfigResponse:
    """
    Create a new system configuration.

    Args:
        request: The incoming request.
        config_request: The configuration request.

    Returns:
        SystemConfigResponse: The created configuration.

    Raises:
        ErrorResponse: If the configuration already exists or persistence fails.
    """
    db: AsyncSession = request.state.db

    try:
        # Check if config already exists
        existing_query = select(SystemConfig).where(
            SystemConfig.config_key == config_request.config_key
        )
        existing_result = await db.execute(existing_query)
        existing_config = existing_result.scalar_one_or_none()

        if existing_config:
            raise ErrorResponse.bad_request(ErrorMessages.CONFIG_ALREADY_EXISTS)

        # Create new config - store original payload without encryption
        config_id = str(uuid.uuid4())
        config = SystemConfig(
            id=config_id,
            config_key=config_request.config_key,
            config_value=config_request.config_value,  # Store original value
            description=config_request.description,
        )

        db.add(config)
        await db.commit()
        await db.refresh(config)

        return _build_config_response(config)

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to create system config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_CREATION_FAILED)


async def update_system_config_svc(
    request: Request, config_key: str, config_request: SystemConfigRequest
) -> SystemConfigResponse:
    """
    Update an existing system configuration.

    Args:
        request: The incoming request.
        config_key: The configuration key to update.
        config_request: The configuration request.

    Returns:
        SystemConfigResponse: The updated configuration.

    Raises:
        ErrorResponse: If the configuration doesn't exist or persistence fails.
    """
    db: AsyncSession = request.state.db

    try:
        # Find existing config
        config_query = select(SystemConfig).where(SystemConfig.config_key == config_key)
        config_result = await db.execute(config_query)
        config = config_result.scalar_one_or_none()

        if not config:
            raise ErrorResponse.not_found("Configuration not found")

        # Update config - store original payload without encryption
        setattr(
            config, "config_value", config_request.config_value
        )  # Store original value
        if config_request.description is not None:
            setattr(config, "description", config_request.description)

        await db.commit()
        await db.refresh(config)

        return _build_config_response(config)

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to update system config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_UPDATE_FAILED)


async def delete_system_config_svc(request: Request, config_key: str) -> Dict:
    """
    Delete a system configuration.

    Args:
        request: The incoming request.
        config_key: The configuration key to delete.

    Returns:
        Dict: Success response.

    Raises:
        ErrorResponse: If the configuration doesn't exist or deletion fails.
    """
    db: AsyncSession = request.state.db

    try:
        # Find existing config
        config_query = select(SystemConfig).where(SystemConfig.config_key == config_key)
        config_result = await db.execute(config_query)
        config = config_result.scalar_one_or_none()

        if not config:
            raise ErrorResponse.not_found(ErrorMessages.CONFIG_NOT_FOUND)

        # Delete config
        await db.delete(config)
        await db.commit()

        return {"status": "success", "message": "Configuration deleted successfully"}

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to delete system config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.TASK_DELETION_FAILED)


async def get_ai_service_config_svc(request: Request) -> AIServiceConfig:
    """
    Get AI service configuration for API responses (with masked API key).

    Args:
        request: The incoming request.

    Returns:
        AIServiceConfig: The AI service configuration with masked API key.

    Raises:
        ErrorResponse: If the configuration is incomplete or query fails.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _resolve_ai_service_configs(db)
        ssl_verify = configs.get("ai_service_ssl_verify", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        return AIServiceConfig(
            host=configs["ai_service_host"],
            model=configs["ai_service_model"],
            api_key=mask_api_key(configs["ai_service_api_key"]),
            ssl_verify=ssl_verify,
        )

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to get AI service config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.DATABASE_ERROR)


async def get_ai_service_config_internal_svc(request: Request) -> AIServiceConfig:
    """
    Get AI service configuration for internal use (with real API key).

    Args:
        request: The incoming request.

    Returns:
        AIServiceConfig: The AI service configuration with real API key.

    Raises:
        ErrorResponse: If the configuration is incomplete or query fails.
    """
    db: AsyncSession = request.state.db

    try:
        configs = await _resolve_ai_service_configs(db)
        ssl_verify = configs.get("ai_service_ssl_verify", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        return AIServiceConfig(
            host=configs["ai_service_host"],
            model=configs["ai_service_model"],
            api_key=configs["ai_service_api_key"],
            ssl_verify=ssl_verify,
        )

    except ErrorResponse:
        raise
    except Exception as e:
        logger.error("Failed to get AI service config: {}", e)
        raise ErrorResponse.internal_server_error(ErrorMessages.DATABASE_ERROR)


async def batch_upsert_system_configs_svc(
    request: Request, batch_request: BatchSystemConfigRequest
) -> BatchSystemConfigResponse:
    """
    Batch create or update system configurations in a single transaction.

    Args:
        request: The incoming request.
        batch_request: The batch configuration request.

    Returns:
        BatchSystemConfigResponse: The batch operation result.
    """
    db: AsyncSession = request.state.db

    try:
        config_responses = []

        # Start transaction
        async with db.begin():
            for config_request in batch_request.configs:
                # Check if config already exists
                existing_query = select(SystemConfig).where(
                    SystemConfig.config_key == config_request.config_key
                )
                existing_result = await db.execute(existing_query)
                existing_config = existing_result.scalar_one_or_none()

                if existing_config:
                    # Update existing config
                    setattr(
                        existing_config, "config_value", config_request.config_value
                    )
                    if config_request.description is not None:
                        setattr(
                            existing_config, "description", config_request.description
                        )

                    config = existing_config
                else:
                    # Create new config
                    config_id = str(uuid.uuid4())
                    config = SystemConfig(
                        id=config_id,
                        config_key=config_request.config_key,
                        config_value=config_request.config_value,
                        description=config_request.description,
                    )
                    db.add(config)

                # Refresh to get updated data
                await db.flush()
                await db.refresh(config)

                config_responses.append(_build_config_response(config))

        return BatchSystemConfigResponse(
            data=config_responses,
            status="success",
            error=None,
        )

    except Exception as e:
        logger.error("Failed to batch upsert system configs: {}", e)
        return BatchSystemConfigResponse(
            data=[],
            status="error",
            error=ErrorMessages.DATABASE_ERROR,
        )


def _get_username(request: Request, auth_settings) -> str:
    from utils.auth import get_current_user

    username = ""
    try:
        user = get_current_user(request)
        if isinstance(user, dict):
            username = str(user.get("username") or user.get("sub") or "").strip()
    except Exception:
        username = "-"

    if not auth_settings.LDAP_ENABLED:
        username = username or "-"
    return username


async def _get_total_projects_and_users(db: AsyncSession) -> Tuple[int, int]:
    from urllib.parse import urlsplit

    from model.http_task import HttpTask
    from model.llm_task import Task

    # Total projects (distinct hosts/domains from target_host in both Task and HttpTask)
    llm_hosts_query = (
        select(Task.target_host)
        .where(
            Task.is_deleted == 0,
            Task.target_host.isnot(None),
            Task.target_host != "",
        )
        .distinct()
    )
    http_hosts_query = (
        select(HttpTask.target_host)
        .where(
            HttpTask.is_deleted == 0,
            HttpTask.target_host.isnot(None),
            HttpTask.target_host != "",
        )
        .distinct()
    )
    llm_hosts_res = await db.execute(llm_hosts_query)
    http_hosts_res = await db.execute(http_hosts_query)

    all_hosts = set()
    llm_hosts = list(llm_hosts_res.scalars().all())
    http_hosts = list(http_hosts_res.scalars().all())
    for h in llm_hosts + http_hosts:
        if h:
            h_clean = h.strip()
            if h_clean:
                parts = urlsplit(h_clean if "://" in h_clean else f"http://{h_clean}")
                netloc = parts.netloc or parts.path
                if netloc:
                    host_part = netloc.split("/")[0].strip().lower()
                    if host_part:
                        all_hosts.add(host_part)

    total_projects = len(all_hosts)

    # Total users (distinct created_by from both Task and HttpTask)
    llm_users_query = (
        select(Task.created_by)
        .where(
            Task.is_deleted == 0,
            Task.created_by.isnot(None),
            Task.created_by != "",
            Task.created_by != "-",
        )
        .distinct()
    )
    http_users_query = (
        select(HttpTask.created_by)
        .where(
            HttpTask.is_deleted == 0,
            HttpTask.created_by.isnot(None),
            HttpTask.created_by != "",
            HttpTask.created_by != "-",
        )
        .distinct()
    )
    llm_users_res = await db.execute(llm_users_query)
    http_users_res = await db.execute(http_users_query)

    all_users = set()
    llm_users = list(llm_users_res.scalars().all())
    http_users = list(http_users_res.scalars().all())
    for u in llm_users + http_users:
        if u:
            cleaned = u.strip()
            if cleaned and cleaned != "-":
                all_users.add(cleaned)
    total_users = len(all_users)

    return total_projects, total_users


async def _get_task_stats(db: AsyncSession, username: str) -> Dict[str, Any]:
    from sqlalchemy import and_, case, func

    from model.http_task import HttpTask
    from model.llm_task import Task

    # LLM Task counts — single query with conditional aggregation
    llm_stats_query = select(
        func.count(Task.id).label("total"),
        func.sum(case((Task.status.in_(["queuing", "created"]), 1), else_=0)).label(
            "pending"
        ),
        func.sum(case((Task.status == "running", 1), else_=0)).label("running"),
        func.sum(case((Task.status == "completed", 1), else_=0)).label("successed"),
        func.sum(case((Task.status == "failed_requests", 1), else_=0)).label(
            "partial_failed"
        ),
        func.sum(case((Task.status == "failed", 1), else_=0)).label("exception"),
        func.sum(case((Task.created_by == username, 1), else_=0)).label("my_count"),
        func.count(
            func.distinct(
                case(
                    (
                        and_(Task.model.isnot(None), Task.model != ""),
                        Task.model,
                    ),
                )
            )
        ).label("unique_models"),
    ).where(Task.is_deleted == 0)

    llm_row = (await db.execute(llm_stats_query)).one()
    llm_total = llm_row.total or 0
    llm_pending = llm_row.pending or 0
    llm_running = llm_row.running or 0
    llm_successed = llm_row.successed or 0
    llm_partial_failed = llm_row.partial_failed or 0
    llm_exception = llm_row.exception or 0
    llm_my = (llm_row.my_count or 0) if (username and username != "-") else 0
    total_models = llm_row.unique_models or 0

    # HTTP Task counts — single query with conditional aggregation
    http_stats_query = select(
        func.count(HttpTask.id).label("total"),
        func.sum(case((HttpTask.status.in_(["queuing", "created"]), 1), else_=0)).label(
            "pending"
        ),
        func.sum(case((HttpTask.status == "running", 1), else_=0)).label("running"),
        func.sum(case((HttpTask.status == "completed", 1), else_=0)).label("successed"),
        func.sum(case((HttpTask.status == "failed_requests", 1), else_=0)).label(
            "partial_failed"
        ),
        func.sum(case((HttpTask.status == "failed", 1), else_=0)).label("exception"),
        func.sum(case((HttpTask.created_by == username, 1), else_=0)).label("my_count"),
    ).where(HttpTask.is_deleted == 0)

    http_row = (await db.execute(http_stats_query)).one()
    http_total = http_row.total or 0
    http_pending = http_row.pending or 0
    http_running = http_row.running or 0
    http_successed = http_row.successed or 0
    http_partial_failed = http_row.partial_failed or 0
    http_exception = http_row.exception or 0
    http_my = (http_row.my_count or 0) if (username and username != "-") else 0

    return {
        "llm_total": llm_total,
        "llm_pending": llm_pending,
        "llm_running": llm_running,
        "llm_successed": llm_successed,
        "llm_partial_failed": llm_partial_failed,
        "llm_exception": llm_exception,
        "total_models": total_models,
        "http_total": http_total,
        "http_pending": http_pending,
        "http_running": http_running,
        "http_successed": http_successed,
        "http_partial_failed": http_partial_failed,
        "http_exception": http_exception,
        "my_tasks_count": llm_my + http_my,
    }


async def _get_weekly_stats(db: AsyncSession) -> List[Dict[str, Any]]:
    from collections import defaultdict
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from model.http_task import HttpTask
    from model.llm_task import Task

    # Weekly task distribution (last 8 weeks) — DB-level grouping
    today = datetime.now().date()
    current_monday = today - timedelta(days=today.weekday())
    eight_weeks_ago = current_monday - timedelta(weeks=7)

    # MySQL: SUBDATE(DATE(created_at), WEEKDAY(created_at)) gives Monday
    llm_monday_expr = func.subdate(
        func.date(Task.created_at), func.weekday(Task.created_at)
    )
    llm_weekly_query = (
        select(
            llm_monday_expr.label("week_monday"),
            func.count(Task.id).label("cnt"),
        )
        .where(Task.is_deleted == 0, Task.created_at >= eight_weeks_ago)
        .group_by(llm_monday_expr)
    )

    http_monday_expr = func.subdate(
        func.date(HttpTask.created_at), func.weekday(HttpTask.created_at)
    )
    http_weekly_query = (
        select(
            http_monday_expr.label("week_monday"),
            func.count(HttpTask.id).label("cnt"),
        )
        .where(HttpTask.is_deleted == 0, HttpTask.created_at >= eight_weeks_ago)
        .group_by(http_monday_expr)
    )

    llm_weekly_rows = (await db.execute(llm_weekly_query)).all()
    http_weekly_rows = (await db.execute(http_weekly_query)).all()

    weeks_data: Dict[str, int] = defaultdict(int)
    for i in range(8):
        monday_of_week = current_monday - timedelta(weeks=i)
        weeks_data[monday_of_week.strftime("%Y-%m-%d")] = 0

    for row in llm_weekly_rows:
        key = str(row.week_monday)
        if key in weeks_data:
            weeks_data[key] += row.cnt
    for row in http_weekly_rows:
        key = str(row.week_monday)
        if key in weeks_data:
            weeks_data[key] += row.cnt

    return [
        {"week": week, "count": count} for week, count in sorted(weeks_data.items())
    ]


async def _get_running_tasks(
    db: AsyncSession,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from model.http_task import HttpTask
    from model.llm_task import Task
    from service.http_task_service import _map_status as map_http_status
    from service.llm_task_service import _map_status as map_llm_status

    # Fetch active running tasks
    running_llm_query = (
        select(Task)
        .where(Task.is_deleted == 0, Task.status == "running")
        .order_by(Task.created_at.desc())
    )
    running_llm_res = await db.execute(running_llm_query)
    running_llm_tasks = [
        {
            "id": t.id,
            "name": t.name,
            "status": map_llm_status(cast(Optional[str], t.status)),
            "model": t.model,
            "concurrent_users": t.concurrent_users,
            "duration": t.duration,
            "created_by": t.created_by or "-",
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
        for t in running_llm_res.scalars().all()
    ]

    running_http_query = (
        select(HttpTask)
        .where(HttpTask.is_deleted == 0, HttpTask.status == "running")
        .order_by(HttpTask.created_at.desc())
    )
    running_http_res = await db.execute(running_http_query)
    running_http_tasks = [
        {
            "id": t.id,
            "name": t.name,
            "status": map_http_status(cast(Optional[str], t.status)),
            "method": t.method,
            "target_url": t.target_url,
            "concurrent_users": t.concurrent_users,
            "duration": t.duration,
            "created_by": t.created_by or "-",
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
        for t in running_http_res.scalars().all()
    ]

    return running_llm_tasks, running_http_tasks


async def get_dashboard_stats_svc(request: Request) -> Dict[str, Any]:
    """
    Get statistics, weekly task distribution, running and recent tasks for the dashboard.
    """
    from utils.auth_settings import get_auth_settings

    auth_settings = get_auth_settings()
    db: AsyncSession = request.state.db
    try:
        username = _get_username(request, auth_settings)

        total_projects, total_users = await _get_total_projects_and_users(db)

        stats = await _get_task_stats(db, username)

        weekly_stats = await _get_weekly_stats(db)

        running_llm_tasks, running_http_tasks = await _get_running_tasks(db)

        return {
            "status": "success",
            "stats": {
                "totalTasks": stats["llm_total"] + stats["http_total"],
                "pendingTasks": stats["llm_pending"] + stats["http_pending"],
                "runningTasks": stats["llm_running"] + stats["http_running"],
                "completedTasks": stats["llm_successed"] + stats["http_successed"],
                "partialFailedTasks": stats["llm_partial_failed"]
                + stats["http_partial_failed"],
                "exceptionTasks": stats["llm_exception"] + stats["http_exception"],
                "failedTasks": stats["llm_exception"]
                + stats["http_exception"]
                + stats["llm_partial_failed"]
                + stats["http_partial_failed"],
                "totalCollections": total_projects,
                "totalProjects": total_projects,
                "totalModels": stats["total_models"],
                "llmTasksCount": stats["llm_total"],
                "httpTasksCount": stats["http_total"],
                "myTasksCount": stats["my_tasks_count"],
                "totalUsers": total_users,
            },
            "weeklyStats": weekly_stats,
            "runningLlmTasks": running_llm_tasks,
            "runningHttpTasks": running_http_tasks,
        }

    except Exception as e:
        logger.exception("Failed to fetch dashboard stats: {}", e)
        return {
            "status": "error",
            "error": str(e),
        }
