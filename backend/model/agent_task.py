"""Models for protocol-aware MCP and A2A load tests."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, func

from db.mysql import Base

_HTTP_HEADER_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class AgentHeader(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=4000)


class A2AScenario(BaseModel):
    """One weighted A2A request using the standard Message shape."""

    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    message: Dict[str, Any]
    weight: int = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def validate_message(self):
        role = self.message.get("role", "ROLE_USER")
        if role != "ROLE_USER":
            raise ValueError("A2A scenario message.role must be ROLE_USER")
        parts = self.message.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("A2A scenario message.parts must be a non-empty array")
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                raise ValueError(f"A2A message.parts[{index}] must be an object")
            content_fields = {"text", "data", "raw", "url"}.intersection(part)
            if len(content_fields) != 1:
                raise ValueError(
                    f"A2A message.parts[{index}] must contain exactly one of "
                    "text, data, raw, or url"
                )
        return self


class MCPToolCall(BaseModel):
    """One weighted standard MCP tools/call operation."""

    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    tool_name: str = Field(..., min_length=1, max_length=256)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    weight: int = Field(default=1, ge=1, le=100)


class A2ADatasetRow(BaseModel):
    """One dataset message bound to an A2A scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=200)
    scenario_id: str = Field(..., min_length=1, max_length=100)
    message: Dict[str, Any]

    @model_validator(mode="after")
    def validate_message(self):
        A2AScenario(
            id=self.scenario_id,
            name=self.scenario_id,
            message=self.message,
        )
        return self


class MCPDatasetRow(BaseModel):
    """One arguments row bound to a configured MCP tool-call scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=200)
    scenario_id: str = Field(..., min_length=1, max_length=100)
    arguments: Dict[str, Any] = Field(default_factory=dict)


class AgentTaskCreateReq(BaseModel):
    """Create a standards-based A2A or MCP load-test job."""

    name: str = Field(..., min_length=1, max_length=100)
    protocol: Literal["a2a", "mcp"]
    target_url: str = Field(..., min_length=1, max_length=2000)
    protocol_version: Optional[str] = Field(default=None, max_length=32)
    headers: List[AgentHeader] = Field(default_factory=list, max_length=50)
    duration: int = Field(default=60, ge=1, le=172800)
    concurrent_users: int = Field(default=1, ge=1, le=5000)
    spawn_rate: int = Field(default=1, ge=1, le=10000)
    request_timeout: float = Field(default=30.0, gt=0, le=3600)
    cluster_id: str = Field(default="local", min_length=1, max_length=64)
    dataset_file: Optional[str] = Field(default=None, max_length=2000)
    dataset_id: Optional[str] = Field(default=None, max_length=40)
    # Server-side copy context. Values from the source task are never sent to
    # the browser; these flags only authorize inheritance during create/test.
    copy_source_task_id: Optional[str] = Field(default=None, max_length=40)
    inherit_source_headers: bool = False
    inherit_source_dataset: bool = False

    # A2A protocol binding – determines transport and request format.
    a2a_binding: Literal["jsonrpc", "http_json", "grpc"] = "jsonrpc"

    # A2A execution mode.
    a2a_mode: Literal["sync", "stream", "async_poll"] = "async_poll"
    agent_card_url: Optional[str] = Field(default=None, max_length=2000)
    a2a_tenant: Optional[str] = Field(default=None, max_length=512)
    poll_interval: float = Field(default=1.0, ge=0.05, le=300)
    task_timeout: float = Field(default=300.0, gt=0, le=86400)
    a2a_scenarios: List[A2AScenario] = Field(default_factory=list)
    cascade_count_paths: List[str] = Field(default_factory=list, max_length=20)

    # MCP Streamable HTTP options (2026-07-28 default, legacy versions supported).
    mcp_calls: List[MCPToolCall] = Field(default_factory=list)
    token_count_path: Optional[str] = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_protocol_config(self):
        self.name = self.name.strip()
        self.target_url = self.target_url.strip()
        managed_headers = {
            "accept",
            "content-type",
            "a2a-version",
            "mcp-protocol-version",
            "mcp-method",
            "mcp-name",
            "mcp-session-id",
            "traceparent",
            "x-lmeterx-run-id",
            "x-lmeterx-request-id",
        }
        seen_headers = set()
        for header in self.headers:
            normalized = header.key.strip().lower()
            if not _HTTP_HEADER_TOKEN.fullmatch(header.key.strip()):
                raise ValueError(f"invalid HTTP request header name: {header.key!r}")
            if normalized in seen_headers:
                raise ValueError(f"duplicate request header: {header.key}")
            if normalized in managed_headers or normalized.startswith("mcp-param-"):
                raise ValueError(f"request header is managed by LMeterX: {header.key}")
            header.key = header.key.strip()
            seen_headers.add(normalized)
        if self.a2a_binding == "grpc":
            if self.target_url.startswith(("http://", "https://")):
                raise ValueError("gRPC target_url must be host:port, not an HTTP URL")
        elif not self.target_url.startswith(("http://", "https://")):
            raise ValueError("target_url must start with http:// or https://")
        if self.agent_card_url:
            self.agent_card_url = self.agent_card_url.strip()
            if not self.agent_card_url.startswith(("http://", "https://")):
                raise ValueError("agent_card_url must start with http:// or https://")
        if self.protocol == "a2a":
            self.protocol_version = self.protocol_version or "1.0"
            if self.protocol_version != "1.0":
                raise ValueError("only A2A protocol version 1.0 is supported")
            if not self.a2a_scenarios:
                raise ValueError("a2a_scenarios must contain at least one scenario")
        else:
            self.protocol_version = self.protocol_version or "2026-07-28"
            if self.protocol_version not in {"2025-11-25", "2026-07-28"}:
                raise ValueError(
                    "supported MCP protocol versions are 2025-11-25 and 2026-07-28"
                )
            if not self.mcp_calls:
                raise ValueError("mcp_calls must contain at least one tool call")
        scenarios = self.a2a_scenarios if self.protocol == "a2a" else self.mcp_calls
        scenario_ids = [item.id for item in scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("business scenario ids must be unique")
        if self.dataset_file and self.dataset_file.strip():
            self.dataset_file = self.dataset_file.strip()
            if not self.dataset_file.lower().endswith(".jsonl"):
                raise ValueError("agent protocol datasets must use the .jsonl format")
        else:
            self.dataset_file = None
        if self.copy_source_task_id:
            self.copy_source_task_id = self.copy_source_task_id.strip() or None
        if (self.inherit_source_headers or self.inherit_source_dataset) and not (
            self.copy_source_task_id
        ):
            raise ValueError(
                "copy_source_task_id is required when inheriting source data"
            )
        return self

    def config_json(self) -> str:
        return json.dumps(
            {
                "request_timeout": self.request_timeout,
                "dataset_file": self.dataset_file,
                "a2a_binding": self.a2a_binding,
                "a2a_mode": self.a2a_mode,
                "agent_card_url": self.agent_card_url,
                "a2a_tenant": self.a2a_tenant,
                "poll_interval": self.poll_interval,
                "task_timeout": self.task_timeout,
                "a2a_scenarios": [item.model_dump() for item in self.a2a_scenarios],
                "cascade_count_paths": self.cascade_count_paths,
                "mcp_calls": [item.model_dump() for item in self.mcp_calls],
                "token_count_path": self.token_count_path,
            },
            ensure_ascii=False,
        )


class AgentTask(Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_tasks_deleted_status", "is_deleted", "status"),
        Index("ix_agent_tasks_protocol_created", "protocol", "created_at"),
    )

    id = Column(String(40), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    created_by = Column(String(100), nullable=True)
    protocol = Column(String(16), nullable=False)
    protocol_version = Column(String(32), nullable=False)
    target_url = Column(String(2000), nullable=False)
    target_host = Column(String(255), nullable=False)
    api_path = Column(String(1024), nullable=False)
    headers = Column(Text, nullable=True)
    protocol_config = Column(Text, nullable=False)
    concurrent_users = Column(Integer, nullable=False)
    spawn_rate = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    error_message = Column(Text, nullable=True)
    engine_id = Column(String(64), nullable=True)
    cluster_id = Column(String(64), nullable=False, default="local")
    is_deleted = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentTaskResult(Base):
    __tablename__ = "agent_task_results"
    __table_args__ = (Index("ix_agent_results_task_metric", "task_id", "metric_type"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(40), nullable=False)
    metric_type = Column(String(128), nullable=False)
    num_requests = Column(Integer, nullable=False, default=0)
    num_failures = Column(Integer, nullable=False, default=0)
    avg_latency = Column(Float, nullable=False, default=0.0)
    min_latency = Column(Float, nullable=False, default=0.0)
    max_latency = Column(Float, nullable=False, default=0.0)
    median_latency = Column(Float, nullable=False, default=0.0)
    p95_latency = Column(Float, nullable=False, default=0.0)
    rps = Column(Float, nullable=False, default=0.0)
    avg_content_length = Column(Float, nullable=False, default=0.0)
    metric_data = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        try:
            details = json.loads(str(self.metric_data or "{}"))
        except (TypeError, json.JSONDecodeError):
            details = {}
        return {
            "id": self.id,
            "task_id": self.task_id,
            "metric_type": self.metric_type,
            "request_count": self.num_requests,
            "failure_count": self.num_failures,
            "avg_response_time": self.avg_latency,
            "min_response_time": self.min_latency,
            "max_response_time": self.max_latency,
            "median_response_time": self.median_latency,
            "percentile_95_response_time": self.p95_latency,
            "rps": self.rps,
            "avg_content_length": self.avg_content_length,
            "details": details,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class AgentComparisonTaskInfo(BaseModel):
    """Basic A2A/MCP task info used for comparison selection."""

    task_id: str
    task_name: str
    protocol: Literal["a2a", "mcp"]
    target_url: str
    concurrent_users: int
    created_at: str
    duration: int


class AgentComparisonRequest(BaseModel):
    """Request model for A2A/MCP performance comparison."""

    selected_tasks: List[str] = Field(
        ..., min_length=2, max_length=10, description="Task IDs to compare"
    )
    protocol: Literal["a2a", "mcp"]


class AgentLatencyMetric(BaseModel):
    """One named response-latency row that can be compared across tasks."""

    metric_name: str
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p95_response_time: float
    median_response_time: Optional[float] = None


class AgentComparisonMetrics(BaseModel):
    """Aggregated metrics for comparing A2A or MCP tasks."""

    task_id: str
    task_name: str
    protocol: Literal["a2a", "mcp"]
    target_url: str
    concurrent_users: int
    duration: str
    created_at: str
    throughput: float
    latency_metrics: List[AgentLatencyMetric] = Field(default_factory=list)


class AgentComparisonResponse(BaseModel):
    """Response model for A2A/MCP comparison."""

    data: List[AgentComparisonMetrics]
    status: str
    error: Union[str, None]


class AgentComparisonTasksResponse(BaseModel):
    """Response model for available A2A/MCP tasks for comparison."""

    data: List[AgentComparisonTaskInfo]
    status: str
    error: Union[str, None]


def percentile(values: List[float], quantile: float) -> float:
    """Linear percentile helper shared by protocol metric tests."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
