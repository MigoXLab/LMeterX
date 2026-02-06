"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from db.mysql import Base


# ---------- Pydantic schemas ----------
class CommonTaskPagination(BaseModel):
    """Pagination metadata for common API tasks."""

    total: int = 0
    page: int = 0
    page_size: int = 0
    total_pages: int = 0


class CommonTaskCreateRsp(BaseModel):
    """Response payload when creating a common API task."""

    task_id: str
    status: str
    message: str


class CommonTaskStatusRsp(BaseModel):
    """Lightweight status list response for common API tasks."""

    data: List[Dict]
    timestamp: int
    status: str


class CommonHeaderItem(BaseModel):
    """Represents a single HTTP header."""

    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., max_length=2000)


class CommonTaskCreateReq(BaseModel):
    """Request payload for creating a common API load test."""

    temp_task_id: str = Field(..., max_length=100, description="Temporary task ID")
    name: str = Field(..., min_length=1, max_length=100, description="Task name")
    method: str = Field(..., description="HTTP method, e.g. GET/POST/PUT/PATCH/DELETE")
    target_url: str = Field(..., max_length=2000, description="Full request URL")
    headers: List[CommonHeaderItem] = Field(default_factory=list)
    cookies: List[CommonHeaderItem] = Field(default_factory=list)
    request_body: Optional[str] = Field(
        default=None, max_length=100000, description="Request body (raw text/JSON)"
    )
    dataset_file: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        max_length=4096,
        description="Path to uploaded dataset file (JSONL, one request per line)",
    )
    curl_command: Optional[str] = Field(
        default=None, max_length=8000, description="Original curl command"
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
    spawn_rate: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000,
        description="Users spawned per second. Defaults to concurrent_users.",
    )

    @validator("name")
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @validator("method")
    def validate_method(cls, v: str) -> str:
        if not v:
            raise ValueError("HTTP method is required")
        method = v.strip().upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            raise ValueError("Unsupported HTTP method")
        return method

    @validator("target_url")
    def validate_target_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Target URL cannot be empty")
        url = v.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("Target URL must start with http:// or https://")
        if len(url) > 2000:
            raise ValueError("Target URL length cannot exceed 2000 characters")
        return url

    @validator("headers", "cookies")
    def validate_kv_items(cls, items: List[CommonHeaderItem]) -> List[CommonHeaderItem]:
        if len(items) > 50:
            raise ValueError("Header/Cookie count cannot exceed 50")
        return items

    @validator("request_body")
    def validate_body(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        body = v.strip()
        if len(body) > 100000:
            raise ValueError("Request body length cannot exceed 100000 characters")
        return body

    @validator("dataset_file", pre=True)
    def normalize_dataset_file(cls, v: Any) -> Optional[str]:
        """
        Accept both plain string path and upload widgets' nested payloads.
        Expected to extract a path string like '/app/upload_files/xxx/file.jsonl'.
        """
        if v is None or v == "":
            return None

        # If already a string, strip and return
        if isinstance(v, str):
            path = v.strip()
            return path or None

        # Helper to safely dig into dict/list structures
        def _first_path(obj: Any) -> Optional[str]:
            if not obj:
                return None
            if isinstance(obj, str):
                return obj
            if isinstance(obj, dict):
                # common patterns: {'path': '...'} or nested response/files/fileList
                if "path" in obj and isinstance(obj["path"], str):
                    return obj["path"]
                if "response" in obj:
                    resp = obj.get("response") or {}
                    if isinstance(resp, dict):
                        if isinstance(resp.get("path"), str):
                            return resp["path"]
                        files = resp.get("files")
                        if isinstance(files, list) and files:
                            return _first_path(files[0])
                if (
                    "fileList" in obj
                    and isinstance(obj["fileList"], list)
                    and obj["fileList"]
                ):
                    return _first_path(obj["fileList"][0])
                if "file" in obj:
                    return _first_path(obj["file"])
            if isinstance(obj, list) and obj:
                return _first_path(obj[0])
            return None

        path_str: Optional[str] = _first_path(v)
        if path_str is None:
            return None

        path_clean = str(path_str).strip()
        if len(path_clean) > 4096:
            raise ValueError("Dataset file path length cannot exceed 4096 characters")
        return path_clean or None


class CommonTaskResultItem(BaseModel):
    """Represents a single metric row for common API task results."""

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


class CommonTaskResultRsp(BaseModel):
    """Response model for common API task performance results."""

    results: List[CommonTaskResultItem]
    status: str
    error: Union[str, None]


class CommonTaskResponse(BaseModel):
    """Paginated common API task response."""

    data: List[Dict]
    pagination: CommonTaskPagination
    status: str


class CommonComparisonTaskInfo(BaseModel):
    """Basic task info used for comparison selection."""

    task_id: str
    task_name: str
    method: str
    target_url: str
    concurrent_users: int
    created_at: str
    duration: int


class CommonComparisonRequest(BaseModel):
    """Request model for common API performance comparison."""

    selected_tasks: List[str] = Field(
        ..., min_length=2, max_length=10, description="Task IDs to compare"
    )


class CommonComparisonMetrics(BaseModel):
    """Aggregated metrics for comparing common API tasks."""

    task_id: str
    task_name: str
    method: str
    target_url: str
    concurrent_users: int
    duration: str
    request_count: int
    failure_count: int
    success_rate: float
    rps: float
    avg_response_time: float
    p90_response_time: float
    min_response_time: float
    max_response_time: float
    avg_content_length: float


class CommonComparisonResponse(BaseModel):
    """Response model for common API comparison."""

    data: List[CommonComparisonMetrics]
    status: str
    error: Union[str, None]


class CommonComparisonTasksResponse(BaseModel):
    """Response model for available common tasks for comparison."""

    data: List[CommonComparisonTaskInfo]
    status: str
    error: Union[str, None]


# ---------- SQLAlchemy models ----------
class CommonTask(Base):
    """SQLAlchemy model for common API load test tasks."""

    __tablename__ = "common_tasks"

    id = Column(String(40), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    created_by = Column(String(100), nullable=True)
    method = Column(String(16), nullable=False)
    target_url = Column(String(2000), nullable=False)
    # Stored for engine routing (not exposed separately)
    target_host = Column(String(255), nullable=False)
    api_path = Column(String(1024), nullable=False)
    headers = Column(Text, nullable=True)
    cookies = Column(Text, nullable=True)
    request_body = Column(Text, nullable=True)
    dataset_file = Column(Text, nullable=True)
    curl_command = Column(Text, nullable=True)
    concurrent_users = Column(Integer, nullable=False)
    spawn_rate = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    log_file = Column(Text, nullable=True)
    result_file = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    is_deleted = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CommonTaskResult(Base):
    """SQLAlchemy model for common API task results."""

    __tablename__ = "common_task_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(40), nullable=False)
    metric_type = Column(String(64), nullable=False)
    num_requests = Column(Integer, nullable=False)
    num_failures = Column(Integer, nullable=False)
    avg_latency = Column(Float, nullable=False)
    min_latency = Column(Float, nullable=False)
    max_latency = Column(Float, nullable=False)
    median_latency = Column(Float, nullable=False)
    p90_latency = Column(Float, nullable=False)
    rps = Column(Float, nullable=False)
    avg_content_length = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_task_result_item(self) -> CommonTaskResultItem:
        """Convert SQLAlchemy model to response item."""
        return CommonTaskResultItem(
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
        )
