"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.

OSS (Object Storage Service) integration for file upload/download.
Provides presigned URL generation for cross-cluster file access.
"""

import os
from typing import Optional

from utils.logger import logger

OSS_ENABLED = os.getenv("OSS_ENABLED", "false").lower() == "true"
OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
OSS_BUCKET = os.getenv("OSS_BUCKET", "lmeterx-data")
OSS_ACCESS_KEY = os.getenv("OSS_ACCESS_KEY", "")
OSS_SECRET_KEY = os.getenv("OSS_SECRET_KEY", "")
OSS_URL_EXPIRY = int(os.getenv("OSS_URL_EXPIRY", "7200"))


def _is_object_not_found_error(error: Exception) -> bool:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False

    error_info = response.get("Error", {})
    code = str(error_info.get("Code", "")).lower()
    status_code = str(response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
    return status_code == "404" or code in {"404", "nosuchkey", "notfound"}


def generate_presigned_url(
    file_path: str, expiry: int = OSS_URL_EXPIRY
) -> Optional[str]:
    if not OSS_ENABLED:
        return None

    try:
        import boto3
        from botocore.config import Config

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

        object_key = file_path.lstrip("/")
        if not object_key.startswith("upload_files/"):
            object_key = f"upload_files/{object_key}"

        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": OSS_BUCKET, "Key": object_key},
            ExpiresIn=expiry,
        )
        return url
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {file_path}: {e}")
        return None


async def upload_file_to_oss(local_path: str, object_key: str) -> bool:
    if not OSS_ENABLED:
        return False

    try:
        import boto3
        from botocore.config import Config

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

        s3_client.upload_file(local_path, OSS_BUCKET, object_key)
        logger.info(f"Uploaded {local_path} to OSS: {object_key}")
        return True
    except Exception as e:
        logger.error(f"Failed to upload {local_path} to OSS: {e}")
        return False


async def download_file_from_oss(object_key: str, local_path: str) -> bool:
    if not OSS_ENABLED:
        return False

    try:
        import boto3
        from botocore.config import Config

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

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        s3_client.download_file(OSS_BUCKET, object_key, local_path)
        logger.info(f"Downloaded {object_key} from OSS to {local_path}")
        return True
    except Exception as e:
        if _is_object_not_found_error(e):
            logger.warning(f"OSS object not found: {object_key}")
        else:
            logger.error(f"Failed to download {object_key} from OSS: {e}")
        return False


def list_files_in_oss(prefix: str) -> list[str]:
    if not OSS_ENABLED:
        return []

    try:
        import boto3
        from botocore.config import Config

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

        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=OSS_BUCKET, Prefix=prefix)
        keys = []
        for page in pages:
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
    except Exception as e:
        logger.error(f"Failed to list files in OSS with prefix {prefix}: {e}")
        return []
