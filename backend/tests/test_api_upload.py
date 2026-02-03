"""
Upload API tests.
"""

import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from model.upload import UploadedFileInfo, UploadFileRsp

client = TestClient(app)


class TestUploadAPI:
    """File upload API tests."""

    @patch("api.api_upload.upload_file_svc")
    def test_upload_file_success(self, mock_upload):
        test_file_content = b"test certificate content"
        test_file = io.BytesIO(test_file_content)

        file_info = UploadedFileInfo(
            originalname="cert.pem",
            path="/uploads/cert_123.pem",
            size=len(test_file_content),
        )

        mock_response = UploadFileRsp(
            message="File uploaded successfully",
            task_id="task_123",
            files=[file_info],
            cert_config={"cert_file": "/uploads/cert_123.pem", "key_file": None},
        )
        mock_upload.return_value = mock_response

        files = {"files": ("cert.pem", test_file, "application/x-pem-file")}
        data = {"type": "cert", "cert_type": "cert_file", "task_id": "task_123"}

        response = client.post("/api/upload", files=files, data=data)
        assert response.status_code == 200

        response_data = response.json()
        assert "successfully" in response_data["message"]
        assert response_data["task_id"] == "task_123"
        assert len(response_data["files"]) == 1

    @patch("api.api_upload.upload_file_svc")
    def test_upload_multiple_files(self, mock_upload):
        file_info1 = UploadedFileInfo(
            originalname="cert.pem", path="/uploads/cert_123.pem", size=100
        )
        file_info2 = UploadedFileInfo(
            originalname="key.pem", path="/uploads/key_123.pem", size=200
        )

        mock_response = UploadFileRsp(
            message="Files uploaded successfully",
            task_id="task_456",
            files=[file_info1, file_info2],
            cert_config={
                "cert_file": "/uploads/cert_123.pem",
                "key_file": "/uploads/key_123.pem",
            },
        )
        mock_upload.return_value = mock_response

        files = [
            (
                "files",
                ("cert.pem", io.BytesIO(b"cert content"), "application/x-pem-file"),
            ),
            (
                "files",
                ("key.pem", io.BytesIO(b"key content"), "application/x-pem-file"),
            ),
        ]
        data = {"type": "cert", "cert_type": "both", "task_id": "task_456"}

        response = client.post("/api/upload", files=files, data=data)
        assert response.status_code == 200

        response_data = response.json()
        assert "successfully" in response_data["message"]
        assert len(response_data["files"]) == 2

    def test_upload_no_file(self):
        data = {"type": "cert", "cert_type": "cert_file", "task_id": "task_789"}
        response = client.post("/api/upload", data=data)
        assert response.status_code == 422
