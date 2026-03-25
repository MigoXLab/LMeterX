"""
Pydantic schemas for the Skills API (web URL analysis → loadtest config).

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

# ─────────────────────────────────────────────────────────────────────────────
# Request / Response: POST /api/skills/analyze-url
# ─────────────────────────────────────────────────────────────────────────────


class AnalyzeUrlRequest(BaseModel):
    """Request body for the URL analysis endpoint."""

    target_url: str = Field(
        ..., max_length=2000, description="Target webpage URL to analyze"
    )
    cookies: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description='Browser cookies, e.g. [{"name":"token","value":"abc"}]',
    )
    headers: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description='Extra headers, e.g. [{"name":"Authorization","value":"Bearer x"}]',
    )
    wait_seconds: int = Field(
        default=5, ge=1, le=30, description="Seconds to wait after page load"
    )
    scroll: bool = Field(
        default=True, description="Scroll the page to trigger lazy-load APIs"
    )
    concurrent_users: int = Field(
        default=50, ge=1, le=5000, description="Default concurrent users"
    )
    duration: int = Field(
        default=300, ge=1, le=172800, description="Default duration in seconds"
    )
    spawn_rate: int = Field(
        default=30, ge=1, le=10000, description="Default user spawn rate per second"
    )

    @validator("target_url")
    def validate_url(cls, v: str) -> str:
        url = v.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("target_url must start with http:// or https://")
        return url


class DiscoveredApiItem(BaseModel):
    """A single API discovered from the webpage."""

    name: str = Field(..., description="Human-readable API name")
    target_url: str = Field(..., description="Full API endpoint URL")
    method: str = Field(..., description="HTTP method")
    headers: List[Dict[str, str]] = Field(
        default_factory=list, description="Headers to forward"
    )
    request_body: Optional[str] = Field(
        default=None, description="POST/PUT request body"
    )
    http_status: Optional[int] = Field(
        default=None, description="HTTP status observed during capture"
    )
    source: str = Field(
        default="playwright_xhr_fetch",
        description="Discovery source: playwright_xhr_fetch / js_static_scan",
    )
    confidence: str = Field(
        default="high",
        description="Confidence level of discovered API: high / medium / low",
    )


class LoadtestConfigItem(BaseModel):
    """
    A ready-to-use loadtest configuration for one API.
    Includes all fields required by POST /api/http-tasks.
    """

    temp_task_id: str = Field(..., description="Temporary task ID")
    name: str = Field(..., description="Task name")
    method: str = Field(..., description="HTTP method")
    target_url: str = Field(..., description="Full API endpoint URL")
    headers: List[Dict[str, str]] = Field(
        default_factory=list, description="[{key, value}]"
    )
    cookies: List[Dict[str, str]] = Field(default_factory=list)
    request_body: str = Field(default="", description="Request body")
    concurrent_users: int = Field(
        default=50, ge=1, le=5000, description="Concurrent users (1-5000)"
    )
    duration: int = Field(
        default=300, ge=1, le=172800, description="Duration in seconds (1-48h)"
    )
    spawn_rate: int = Field(
        default=30, ge=1, le=10000, description="Spawn rate per second (1-10000)"
    )
    load_mode: str = Field(default="fixed", description="Load mode: fixed/stepped")


class AnalyzeUrlResponse(BaseModel):
    """Response for the URL analysis endpoint."""

    status: str = Field(..., description="success / partial / error")
    message: str
    target_url: str = ""
    analysis_summary: str = ""
    discovered_apis: List[DiscoveredApiItem] = Field(default_factory=list)
    loadtest_configs: List[LoadtestConfigItem] = Field(default_factory=list)
    llm_used: bool = Field(
        default=False,
        description="Whether LLM was used to generate loadtest configs",
    )
