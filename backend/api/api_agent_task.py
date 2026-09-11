"""HTTP API for MCP and A2A load-test jobs."""

from typing import Any, Dict

from fastapi import APIRouter, Query, Request

from model.agent_task import AgentTaskCreateReq
from service.agent_task_service import (
    create_agent_task,
    delete_agent_task,
    get_agent_task,
    get_agent_task_copy_template,
    get_agent_task_results,
    list_agent_tasks,
    rerun_agent_task,
    stop_agent_task,
    test_agent_connection_for_request,
    update_agent_task,
)

router = APIRouter()


@router.get("")
async def list_tasks(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    protocol: str | None = Query(None),
):
    return await list_agent_tasks(request, page, page_size, protocol)


@router.post("")
async def create_task(request: Request, body: AgentTaskCreateReq):
    return await create_agent_task(request, body)


@router.post("/test-connection")
async def test_connection(request: Request, body: AgentTaskCreateReq):
    return await test_agent_connection_for_request(request, body)


@router.post("/{task_id}/stop")
async def stop_task(request: Request, task_id: str):
    return await stop_agent_task(request, task_id)


@router.post("/{task_id}/rerun")
async def rerun_task(request: Request, task_id: str):
    return await rerun_agent_task(request, task_id)


@router.get("/{task_id}/results")
async def task_results(request: Request, task_id: str):
    return await get_agent_task_results(request, task_id)


@router.get("/{task_id}/status")
async def task_status(request: Request, task_id: str):
    task = await get_agent_task(request, task_id)
    return {
        key: task[key]
        for key in ("id", "name", "status", "error_message", "updated_at")
    }


@router.get("/{task_id}/copy-template")
async def task_copy_template(request: Request, task_id: str):
    return await get_agent_task_copy_template(request, task_id)


@router.get("/{task_id}")
async def task_detail(request: Request, task_id: str):
    return await get_agent_task(request, task_id)


@router.put("/{task_id}")
async def update_task(request: Request, task_id: str, body: Dict[str, Any]):
    return await update_agent_task(request, task_id, body)


@router.delete("/{task_id}")
async def delete_task(request: Request, task_id: str):
    return await delete_agent_task(request, task_id)
