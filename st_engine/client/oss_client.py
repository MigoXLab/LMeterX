"""
OSS Client for Engine.

Downloads test data files from OSS (or local path) for task execution.
"""

import os
import shutil
import tempfile
from typing import Optional

import httpx

from utils.logger import logger
from utils.sls_settings import get_sls_settings

TEMP_DIR = os.getenv("ENGINE_TEMP_DIR", os.path.join(tempfile.gettempdir(), "lmeterx"))

OSS_ENABLED = os.getenv("OSS_ENABLED", "false").lower() == "true"
sls_settings = get_sls_settings()
SLS_ENABLED = sls_settings.SLS_ENABLED
OSS_LIVE_LOG_SYNC_ENABLED = os.getenv("OSS_LIVE_LOG_SYNC_ENABLED", "").strip().lower()
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
OSS_BUCKET = os.getenv("OSS_BUCKET", "webqa-oss")
OSS_ACCESS_KEY = os.getenv("OSS_ACCESS_KEY", "")
OSS_SECRET_KEY = os.getenv("OSS_SECRET_KEY", "")


def is_oss_live_log_sync_enabled() -> bool:
    """Return whether OSS should be used for running log snapshots.

    By default, SLS owns realtime log query. OSS live snapshots remain enabled
    only when SLS is off, so OSS can still serve as the remote viewing fallback.
    Set OSS_LIVE_LOG_SYNC_ENABLED=true/false to override this auto behavior.
    """
    if not OSS_ENABLED:
        return False
    if OSS_LIVE_LOG_SYNC_ENABLED:
        return OSS_LIVE_LOG_SYNC_ENABLED in {"1", "true", "yes", "on"}
    return not SLS_ENABLED


def is_oss_system_log_snapshot_enabled() -> bool:
    """Return whether OSS should keep engine system-log fallback snapshots.

    System snapshots back the Backend's OSS fallback/download endpoint. Keep
    them on by default when OSS is enabled, but respect an explicit false
    override for deployments that want to disable all live OSS log writes.
    """
    if not OSS_ENABLED:
        return False
    if OSS_LIVE_LOG_SYNC_ENABLED:
        return OSS_LIVE_LOG_SYNC_ENABLED in {"1", "true", "yes", "on"}
    return True


def ensure_temp_dir(task_id: str) -> str:
    task_dir = os.path.join(TEMP_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    return task_dir


def download_test_data(task_id: str, test_data_url: Optional[str]) -> Optional[str]:
    if not test_data_url:
        return None

    if not test_data_url.startswith("http"):
        if os.path.exists(test_data_url):
            return test_data_url
        logger.warning(f"Local test data not found: {test_data_url}")
        return None

    task_dir = ensure_temp_dir(task_id)
    filename = test_data_url.split("/")[-1].split("?")[0] or "data.csv"
    local_path = os.path.join(task_dir, filename)

    try:
        with httpx.stream(
            "GET", test_data_url, timeout=120.0, follow_redirects=True
        ) as resp:
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        logger.info(f"Downloaded test data for task {task_id}: {local_path}")
        return local_path
    except Exception as e:
        logger.error(f"Failed to download test data for task {task_id}: {e}")
        return None


def cleanup_task_files(task_id: str):
    task_dir = os.path.join(TEMP_DIR, task_id)
    if os.path.exists(task_dir):
        try:
            shutil.rmtree(task_dir)
            logger.debug(f"Cleaned up temp files for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp files for task {task_id}: {e}")


def upload_system_log_to_oss(engine_id: str, cluster_id: str) -> bool:
    """Upload the tail of this engine's system log to OSS for remote viewing.

    Reads the last 200KB of the local engine-specific log and pushes it to
    logs/system/{cluster_id}/{engine_id}/engine.log, overwriting each cycle.
    """
    if not OSS_ENABLED:
        return False

    try:
        import boto3
        from botocore.config import Config

        from config.base import LOG_DIR

        log_file = os.path.join(LOG_DIR, f"engine_{engine_id}.log")
        if not os.path.exists(log_file):
            # Backward-compatible fallback for older engine images.
            log_file = os.path.join(LOG_DIR, "engine.log")
        if not os.path.exists(log_file):
            return False

        max_bytes = 200 * 1024
        file_size = os.path.getsize(log_file)

        # Read last 200KB without modifying the file
        with open(log_file, "rb") as f:
            if file_size > max_bytes:
                f.seek(file_size - max_bytes)
            content = f.read()

        # Write to a temp file for upload
        tmp_path = os.path.join(tempfile.gettempdir(), f"engine_log_{engine_id}.tmp")
        with open(tmp_path, "wb") as f:
            f.write(content)

        s3_client = boto3.client(
            "s3",
            endpoint_url=OSS_ENDPOINT,
            aws_access_key_id=OSS_ACCESS_KEY,
            aws_secret_access_key=OSS_SECRET_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual", "payload_signing_enabled": True},
                request_checksum_calculation="when_required",
            ),
        )

        object_key = f"logs/system/{cluster_id}/{engine_id}/engine.log"
        s3_client.upload_file(tmp_path, OSS_BUCKET, object_key)

        try:
            os.remove(tmp_path)
        except OSError:
            pass

        return True
    except Exception as e:
        logger.debug(f"Failed to push system log to OSS: {e}")
        return False


def upload_task_logs_to_oss(task_id: str, include_archives: bool = True) -> bool:
    if not OSS_ENABLED:
        return False

    try:
        import boto3
        from botocore.config import Config

        from config.base import LOG_TASK_DIR

        s3_client = boto3.client(
            "s3",
            endpoint_url=OSS_ENDPOINT,
            aws_access_key_id=OSS_ACCESS_KEY,
            aws_secret_access_key=OSS_SECRET_KEY,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual", "payload_signing_enabled": True},
                request_checksum_calculation="when_required",
            ),
        )

        uploaded_any = False

        if os.path.exists(LOG_TASK_DIR):
            for filename in os.listdir(LOG_TASK_DIR):
                if filename.startswith(f"task_{task_id}_"):
                    if not include_archives and not filename.endswith(".log"):
                        continue
                    local_file_path = os.path.join(LOG_TASK_DIR, filename)
                    if os.path.isfile(local_file_path):
                        object_key = f"logs/{filename}"
                        s3_client.upload_file(local_file_path, OSS_BUCKET, object_key)
                        logger.info(
                            f"Uploaded task log file {filename} to OSS: {object_key}"
                        )
                        uploaded_any = True

        return uploaded_any
    except Exception as e:
        logger.error(f"Failed to upload task logs to OSS for task {task_id}: {e}")
        return False
