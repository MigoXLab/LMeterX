"""
API routes for Skills integration.

Exposes three key endpoints for external agent skills:
  1. POST /api/skills/analyze-url   — Analyze a webpage and generate loadtest configs
  2. POST /api/common-tasks/test    — Test API connectivity (already exists)
  3. POST /api/common-tasks         — Create load test task (already exists)

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

from fastapi import APIRouter, Request

from model.skill import AnalyzeUrlRequest, AnalyzeUrlResponse
from service.skill_service import analyze_url_svc

router = APIRouter()


@router.post("/analyze-url", response_model=AnalyzeUrlResponse)
async def analyze_url(request: Request, body: AnalyzeUrlRequest):
    """
    Analyze a target webpage URL: discover core business APIs via Playwright,
    and generate ready-to-use loadtest configurations.

    If the system has an AI service configured, uses LLM for smart config
    generation (adjusting concurrency/duration per API semantics).
    Otherwise, assigns fixed defaults (50 users, 300s).

    The returned ``loadtest_configs`` can be directly submitted to
    ``POST /api/common-tasks`` one by one to create loadtest tasks.
    """
    return await analyze_url_svc(request, body)
