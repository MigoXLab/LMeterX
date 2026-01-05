"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import List, Optional

from fastapi import APIRouter, File, Request, UploadFile

from model.upload import UploadFileRsp
from service.upload_service import upload_file_svc

# Create an API router for file upload endpoints
router = APIRouter()


@router.post("", response_model=UploadFileRsp)
async def upload_file(
    request: Request,
    task_id: Optional[str] = None,
    file_type: Optional[str] = "dataset",
    cert_type: Optional[str] = "cert_file",
    files: List[UploadFile] = File(..., description="The file(s) to upload"),
):
    """
    Upload one or more files.

    This endpoint handles file uploads and can be used for different purposes
    based on the 'file_type' parameter. For example, it can be used to upload
    certificates or files related to a specific task.

    Args:
        file_type (str, optional): The type of upload (e.g., "cert", "dataset").
        cert_type (str, optional): The specific type of certificate. Only used for cert uploads.
        task_id (str, optional): The ID of the task to associate the upload with.
        files (List[UploadFile]): A list of files to be uploaded.

    Returns:
        UploadFileRsp: A response object confirming the file upload.
    """
    return await upload_file_svc(request, task_id, file_type, cert_type, files)
