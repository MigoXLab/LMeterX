"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import re
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from db.mysql import Base


class Pagination(BaseModel):
    """
    Defines the pagination metadata for paginated responses.

    Attributes:
        total: The total number of items across all pages.
        page: The current page number.
        page_size: The number of items per page.
        total_pages: The total number of pages.
    """

    total: int = 0
    page: int = 0
    page_size: int = 0
    total_pages: int = 0


class TaskResponse(BaseModel):
    """
    Standard response model for a list of tasks with pagination.

    Attributes:
        data: A list of task data.
        pagination: Pagination metadata.
        status: The status of the response (e.g., "success").
    """

    data: List[Dict]
    pagination: Pagination
    status: str


class TaskStatusRsp(BaseModel):
    """
    Response model for querying the status of a task.

    Attributes:
        data: A list of status-related data points.
        timestamp: The timestamp of the status check.
        status: The overall status of the response.
    """

    data: List[Dict]
    timestamp: int
    status: str


class TaskCreateRsp(BaseModel):
    """
    Response model for a task creation request.

    Attributes:
        task_id: The unique identifier for the created task.
        status: The initial status of the task.
        message: A message indicating the result of the creation request.
    """

    task_id: str
    status: str
    message: str


class HeaderItem(BaseModel):
    """
    Represents a single HTTP header item for a request.

    Attributes:
        key: The header name.
        value: The header value.
        fixed: A boolean indicating if the header is fixed (not used currently).
    """

    key: str = Field(
        ..., min_length=1, max_length=100, description="Header name (1-100 chars)"
    )
    value: str = Field(
        ..., max_length=1000, description="Header value (max 1000 chars)"
    )
    fixed: bool = True


class CookieItem(BaseModel):
    """
    Represents a single HTTP cookie item for a request.

    Attributes:
        key: The cookie name.
        value: The cookie value.
    """

    key: str = Field(
        ..., min_length=1, max_length=100, description="Cookie name (1-100 chars)"
    )
    value: str = Field(
        ..., max_length=1000, description="Cookie value (max 1000 chars)"
    )


class CertConfig(BaseModel):
    """
    Configuration for SSL/TLS certificates.

    Attributes:
        cert_file: Path to the SSL certificate file.
        key_file: Path to the SSL private key file.
    """

    cert_file: Optional[str] = Field(
        None, max_length=255, description="Path to the certificate file (max 255 chars)"
    )
    key_file: Optional[str] = Field(
        None, max_length=255, description="Path to the private key file (max 255 chars)"
    )


class TaskStopReq(BaseModel):
    """
    Request model to stop a running task.

    Attributes:
        task_id: The ID of the task to be stopped.
    """

    task_id: str


class TaskCreateReq(BaseModel):
    """
    Request model for creating a new performance testing task.
    """

    temp_task_id: str = Field(..., max_length=100, description="Temporary task ID")
    name: str = Field(..., min_length=1, max_length=100, description="Name of the task")
    target_host: str = Field(
        ..., min_length=1, max_length=255, description="Target model API host"
    )
    api_path: str = Field(
        default="/chat/completions", max_length=255, description="API path to test"
    )
    model: Optional[str] = Field(
        default="", max_length=255, description="Name of the model to test"
    )
    duration: int = Field(
        default=300,
        ge=1,
        le=172800,
        description="Duration of the test in seconds (1-48 hours)",
    )
    concurrent_users: int = Field(
        ..., ge=1, le=5000, description="Number of concurrent users (1-5000)"
    )
    spawn_rate: int = Field(
        ge=1, le=100, description="Number of users to spawn per second (1-100)"
    )
    chat_type: Optional[int] = Field(
        default=0,
        ge=0,
        le=2,
        description=(
            "Built-in dataset selector: 0=text self-built, "
            "1=ShareGPT partial, 2=vision self-built"
        ),
    )
    stream_mode: bool = Field(
        default=True, description="Whether to use streaming response"
    )
    headers: List[HeaderItem] = Field(
        default_factory=list,
        description="List of request headers (max 50)",
    )
    cookies: List[CookieItem] = Field(
        default_factory=list,
        description="List of request cookies (max 50)",
    )
    cert_config: Optional[CertConfig] = Field(
        default=None, description="Certificate configuration"
    )
    request_payload: Optional[str] = Field(
        default="",
        max_length=50000,
        description="Custom request payload for non-chat APIs (JSON string, max 50000 chars)",
    )
    field_mapping: Optional[Dict[str, str]] = Field(
        default=None, description="Field mapping configuration for custom APIs"
    )
    api_type: Optional[str] = Field(
        default="openai-chat",
        description="API type: openai-chat, claude-chat, embeddings, or custom-chat",
    )
    test_data: Optional[str] = Field(
        default="",
        max_length=1000000,
        description="Custom test data in JSONL format or file path (max 1MB)",
    )

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        if len(v.strip()) > 100:
            raise ValueError("Name length cannot exceed 100 characters")
        return v.strip()

    @validator("target_host")
    def validate_target_host(cls, v):
        if not v or not v.strip():
            raise ValueError("API address cannot be empty")
        v = v.strip()
        if len(v) > 255:
            raise ValueError("API address length cannot exceed 255 characters")
        # 基本URL格式验证
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("API address must start with http:// or https://")
        return v

    @validator("api_path")
    def validate_api_path(cls, v):
        if not v or not v.strip():
            raise ValueError("API path cannot be empty")
        v = v.strip()
        if len(v) > 255:
            raise ValueError("API path length cannot exceed 255 characters")
        if not v.startswith("/"):
            raise ValueError("API path must start with /")
        return v

    @validator("model")
    def validate_model(cls, v):
        if v and len(v.strip()) > 255:
            raise ValueError("Model name length cannot exceed 255 characters")
        return v.strip() if v else ""

    @validator("request_payload")
    def validate_request_payload(cls, v, values):
        """Ensure request_payload is never empty - auto-generate if needed"""
        # If request_payload is empty, generate default payload
        if not v or not v.strip():
            model = values.get("model", "your-model-name")
            stream_mode = values.get("stream_mode", True)

            # Generate default payload for chat/completions API
            default_payload = {
                "model": model,
                "stream": stream_mode,
                "messages": [{"role": "user", "content": "Hi"}],
            }

            import json

            return json.dumps(default_payload)

        # Validate length
        if len(v) > 50000:
            raise ValueError("Request payload length cannot exceed 50000 characters")

        # Validate JSON format
        try:
            import json

            json.loads(v.strip())
        except json.JSONDecodeError:
            raise ValueError("Request payload must be a valid JSON format")

        return v.strip()

    @validator("headers")
    def validate_headers(cls, v):
        if len(v) > 50:
            raise ValueError("Request header count cannot exceed 50")
        for header in v:
            if not header.key or not header.key.strip():
                raise ValueError("Request header name cannot be empty")
            if len(header.key.strip()) > 100:
                raise ValueError(
                    "Request header name length cannot exceed 100 characters"
                )
            if len(header.value) > 1000:
                raise ValueError(
                    "Request header value length cannot exceed 1000 characters"
                )
        return v

    @validator("cookies")
    def validate_cookies(cls, v):
        if len(v) > 50:
            raise ValueError("Cookie count cannot exceed 50")
        for cookie in v:
            if not cookie.key or not cookie.key.strip():
                raise ValueError("Cookie name cannot be empty")
            if len(cookie.key.strip()) > 100:
                raise ValueError("Cookie name length cannot exceed 100 characters")
            if len(cookie.value) > 1000:
                raise ValueError("Cookie value length cannot exceed 1000 characters")
        return v

    @validator("test_data")
    def validate_test_data(cls, v):
        if v and len(v) > 1000000:  # 1MB
            raise ValueError("Test data size cannot exceed 1MB")
        return v


class TaskResultItem(BaseModel):
    """
    Represents a single data point of a task's performance results.
    """

    avg_content_length: float
    avg_response_time: float
    created_at: str
    failure_count: int
    id: int
    max_response_time: float
    median_response_time: float
    metric_type: str
    min_response_time: float
    percentile_90_response_time: float
    request_count: int
    rps: float
    task_id: str
    total_tps: float
    completion_tps: float
    avg_total_tokens_per_req: float
    avg_completion_tokens_per_req: float


class TaskResultRsp(BaseModel):
    """
    Response model for task performance results.

    Attributes:
        results: A list of `TaskResultItem` objects.
        status: The status of the response.
        error: An error message if the request failed, otherwise None.
    """

    results: List[TaskResultItem]
    status: str
    error: Union[str, None]


class ModelTaskInfo(BaseModel):
    """
    Model information for performance comparison.

    Attributes:
        model_name: The name of the model.
        concurrent_users: The number of concurrent users.
        task_id: The task ID.
        task_name: The task name.
        created_at: The creation timestamp.
        duration: The test duration in seconds.
    """

    model_name: str
    concurrent_users: int
    task_id: str
    task_name: str
    created_at: str
    duration: int


class ComparisonRequest(BaseModel):
    """
    Request model for performance comparison.

    Attributes:
        selected_tasks: List of task IDs to compare.
    """

    selected_tasks: List[str] = Field(
        ..., min_length=2, max_length=10, description="Task IDs to compare"
    )


class ComparisonMetrics(BaseModel):
    """
    Comparison metrics for a single task.

    Attributes:
        task_id: The task ID.
        model_name: The model name.
        concurrent_users: The number of concurrent users.
        task_name: The task name.
        duration: Test duration with 's' suffix.
        stream_mode: Whether stream mode is enabled.
        dataset_type: Type of dataset used.
        first_token_latency: Time to first token (avg_latency in seconds).
        total_time: Total time for request completion.
        total_tps: Total tokens per second.
        completion_tps: Completion tokens per second.
        avg_total_tokens_per_req: Average total tokens per request.
        avg_completion_tokens_per_req: Average completion tokens per request.
        rps: Requests per second.
    """

    task_id: str
    model_name: str
    concurrent_users: int
    task_name: str
    duration: str
    stream_mode: bool
    dataset_type: str
    first_token_latency: float
    total_time: float
    total_tps: float
    completion_tps: float
    avg_total_tokens_per_req: float
    avg_completion_tokens_per_req: float
    rps: float


class ComparisonResponse(BaseModel):
    """
    Response model for performance comparison.

    Attributes:
        data: List of comparison metrics.
        status: The status of the response.
        error: An error message if the request failed, otherwise None.
    """

    data: List[ComparisonMetrics]
    status: str
    error: Union[str, None]


class ModelTasksResponse(BaseModel):
    """
    Response model for getting available model tasks for comparison.

    Attributes:
        data: List of model task information.
        status: The status of the response.
        error: An error message if the request failed, otherwise None.
    """

    data: List[ModelTaskInfo]
    status: str
    error: Union[str, None]


class Task(Base):
    """
    SQLAlchemy model representing a task in the 'tasks' table.
    """

    __tablename__ = "tasks"
    id = Column(String(40), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    target_host = Column(String(255), nullable=False)
    model = Column(String(100), nullable=True)
    stream_mode = Column(String(20), nullable=False)
    concurrent_users = Column(Integer, nullable=False)
    spawn_rate = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    chat_type = Column(Integer, nullable=True)
    log_file = Column(Text, nullable=True)
    result_file = Column(Text, nullable=True)
    cert_file = Column(String(255), nullable=True)
    key_file = Column(String(255), nullable=True)
    headers = Column(Text, nullable=True)
    cookies = Column(Text, nullable=True)
    api_path = Column(String(255), nullable=True)
    request_payload = Column(Text, nullable=True)
    field_mapping = Column(Text, nullable=True)
    api_type = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    test_data = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TaskResult(Base):
    """
    SQLAlchemy model for storing performance results of a task in the 'task_results' table.
    """

    __tablename__ = "task_results"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(40), nullable=False)
    metric_type = Column(String(36), nullable=False)
    num_requests = Column(Integer, nullable=False)
    num_failures = Column(Integer, nullable=False)
    avg_latency = Column(Float, nullable=False)
    min_latency = Column(Float, nullable=False)
    max_latency = Column(Float, nullable=False)
    median_latency = Column(Float, nullable=False)
    p90_latency = Column(Float, nullable=False)
    rps = Column(Float, nullable=False)
    avg_content_length = Column(Float, nullable=False)
    total_tps = Column(Float, nullable=True, default=0.0)
    completion_tps = Column(Float, nullable=True, default=0.0)
    avg_total_tokens_per_req = Column(Float, nullable=True, default=0.0)
    avg_completion_tokens_per_req = Column(Float, nullable=True, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_task_result_item(self) -> TaskResultItem:
        """Converts the SQLAlchemy model instance to a Pydantic TaskResultItem."""
        return TaskResultItem(
            id=int(self.id) if self.id is not None else 0,
            task_id=str(self.task_id) if self.task_id is not None else "",
            metric_type=str(self.metric_type) if self.metric_type is not None else "",
            request_count=(
                int(self.num_requests) if self.num_requests is not None else 0
            ),
            failure_count=(
                int(self.num_failures) if self.num_failures is not None else 0
            ),
            avg_response_time=(
                float(self.avg_latency) if self.avg_latency is not None else 0.0
            ),
            min_response_time=(
                float(self.min_latency) if self.min_latency is not None else 0.0
            ),
            max_response_time=(
                float(self.max_latency) if self.max_latency is not None else 0.0
            ),
            median_response_time=(
                float(self.median_latency) if self.median_latency is not None else 0.0
            ),
            percentile_90_response_time=(
                float(self.p90_latency) if self.p90_latency is not None else 0.0
            ),
            rps=float(self.rps) if self.rps is not None else 0.0,
            avg_content_length=(
                float(self.avg_content_length)
                if self.avg_content_length is not None
                else 0.0
            ),
            created_at=self.created_at.isoformat() if self.created_at else "",
            total_tps=float(self.total_tps) if self.total_tps is not None else 0.0,
            completion_tps=(
                float(self.completion_tps) if self.completion_tps is not None else 0.0
            ),
            avg_total_tokens_per_req=(
                float(self.avg_total_tokens_per_req)
                if self.avg_total_tokens_per_req is not None
                else 0.0
            ),
            avg_completion_tokens_per_req=(
                float(self.avg_completion_tokens_per_req)
                if self.avg_completion_tokens_per_req is not None
                else 0.0
            ),
        )
