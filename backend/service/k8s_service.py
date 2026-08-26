"""
K8s service: queries the Kubernetes API to list running engine pods.
Used by the reconciler to detect and clean up ghost heartbeat entries.
Only active when K8S_RECONCILE_ENABLED=true.
"""

import os
from typing import List, Optional

from utils.logger import logger

K8S_RECONCILE_ENABLED = os.getenv("K8S_RECONCILE_ENABLED", "false").lower() == "true"
RECONCILE_NAMESPACE = os.getenv("RECONCILE_NAMESPACE", "lmeterx-staging")
RECONCILE_LABEL_SELECTOR = os.getenv("RECONCILE_LABEL_SELECTOR", "app=lmeterx-engine-1")


def get_active_engine_uids() -> Optional[List[str]]:
    """
    Query K8s API for running pods matching the label selector.
    Returns a list of pod UIDs, or None if K8s reconciliation is disabled or fails.
    """
    if not K8S_RECONCILE_ENABLED:
        return None

    try:
        from kubernetes import client, config

        config.load_incluster_config()
        v1 = client.CoreV1Api()

        pods = v1.list_namespaced_pod(
            namespace=RECONCILE_NAMESPACE,
            label_selector=RECONCILE_LABEL_SELECTOR,
            field_selector="status.phase=Running",
        )

        uids = [pod.metadata.uid for pod in pods.items if pod.metadata.uid]
        logger.debug(
            f"[K8s] Found {len(uids)} running pods "
            f"(namespace={RECONCILE_NAMESPACE}, selector={RECONCILE_LABEL_SELECTOR})"
        )
        return uids

    except ImportError:
        logger.warning(
            "[K8s] kubernetes package not installed, skipping reconciliation"
        )
        return None
    except Exception as e:
        logger.warning(f"[K8s] Failed to list pods: {e}")
        return None
