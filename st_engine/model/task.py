"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field
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

    key: str
    value: str
    fixed: bool = True


class CookieItem(BaseModel):
    """
    Represents a single HTTP cookie item for a request.

    Attributes:
        key: The cookie name.
        value: The cookie value.
    """

    key: str
    value: str


class CertConfig(BaseModel):
    """
    Configuration for SSL/TLS certificates.

    Attributes:
        cert_file: Path to the SSL certificate file.
        key_file: Path to the SSL private key file.
    """

    cert_file: Optional[str] = Field(None, description="Path to the certificate file")
    key_file: Optional[str] = Field(None, description="Path to the private key file")


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

    temp_task_id: str
    name: str = Field(..., description="Name of the task")
    target_host: str = Field(..., description="Target model API host")
    api_path: str = Field(default="/chat/completions", description="API path to test")
    model: str = Field(..., description="Name of the model to test")
    duration: int = Field(
        default=300, ge=1, description="Duration of the test in seconds"
    )
    concurrent_users: int = Field(..., ge=1, description="Number of concurrent users")
    spawn_rate: int = Field(ge=1, description="Number of users to spawn per second")
    chat_type: int = Field(ge=0, description="Type of chat interaction")
    stream_mode: bool = Field(
        default=True, description="Whether to use streaming response"
    )
    headers: List[HeaderItem] = Field(
        default_factory=list, description="List of request headers"
    )
    cookies: List[CookieItem] = Field(
        default_factory=list, description="List of request cookies"
    )
    cert_config: Optional[CertConfig] = Field(
        default=None, description="Certificate configuration"
    )
    request_payload: Optional[str] = Field(
        default="", description="Custom request payload for non-chat APIs (JSON string)"
    )
    field_mapping: Optional[Dict[str, str]] = Field(
        default=None, description="Field mapping configuration for custom APIs"
    )
    test_data: Optional[str] = Field(
        default="", description="Custom test data in JSONL format or file path"
    )


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


class Task(Base):
    """
    SQLAlchemy model representing a task in the 'tasks' table.
    """

    __tablename__ = "tasks"
    id = Column(String(40), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    created_by = Column(String(100), nullable=True)
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
    api_type = Column(String(50), nullable=True)
    request_payload = Column(Text, nullable=True)
    field_mapping = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    test_data = Column(Text, nullable=True)


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
    total_tps = Column(Float, nullable=False)
    completion_tps = Column(Float, nullable=False)
    avg_total_tokens_per_req = Column(Float, nullable=False)
    avg_completion_tokens_per_req = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_task_result_item(self) -> TaskResultItem:
        """Converts the SQLAlchemy model instance to a Pydantic TaskResultItem."""
        return TaskResultItem(
            id=self.id,
            task_id=self.task_id,
            metric_type=self.metric_type,
            request_count=self.num_requests,
            failure_count=self.num_failures,
            avg_response_time=self.avg_latency,
            min_response_time=self.min_latency,
            max_response_time=self.max_latency,
            median_response_time=self.median_latency,
            percentile_90_response_time=self.p90_latency,
            rps=self.rps,
            avg_content_length=self.avg_content_length,
            created_at=self.created_at.isoformat(),
            total_tps=self.total_tps,
            completion_tps=self.completion_tps,
            avg_total_tokens_per_req=self.avg_total_tokens_per_req,
            avg_completion_tokens_per_req=self.avg_completion_tokens_per_req,
        )
