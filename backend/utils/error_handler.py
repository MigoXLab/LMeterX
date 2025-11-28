"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Dict, Optional, Union

from fastapi import HTTPException
from starlette.responses import JSONResponse


class ErrorMessages:
    """Common error messages"""

    # General errors
    TASK_ID_MISSING = "Task ID is missing"
    TASK_ID_EMPTY = "Task ID cannot be empty"
    TASK_NOT_FOUND = "Task not found"
    SERVICE_NAME_EMPTY = "Service name cannot be empty"
    FILE_NOT_FOUND = "File not found"
    INVALID_FILE_TYPE = "Invalid file type"
    UNSupported_FILE_TYPE = "Unsupported file type"
    NO_FILES_PROVIDED = "No files were included in the request"
    INTERNAL_SERVER_ERROR = "Internal server error"
    DATABASE_ERROR = "Database operation failed"
    VALIDATION_ERROR = "Validation failed"
    INVALID_LANGUAGE = "Invalid language option"
    HEADERS_LIMIT_EXCEEDED = "Header count exceeds the allowed maximum"
    COOKIES_LIMIT_EXCEEDED = "Cookie count exceeds the allowed maximum"
    REQUEST_PAYLOAD_INVALID = "Request payload is invalid"

    # File related errors
    FILE_UPLOAD_FAILED = "File upload failed"
    FILE_READ_FAILED = "Failed to read file"
    LOG_FILE_NOT_FOUND = "Log file not found"
    LOG_FILE_READ_FAILED = "Failed to read log file"

    # Task related errors
    TASK_CREATION_FAILED = "Failed to create task"
    TASK_UPDATE_FAILED = "Failed to update task"
    TASK_DELETION_FAILED = "Failed to delete task"
    TASK_STOP_FAILED = "Failed to stop task"
    TASK_NO_RESULTS = "No results found for this task"
    ANALYSIS_NOT_FOUND = "Analysis not found for this task"
    MODEL_TASKS_FETCH_FAILED = "Failed to retrieve model tasks for comparison"

    # Configuration related errors
    CONFIG_NOT_FOUND = "Configuration not found"
    CONFIG_ALREADY_EXISTS = "Configuration key already exists"
    INVALID_CONFIG = "Invalid configuration"
    MISSING_AI_CONFIG = "Missing AI service configuration"

    # Authentication related errors
    UNAUTHORIZED = "Unauthorized access"
    INVALID_CREDENTIALS = "Invalid credentials"
    TOKEN_EXPIRED = "Token expired"  # nosec
    INSUFFICIENT_PERMISSIONS = "Insufficient permissions"

    # Streaming/test errors
    STREAM_PROCESSING_TIMEOUT = "Streaming data processing timeout"
    STREAM_PROCESSING_ERROR = "Streaming data processing error"


class ErrorResponse(HTTPException):
    """Single source of truth for standardized error payloads."""

    def __init__(
        self,
        status_code: int,
        error: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.error = error
        self.details = details
        self.code = self._resolve_code(status_code, code)
        self.extra = extra
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.payload: Dict[str, Any] = {
            "success": False,
            "status": "error",
            "error": error,  # legacy field kept for backwards compatibility
            "message": error,
            "code": self.code,
            "status_code": status_code,
            "timestamp": self.timestamp,
        }

        if details is not None:
            self.payload["details"] = details
        if extra:
            self.payload["meta"] = extra

        super().__init__(status_code=status_code, detail=self.payload)

    @staticmethod
    def _resolve_code(status_code: int, explicit_code: Optional[str]) -> str:
        """Infer a normalized code from HTTP status when not explicitly provided."""
        if explicit_code:
            return explicit_code

        try:
            phrase = HTTPStatus(status_code).phrase
            return phrase.lower().replace(" ", "_")
        except ValueError:
            return str(status_code)

    def to_response(self) -> JSONResponse:
        """Serialize the service error into a standardized JSON response."""
        return JSONResponse(status_code=self.status_code, content=self.payload)

    def to_dict(self) -> Dict[str, Any]:
        """Return the serialized payload."""
        return dict(self.payload)

    @classmethod
    def response(
        cls,
        status_code: int,
        error: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> JSONResponse:
        """Return a JSONResponse without forcing the caller to raise."""
        return cls(status_code, error, details, code, extra).to_response()

    @classmethod
    def bad_request(
        cls,
        error: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        return cls(400, error, details, code, extra)

    @classmethod
    def not_found(
        cls,
        error: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        return cls(404, error, details, code, extra)

    @classmethod
    def internal_server_error(
        cls,
        error: str = ErrorMessages.INTERNAL_SERVER_ERROR,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        return cls(500, error, details, code, extra)

    @classmethod
    def unauthorized(
        cls,
        error: str = ErrorMessages.UNAUTHORIZED,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        return cls(401, error, details, code, extra)

    @classmethod
    def forbidden(
        cls,
        error: str = ErrorMessages.INSUFFICIENT_PERMISSIONS,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        return cls(403, error, details, code, extra)

    @classmethod
    def conflict(
        cls,
        error: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        return cls(409, error, details, code, extra)

    @classmethod
    def unprocessable_entity(
        cls,
        error: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "ErrorResponse":
        return cls(422, error, details, code, extra)
