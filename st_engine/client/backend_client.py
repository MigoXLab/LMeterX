"""
Backend HTTP Client for Engine.

Encapsulates all REST API calls from Engine to the central Backend service:
- Registration
- Heartbeat
- Task claiming
- Task status updates
- Task result submission
- Stopping task queries
"""

import os
from typing import Dict, List, Optional

import httpx

from utils.logger import logger

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5001")
ENGINE_API_TOKEN = os.getenv("ENGINE_API_TOKEN", "")
REQUEST_TIMEOUT = 30.0
CONNECT_TIMEOUT = 10.0


def _get_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if ENGINE_API_TOKEN:
        headers["X-Authorization"] = f"Bearer {ENGINE_API_TOKEN}"
    return headers


def _base_url() -> str:
    return f"{BACKEND_URL}/api/engine"


class BackendClient:
    """Synchronous HTTP client for Engine-to-Backend communication."""

    def __init__(self):
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT),
                headers=_get_headers(),
            )
        return self._client

    def close(self):
        if self._client and not self._client.is_closed:
            self._client.close()

    def register(
        self,
        engine_id: str,
        cluster_id: str,
        capabilities: dict,
        version: Optional[str] = None,
        deployment_name: Optional[str] = None,
        pod_name: Optional[str] = None,
    ) -> Optional[dict]:
        try:
            payload = {
                "engine_id": engine_id,
                "cluster_id": cluster_id,
                "capabilities": capabilities,
                "version": version,
            }
            if deployment_name:
                payload["deployment_name"] = deployment_name
            if pod_name:
                payload["pod_name"] = pod_name
            resp = self.client.post(
                f"{_base_url()}/register",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[BackendClient] Register failed: {e}")
            return None

    def heartbeat(
        self,
        engine_id: str,
        cluster_id: str,
        running_tasks: List[str],
        cpu_usage: float,
        memory_usage: float,
        available_slots: int,
        deployment_name: Optional[str] = None,
        pod_name: Optional[str] = None,
    ) -> Optional[dict]:
        try:
            payload = {
                "engine_id": engine_id,
                "cluster_id": cluster_id,
                "running_tasks": running_tasks,
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "available_slots": available_slots,
            }
            if deployment_name:
                payload["deployment_name"] = deployment_name
            if pod_name:
                payload["pod_name"] = pod_name
            resp = self.client.post(
                f"{_base_url()}/heartbeat",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[BackendClient] Heartbeat failed: {e}")
            return None

    def claim_task(
        self,
        engine_id: str,
        cluster_id: str,
        task_types: List[str] = None,
    ) -> Optional[dict]:
        if task_types is None:
            task_types = ["llm", "http"]
        try:
            resp = self.client.post(
                f"{_base_url()}/tasks/claim",
                json={
                    "engine_id": engine_id,
                    "cluster_id": cluster_id,
                    "task_types": task_types,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("task")
        except Exception as e:
            logger.warning(f"[BackendClient] Claim task failed: {e}")
            return None

    def update_task_status(
        self,
        task_id: str,
        engine_id: str,
        status: str,
        progress: Optional[int] = None,
        message: Optional[str] = None,
    ) -> bool:
        try:
            resp = self.client.put(
                f"{_base_url()}/tasks/{task_id}/status",
                json={
                    "engine_id": engine_id,
                    "status": status,
                    "progress": progress,
                    "message": message,
                },
            )
            resp.raise_for_status()
            return resp.json().get("status") == "ok"
        except Exception as e:
            logger.error(f"[BackendClient] Update task status failed: {e}")
            return False

    def submit_results(
        self,
        task_id: str,
        engine_id: str,
        locust_results: Optional[dict] = None,
        final_status: str = "completed",
        error_message: Optional[str] = None,
    ) -> bool:
        try:
            resp = self.client.post(
                f"{_base_url()}/tasks/{task_id}/results",
                json={
                    "engine_id": engine_id,
                    "locust_results": locust_results,
                    "final_status": final_status,
                    "error_message": error_message,
                },
            )
            resp.raise_for_status()
            return resp.json().get("status") == "ok"
        except Exception as e:
            logger.error(f"[BackendClient] Submit results failed: {e}")
            return False

    def get_stopping_tasks(self, engine_id: str, cluster_id: str) -> List[str]:
        try:
            resp = self.client.get(
                f"{_base_url()}/tasks/stopping",
                params={"engine_id": engine_id, "cluster_id": cluster_id},
            )
            resp.raise_for_status()
            return resp.json().get("task_ids", [])
        except Exception as e:
            logger.warning(f"[BackendClient] Get stopping tasks failed: {e}")
            return []

    def unregister(self, engine_id: str, cluster_id: str) -> Optional[dict]:
        try:
            resp = self.client.post(
                f"{_base_url()}/unregister",
                json={"engine_id": engine_id, "cluster_id": cluster_id},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[BackendClient] Unregister failed: {e}")
            return None

    def submit_probe_result(self, probe_id: str, engine_id: str, result: dict) -> bool:
        try:
            resp = self.client.post(
                f"{_base_url()}/probes/{probe_id}/result",
                json={"engine_id": engine_id, "result": result},
            )
            resp.raise_for_status()
            return resp.json().get("status") == "ok"
        except Exception as e:
            logger.error(f"[BackendClient] Submit probe result failed: {e}")
            return False


# Singleton instance
backend_client = BackendClient()
