"""
LMeterX Cluster Agent

A lightweight service deployed in each remote K8s cluster.
It polls the central Backend for the desired Engine replica count
and adjusts the local Engine Deployment accordingly.

Environment Variables:
  BACKEND_URL       - Central Backend URL (e.g. https://lmeterx.openxlab.org.cn)
  CLUSTER_ID        - This cluster's unique identifier
  ENGINE_API_TOKEN  - Auth token for Backend API
  NAMESPACE         - K8s namespace where Engine Deployment lives (default: cloud-staging)
  DEPLOYMENT_NAME   - Engine Deployment name (default: lmeterx-engine)
  POLL_INTERVAL     - Seconds between polls (default: 15)
"""

import logging
import os
import signal
import sys
import time

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cluster-agent")

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5001")
CLUSTER_ID = os.getenv("CLUSTER_ID", "")
ENGINE_API_TOKEN = os.getenv("ENGINE_API_TOKEN", "")
NAMESPACE = os.getenv("NAMESPACE", "cloud-staging")
DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "lmeterx-engine")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))

_running = True


def _signal_handler(signum, frame):
    global _running
    logger.info(f"Received signal {signum}, shutting down...")
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def _get_headers():
    headers = {"Content-Type": "application/json"}
    if ENGINE_API_TOKEN:
        headers["X-Authorization"] = f"Bearer {ENGINE_API_TOKEN}"
    return headers


def get_desired_state() -> dict | None:
    """Fetch desired replica state from Backend."""
    try:
        resp = httpx.get(
            f"{BACKEND_URL}/api/clusters/{CLUSTER_ID}/desired-state",
            headers=_get_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to get desired state: {e}")
        return None


def report_actual_state(current: int, ready: int, available: int) -> bool:
    """Report actual deployment state to Backend."""
    try:
        resp = httpx.post(
            f"{BACKEND_URL}/api/clusters/{CLUSTER_ID}/actual-state",
            headers=_get_headers(),
            json={
                "current_replicas": current,
                "ready_replicas": ready,
                "available_replicas": available,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to report actual state: {e}")
        return False


def get_current_replicas() -> tuple[int, int, int]:
    """
    Get current Engine Deployment replica counts from K8s API.
    Returns: (spec.replicas, status.readyReplicas, status.availableReplicas)
    """
    try:
        from kubernetes import client, config

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        deployment = apps_v1.read_namespaced_deployment(
            name=DEPLOYMENT_NAME, namespace=NAMESPACE
        )

        spec_replicas = deployment.spec.replicas or 0
        ready = deployment.status.ready_replicas or 0
        available = deployment.status.available_replicas or 0

        return spec_replicas, ready, available
    except Exception as e:
        logger.error(f"Failed to get deployment status: {e}")
        return 0, 0, 0


def scale_deployment(desired_replicas: int) -> bool:
    """Scale the Engine Deployment to desired replica count."""
    try:
        from kubernetes import client, config

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        apps_v1 = client.AppsV1Api()
        body = {"spec": {"replicas": desired_replicas}}
        apps_v1.patch_namespaced_deployment_scale(
            name=DEPLOYMENT_NAME, namespace=NAMESPACE, body=body
        )
        logger.info(f"Scaled {DEPLOYMENT_NAME} to {desired_replicas} replicas")
        return True
    except Exception as e:
        logger.error(f"Failed to scale deployment: {e}")
        return False


def main():
    if not CLUSTER_ID:
        logger.error("CLUSTER_ID is required. Set it via environment variable.")
        sys.exit(1)

    logger.info(
        f"Cluster Agent starting: cluster={CLUSTER_ID}, "
        f"backend={BACKEND_URL}, namespace={NAMESPACE}, "
        f"deployment={DEPLOYMENT_NAME}, interval={POLL_INTERVAL}s"
    )

    while _running:
        try:
            desired_state = get_desired_state()
            if desired_state is None:
                time.sleep(POLL_INTERVAL)
                continue

            desired_replicas = desired_state.get("desired_replicas", 1)
            current, ready, available = get_current_replicas()

            report_actual_state(current, ready, available)

            if current != desired_replicas:
                logger.info(
                    f"Replica mismatch: current={current}, desired={desired_replicas}. Scaling..."
                )
                scale_deployment(desired_replicas)
            else:
                logger.debug(
                    f"Replicas OK: current={current}, ready={ready}, available={available}"
                )

        except Exception as e:
            logger.exception(f"Unexpected error in main loop: {e}")

        time.sleep(POLL_INTERVAL)

    logger.info("Cluster Agent stopped.")


if __name__ == "__main__":
    main()
