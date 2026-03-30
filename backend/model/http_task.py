"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import math
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from db.mysql import Base


# ---------- Pydantic schemas ----------
class HttpTaskPagination(BaseModel):
    """Pagination metadata for HTTP API tasks."""

    total: int = 0
    page: int = 0
    page_size: int = 0
    total_pages: int = 0


class HttpTaskCreateRsp(BaseModel):
    """Response payload when creating an HTTP API task."""

    task_id: str
    status: str
    message: str


class HttpTaskStatusRsp(BaseModel):
    """Lightweight status list response for HTTP API tasks."""

    data: List[Dict]
    timestamp: int
    status: str


class HttpHeaderItem(BaseModel):
    """Represents a single HTTP header."""

    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., max_length=2000)


class HttpTaskCreateReq(BaseModel):
    """Request payload for creating an HTTP API load test."""

    temp_task_id: str = Field(..., max_length=100, description="Temporary task ID")
    name: str = Field(..., min_length=1, max_length=100, description="Task name")
    method: str = Field(..., description="HTTP method, e.g. GET/POST/PUT/PATCH/DELETE")
    target_url: str = Field(..., max_length=2000, description="Full request URL")
    headers: List[HttpHeaderItem] = Field(default_factory=list)
    cookies: List[HttpHeaderItem] = Field(default_factory=list)
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
    success_assert: Optional[str] = Field(
        default=None,
        max_length=2000,
        description=(
            "Business-level success assertion rule (JSON). "
            "When set, response body will be checked against this rule. "
            'Example: {"field":"code","operator":"eq","value":0}'
        ),
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

    # -- Stepped load configuration --
    load_mode: str = Field(
        default="fixed",
        description="Load mode: 'fixed' for constant concurrency, 'stepped' for stepped load",
    )
    step_start_users: Optional[int] = Field(
        default=None,
        ge=1,
        le=5000,
        description="Initial number of users for stepped load",
    )
    step_increment: Optional[int] = Field(
        default=None, ge=1, le=1000, description="Users to add per step"
    )
    step_duration: Optional[int] = Field(
        default=None, ge=1, le=86400, description="Duration of each step in seconds"
    )
    step_max_users: Optional[int] = Field(
        default=None,
        ge=1,
        le=5000,
        description="Maximum number of users for stepped load",
    )
    step_sustain_duration: Optional[int] = Field(
        default=None,
        ge=1,
        le=172800,
        description="Duration to sustain at max users in seconds",
    )

    @validator("load_mode")
    def validate_load_mode(cls, v: str) -> str:
        if v not in ("fixed", "stepped"):
            raise ValueError("load_mode must be 'fixed' or 'stepped'")
        return v

    @validator("step_sustain_duration", always=True)
    def validate_stepped_config(cls, v, values):
        """Validate that all stepped fields are provided when load_mode is 'stepped'."""
        load_mode = values.get("load_mode", "fixed")
        if load_mode == "stepped":
            required_fields = {
                "step_start_users": values.get("step_start_users"),
                "step_increment": values.get("step_increment"),
                "step_duration": values.get("step_duration"),
                "step_max_users": values.get("step_max_users"),
            }
            missing = [k for k, val in required_fields.items() if val is None]
            if missing:
                raise ValueError(f"Stepped load mode requires: {', '.join(missing)}")
            if v is None:
                raise ValueError(
                    "step_sustain_duration is required for stepped load mode"
                )
            start = values.get("step_start_users", 0)
            max_u = values.get("step_max_users", 0)
            if start > max_u:
                raise ValueError(
                    "step_start_users cannot be greater than step_max_users"
                )
            # Validate computed total duration does not exceed 48 hours (172800s)
            increment = values.get("step_increment", 1) or 1
            step_dur = values.get("step_duration", 30) or 30
            num_steps = max(1, math.ceil((max_u - start) / max(increment, 1)))
            total_duration = num_steps * step_dur + v
            if total_duration > 172800:
                raise ValueError(
                    f"Stepped load total duration ({total_duration}s) exceeds "
                    f"maximum allowed 172800s (48h). Reduce step parameters."
                )
        return v

    @validator("success_assert")
    def validate_success_assert(cls, v: Optional[str]) -> Optional[str]:
        """Validate success_assert is valid JSON with required fields."""
        if v is None or v.strip() == "":
            return None
        import json as _json

        try:
            rule = _json.loads(v)
        except _json.JSONDecodeError:
            raise ValueError("success_assert must be valid JSON")
        if not isinstance(rule, dict):
            raise ValueError("success_assert must be a JSON object")
        if "field" not in rule or not rule["field"]:
            raise ValueError("success_assert requires a 'field' key")
        if "operator" not in rule:
            raise ValueError("success_assert requires an 'operator' key")
        valid_ops = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"}
        if rule["operator"] not in valid_ops:
            raise ValueError(
                f"success_assert operator must be one of: {', '.join(sorted(valid_ops))}"
            )
        if "value" not in rule:
            raise ValueError("success_assert requires a 'value' key")
        return v.strip()

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
    def validate_kv_items(cls, items: List[HttpHeaderItem]) -> List[HttpHeaderItem]:
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


class HttpTaskTestReq(BaseModel):
    """
    Request model for testing an HTTP API endpoint.
    Only includes fields actually needed for the test request,
    without requiring task metadata like name, duration, concurrent_users, etc.
    """

    method: str = Field(..., description="HTTP method, e.g. GET/POST/PUT/PATCH/DELETE")
    target_url: str = Field(..., max_length=2000, description="Full request URL")
    headers: List[HttpHeaderItem] = Field(default_factory=list)
    cookies: List[HttpHeaderItem] = Field(default_factory=list)
    request_body: Optional[str] = Field(
        default=None, max_length=100000, description="Request body (raw text/JSON)"
    )

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
    def validate_kv_items(cls, items: List[HttpHeaderItem]) -> List[HttpHeaderItem]:
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


class HttpTaskResultItem(BaseModel):
    """Represents a single metric row for HTTP API task results."""

    avg_content_length: float
    avg_response_time: float
    created_at: str
    failure_count: int
    id: int
    max_response_time: float
    median_response_time: float
    metric_type: str
    min_response_time: float
    percentile_95_response_time: float
    request_count: int
    rps: float
    task_id: str


class HttpTaskResultRsp(BaseModel):
    """Response model for HTTP API task performance results."""

    results: List[HttpTaskResultItem]
    status: str
    error: Union[str, None]


class HttpTaskResponse(BaseModel):
    """Paginated HTTP API task response."""

    data: List[Dict]
    pagination: HttpTaskPagination
    status: str


class HttpComparisonTaskInfo(BaseModel):
    """Basic HTTP task info used for comparison selection."""

    task_id: str
    task_name: str
    method: str
    target_url: str
    concurrent_users: int
    created_at: str
    duration: int


class HttpComparisonRequest(BaseModel):
    """Request model for HTTP API performance comparison."""

    selected_tasks: List[str] = Field(
        ..., min_length=2, max_length=10, description="Task IDs to compare"
    )


class HttpComparisonMetrics(BaseModel):
    """Aggregated metrics for comparing HTTP API tasks."""

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
    p95_response_time: float
    min_response_time: float
    max_response_time: float
    avg_content_length: float


class HttpComparisonResponse(BaseModel):
    """Response model for HTTP API comparison."""

    data: List[HttpComparisonMetrics]
    status: str
    error: Union[str, None]


class HttpComparisonTasksResponse(BaseModel):
    """Response model for available HTTP tasks for comparison."""

    data: List[HttpComparisonTaskInfo]
    status: str
    error: Union[str, None]


# ---------- SQLAlchemy models ----------
class HttpTask(Base):
    """SQLAlchemy model for HTTP API load test tasks."""

    __tablename__ = "http_tasks"

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
    success_assert = Column(Text, nullable=True)
    concurrent_users = Column(Integer, nullable=False)
    spawn_rate = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    # Stepped load configuration
    load_mode = Column(
        String(16), nullable=False, default="fixed", server_default="fixed"
    )
    step_start_users = Column(Integer, nullable=True)
    step_increment = Column(Integer, nullable=True)
    step_duration = Column(Integer, nullable=True)
    step_max_users = Column(Integer, nullable=True)
    step_sustain_duration = Column(Integer, nullable=True)
    log_file = Column(Text, nullable=True)
    result_file = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    engine_id = Column(String(64), nullable=True)
    is_deleted = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class HttpTaskResult(Base):
    """SQLAlchemy model for HTTP API task results."""

    __tablename__ = "http_task_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(40), nullable=False)
    metric_type = Column(String(64), nullable=False)
    num_requests = Column(Integer, nullable=False)
    num_failures = Column(Integer, nullable=False)
    avg_latency = Column(Float, nullable=False)
    min_latency = Column(Float, nullable=False)
    max_latency = Column(Float, nullable=False)
    median_latency = Column(Float, nullable=False)
    p95_latency = Column(Float, nullable=False)
    rps = Column(Float, nullable=False)
    avg_content_length = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_task_result_item(self) -> HttpTaskResultItem:
        """Convert SQLAlchemy model to response item."""
        return HttpTaskResultItem(
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
            percentile_95_response_time=(
                float(self.p95_latency) if self.p95_latency is not None else 0.0
            ),
            rps=float(self.rps) if self.rps is not None else 0.0,
            avg_content_length=(
                float(self.avg_content_length)
                if self.avg_content_length is not None
                else 0.0
            ),
            created_at=self.created_at.isoformat() if self.created_at else "",
        )
