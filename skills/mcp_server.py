"""
LMeterX MCP Server — Model Context Protocol server for AI agent integration.

Exposes three tools via JSON-RPC over stdio:
  - web_api_loadtest     : Analyze page → pre-check → create loadtest tasks
  - api_loadtest         : Direct API / curl → detect type → pre-check → create task
  - get_loadtest_results : Fetch task performance report (HTTP & LLM)

All heavy logic is delegated to the LMeterX backend via HTTP APIs:
  - POST /api/skills/analyze-url
  - POST /api/http-tasks/test     |  POST /api/llm-tasks/test
  - POST /api/http-tasks          |  POST /api/llm-tasks
  - GET  /api/http-tasks/{id}     |  GET  /api/llm-tasks/{id}
  - GET  /api/http-tasks/{id}/results | GET /api/llm-tasks/{id}/results

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import os
import re
import sys
import uuid
from urllib.parse import urlparse

import httpx

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("LMETERX_BASE_URL", "")
AUTH_TOKEN = os.getenv("LMETERX_AUTH_TOKEN", "")
TIMEOUT = 120.0

SERVER_NAME = "lmeterx-skills"
SERVER_VERSION = "3.1.0"

_MCP_CONFIG_HINT = (
    "\n\n💡 **修复方式** — 在 MCP 配置中设置环境变量：\n"
    "```json\n"
    "{\n"
    '  "mcpServers": {\n'
    '    "lmeterx": {\n'
    '      "command": "python",\n'
    '      "args": ["mcp_server.py"],\n'
    '      "env": {\n'
    '        "LMETERX_BASE_URL": "https://your-lmeterx-server.com",\n'
    '        "LMETERX_AUTH_TOKEN": "your-token-here"\n'
    "      }\n"
    "    }\n"
    "  }\n"
    "}\n"
    "```\n"
    "修改后需重启 MCP Server 生效。"
)

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_auth_token(raw_token: str) -> str:
    token = (raw_token or "").strip()
    if not token:
        return ""
    if token.lower().startswith("bearer "):
        bearer_payload = token[7:].strip()
        return f"Bearer {bearer_payload}" if bearer_payload else ""
    return f"Bearer {token}"


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    normalized = _normalize_auth_token(AUTH_TOKEN)
    if normalized:
        h["Authorization"] = normalized
        h["X-Authorization"] = normalized
    return h


def _bounded_int(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(v, hi))


def _api_prefix(task_type: str) -> str:
    """Return the API path prefix for the given task type."""
    return (
        f"{BASE_URL}/api/llm-tasks"
        if task_type == "llm"
        else f"{BASE_URL}/api/http-tasks"
    )


def _report_url(task_id: str, task_type: str) -> str:
    """Build the report page URL for a given task."""
    base = BASE_URL.rstrip("/")
    if task_type == "llm":
        return f"{base}/results/{task_id}"
    return f"{base}/common-results/{task_id}"


# ─────────────────────────────────────────────────────────────────────────────
# Preflight check & error classification
# ─────────────────────────────────────────────────────────────────────────────


def _preflight_check() -> str | None:
    """Verify backend reachability and auth validity before tool execution.

    Returns an error message string if something is wrong, or *None* if OK.
    """
    # 1. BASE_URL must be configured
    if not BASE_URL:
        return (
            "❌ **LMETERX_BASE_URL 未配置**\n\n"
            "MCP Server 启动时未检测到 `LMETERX_BASE_URL` 环境变量，"
            "无法连接 LMeterX 后端。" + _MCP_CONFIG_HINT
        )

    # 2. Health check
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=10.0, verify=False)
        if resp.status_code != 200:
            return (
                f"❌ **后端健康检查异常** — HTTP {resp.status_code}\n\n"
                f"已配置 `LMETERX_BASE_URL={BASE_URL}`，但健康检查未通过。\n"
                "请确认：\n"
                "1. 地址是否拼写正确（需含协议，如 `https://`）\n"
                "2. LMeterX 服务是否已启动\n"
                "3. 网络 / 防火墙是否放通" + _MCP_CONFIG_HINT
            )
    except httpx.ConnectError:
        return (
            f"❌ **无法连接 LMeterX 后端** — {BASE_URL}\n\n"
            "请确认：\n"
            "1. 地址是否正确\n"
            "2. LMeterX 服务是否已启动\n"
            "3. 网络 / 防火墙是否放通" + _MCP_CONFIG_HINT
        )
    except httpx.TimeoutException:
        return (
            f"❌ **连接 LMeterX 后端超时** — {BASE_URL}\n\n"
            "请确认后端服务是否正常运行。" + _MCP_CONFIG_HINT
        )
    except Exception as e:
        return f"❌ **连接后端失败** — {e}" + _MCP_CONFIG_HINT

    # 3. Auth check
    try:
        profile_resp = httpx.get(
            f"{BASE_URL}/api/auth/profile",
            headers=_headers(),
            timeout=10.0,
            verify=False,
        )
        if profile_resp.status_code == 401:
            if not AUTH_TOKEN:
                return (
                    "❌ **后端已启用认证，但未配置 LMETERX_AUTH_TOKEN**\n\n"
                    "该 LMeterX 实例需要登录认证，请在 MCP 配置的 `env` 中添加 "
                    "`LMETERX_AUTH_TOKEN`。\n\n"
                    "**获取 Token**：\n"
                    "```bash\n"
                    f"curl -X POST {BASE_URL}/api/auth/login \\\n"
                    "  -H 'Content-Type: application/json' \\\n"
                    '  -d \'{"username":"<用户名>","password":"<密码>"}\'\n'
                    "```\n"
                    "从返回 JSON 中复制 `access_token` 值。" + _MCP_CONFIG_HINT
                )
            else:
                return (
                    "❌ **LMETERX_AUTH_TOKEN 无效或已过期**\n\n"
                    "请重新获取 Token 并更新 MCP 配置。\n\n"
                    "**获取 Token**：\n"
                    "```bash\n"
                    f"curl -X POST {BASE_URL}/api/auth/login \\\n"
                    "  -H 'Content-Type: application/json' \\\n"
                    '  -d \'{"username":"<用户名>","password":"<密码>"}\'\n'
                    "```" + _MCP_CONFIG_HINT
                )
    except Exception:
        pass  # Non-auth errors don't block; warn and continue

    return None  # All checks passed


def _classify_http_error(e: Exception, context: str = "") -> str:
    """Return a user-friendly error message with MCP-specific guidance."""
    ctx = f"（{context}）" if context else ""

    if isinstance(e, httpx.ConnectError):
        return (
            f"❌ **连接 LMeterX 后端失败**{ctx}\n\n"
            f"当前 `LMETERX_BASE_URL={BASE_URL}`\n"
            "请确认地址正确且服务已启动。" + _MCP_CONFIG_HINT
        )
    if isinstance(e, httpx.TimeoutException):
        return (
            f"❌ **请求超时**{ctx}\n\n"
            f"后端 `{BASE_URL}` 未在规定时间内响应。\n"
            "可能是后端负载过高或网络问题。"
        )
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 401:
            return (
                f"❌ **认证失败 (HTTP 401)**{ctx}\n\n"
                "`LMETERX_AUTH_TOKEN` 无效、已过期或未配置。" + _MCP_CONFIG_HINT
            )
        if status == 403:
            return f"❌ **权限不足 (HTTP 403)**{ctx}\n\n当前账号无权执行此操作，请联系管理员。"
        if status == 404:
            return (
                f"❌ **接口不存在 (HTTP 404)**{ctx}\n\n"
                "可能 LMeterX 后端版本不匹配，请确认后端已更新。"
            )
        if status >= 500:
            return (
                f"❌ **后端服务异常 (HTTP {status})**{ctx}\n\n"
                "LMeterX 后端内部错误，请稍后重试或联系管理员。"
            )
        return f"❌ **请求失败 (HTTP {status})**{ctx}"

    return f"❌ **请求异常**{ctx} — {e}"


# ─────────────────────────────────────────────────────────────────────────────
# LLM API type detection (shared between api_loadtest tool)
# ─────────────────────────────────────────────────────────────────────────────

_LLM_PATTERNS = [
    ("/v1/chat/completions", "openai-chat", "/chat/completions"),
    ("/v1/messages", "claude-chat", "/messages"),
]


def _detect_llm_api(url: str):
    """Detect if URL points to a known LLM API.

    Returns (is_llm, api_type, target_host, api_path).
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    for suffix, api_type, api_path in _LLM_PATTERNS:
        if path.endswith(suffix):
            idx = path.rfind(suffix)
            prefix_path = path[:idx]
            target_host = f"{parsed.scheme}://{parsed.netloc}{prefix_path}"
            return True, api_type, target_host, api_path

    return False, "", "", ""


# ─────────────────────────────────────────────────────────────────────────────
# MCP tool definitions
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "web_api_loadtest",
        "description": (
            "网页压测技能：输入一个网页 URL，自动分析页面中的核心业务 API（通过 Playwright 拦截 XHR/Fetch），"
            "过滤静态资源和第三方埋点，对识别到的 API 做连通性预检，然后创建 LMeterX 压测任务。\n\n"
            '触发示例："帮我压测 https://example.com"、"对这个网站做性能测试"'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_url": {
                    "type": "string",
                    "description": "目标网页 URL，例如 https://example.com",
                },
                "concurrent_users": {
                    "type": "integer",
                    "description": "并发用户数（默认 50）",
                    "default": 50,
                },
                "duration": {
                    "type": "integer",
                    "description": "压测持续时间，单位秒（默认 300）",
                    "default": 300,
                },
                "spawn_rate": {
                    "type": "integer",
                    "description": "每秒产生用户速率（默认 30）",
                    "default": 30,
                },
            },
            "required": ["target_url"],
        },
    },
    {
        "name": "api_loadtest",
        "description": (
            "API 压测技能：给定一个 API URL 和请求参数，自动判断 API 类型"
            "（LLM API 或普通 HTTP API），预检连通性后创建压测任务。\n\n"
            "自动识别规则：URL 以 /v1/chat/completions 结尾 → OpenAI LLM API，"
            "以 /v1/messages 结尾 → Claude LLM API，其他 → 普通 HTTP API。\n\n"
            '触发示例："帮我压测这个 API"、"直接压测 API"'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "API 端点 URL，例如 https://api.openai.com/v1/chat/completions",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP 方法（默认 POST）",
                    "default": "POST",
                },
                "headers": {
                    "type": "object",
                    "description": '请求头字典，例如 {"Authorization": "Bearer sk-xxx"}',
                    "default": {},
                },
                "body": {
                    "type": "string",
                    "description": "请求体 JSON 字符串",
                    "default": "",
                },
                "cookies": {
                    "type": "object",
                    "description": "Cookie 字典",
                    "default": {},
                },
                "model": {
                    "type": "string",
                    "description": "模型名称（LLM API 专用，可从 body 自动提取）",
                    "default": "",
                },
                "stream_mode": {
                    "type": "boolean",
                    "description": "流式响应（LLM API 专用，默认 true）",
                    "default": True,
                },
                "concurrent_users": {
                    "type": "integer",
                    "description": "并发用户数（默认 50）",
                    "default": 50,
                },
                "duration": {
                    "type": "integer",
                    "description": "压测持续时间秒（默认 300）",
                    "default": 300,
                },
                "spawn_rate": {
                    "type": "integer",
                    "description": "每秒产生用户速率（默认 30）",
                    "default": 30,
                },
                "name": {
                    "type": "string",
                    "description": "任务名称（默认自动生成）",
                    "default": "",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_loadtest_results",
        "description": (
            "获取压测报告技能：输入 task_id，获取压测结果的结构化性能报告，"
            "包含 TPS/QPS、平均响应时间、P95 响应时间、错误率等核心指标，"
            "以及性能评级和优化建议。\n\n"
            '触发示例："获取任务 abc-123 的压测结果"、"查看压测报告"'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "压测任务 ID",
                },
                "task_type": {
                    "type": "string",
                    "description": "任务类型：'common'（普通 HTTP，默认）或 'llm'（LLM API）",
                    "default": "common",
                    "enum": ["common", "llm"],
                },
            },
            "required": ["task_id"],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────────────────────


def _handle_web_api_loadtest(args: dict) -> list:
    """Execute the web_api_loadtest tool by calling backend APIs."""
    # ── Preflight ────────────────────────────────────────────────────────
    err = _preflight_check()
    if err:
        return [{"type": "text", "text": err}]

    target_url = args.get("target_url", "")
    concurrent_users = args.get("concurrent_users", 50)
    duration = args.get("duration", 300)
    spawn_rate = args.get("spawn_rate", 30)

    if not target_url:
        return [{"type": "text", "text": "❌ target_url is required"}]

    parts: list[str] = []

    with httpx.Client(timeout=TIMEOUT, verify=False) as client:
        # Step 1: Analyze URL
        parts.append(f"🔍 Analyzing page: {target_url} ...")
        try:
            analyze_resp = client.post(
                f"{BASE_URL}/api/skills/analyze-url",
                headers=_headers(),
                json={
                    "target_url": target_url,
                    "concurrent_users": concurrent_users,
                    "duration": duration,
                    "spawn_rate": spawn_rate,
                },
            )
            analyze_resp.raise_for_status()
            analyze_data = analyze_resp.json()
        except Exception as e:
            return [{"type": "text", "text": _classify_http_error(e, "页面分析")}]

        if analyze_data.get("status") != "success":
            return [
                {
                    "type": "text",
                    "text": f"❌ Analysis failed: {analyze_data.get('message', 'Unknown error')}",
                }
            ]

        configs = analyze_data.get("loadtest_configs", [])
        summary = analyze_data.get("analysis_summary", "")
        llm_used = analyze_data.get("llm_used", False)

        parts.append(f"📊 Analysis summary: {summary}")
        if llm_used:
            parts.append("💡 AI-generated loadtest configs used")

        if not configs:
            parts.append("⚠️ No APIs found for testing")
            return [{"type": "text", "text": "\n".join(parts)}]

        # Step 2: Pre-check
        parts.append(f"\n🔗 Pre-checking {len(configs)} APIs for connectivity ...")
        passing = []
        for cfg in configs:
            name = cfg.get("name", cfg.get("target_url", ""))
            try:
                test_resp = client.post(
                    f"{BASE_URL}/api/http-tasks/test",
                    headers=_headers(),
                    json={
                        "method": cfg["method"],
                        "target_url": cfg["target_url"],
                        "headers": [
                            {"key": h.get("key", ""), "value": h.get("value", "")}
                            for h in cfg.get("headers", [])
                        ],
                        "cookies": [
                            {"key": c.get("key", ""), "value": c.get("value", "")}
                            for c in cfg.get("cookies", [])
                        ],
                        "request_body": cfg.get("request_body", ""),
                    },
                )
                test_resp.raise_for_status()
                test_data = test_resp.json()
                if test_data.get("status") == "success":
                    parts.append(
                        f"  ✅ {name} → HTTP {test_data.get('http_status', '?')}"
                    )
                    passing.append(cfg)
                else:
                    parts.append(f"  ❌ {name} → {test_data.get('error', 'Failed')}")
            except Exception as e:
                parts.append(f"  ❌ {name} → {_classify_http_error(e)}")

        if not passing:
            parts.append("\n❌ All API pre-checks failed, cannot create loadtest tasks")
            return [{"type": "text", "text": "\n".join(parts)}]

        # Step 3: Create tasks
        parts.append(f"\n🚀 Creating {len(passing)} loadtest tasks ...")
        created_ids = []
        for cfg in passing:
            try:
                create_resp = client.post(
                    f"{BASE_URL}/api/http-tasks",
                    headers=_headers(),
                    json={
                        "temp_task_id": cfg["temp_task_id"],
                        "name": cfg["name"],
                        "method": cfg["method"],
                        "target_url": cfg["target_url"],
                        "headers": [
                            {"key": h.get("key", ""), "value": h.get("value", "")}
                            for h in cfg.get("headers", [])
                        ],
                        "cookies": [
                            {"key": c.get("key", ""), "value": c.get("value", "")}
                            for c in cfg.get("cookies", [])
                        ],
                        "request_body": cfg.get("request_body", ""),
                        "concurrent_users": cfg.get("concurrent_users", 50),
                        "duration": cfg.get("duration", 300),
                        "spawn_rate": cfg.get("spawn_rate", 30),
                        "load_mode": cfg.get("load_mode", "fixed"),
                    },
                )
                create_resp.raise_for_status()
                task_id = create_resp.json().get("task_id", "")
                parts.append(f"  ✅ {cfg['name']} → task_id: {task_id}")
                created_ids.append(task_id)
            except Exception as e:
                parts.append(
                    f"  ❌ {cfg['name']} → {_classify_http_error(e, '创建任务')}"
                )

        # Summary
        parts.append(f"\n{'='*50}")
        parts.append(
            f"📋 Summary: Found {len(configs)} APIs, pre-checked {len(passing)} passed, created {len(created_ids)} tasks"
        )
        if created_ids:
            parts.append(f"📌 Task IDs: {', '.join(created_ids)}")
            for tid in created_ids:
                parts.append(f"📊 Report: {_report_url(tid, 'common')}")
            parts.append("💡 Use get_loadtest_results tool to view detailed metrics")

    return [{"type": "text", "text": "\n".join(parts)}]


def _handle_api_loadtest(args: dict) -> list:
    """Execute the api_loadtest tool — direct API load testing."""
    # ── Preflight ────────────────────────────────────────────────────────
    err = _preflight_check()
    if err:
        return [{"type": "text", "text": err}]

    url = args.get("url", "")
    if not url:
        return [{"type": "text", "text": "❌ url is required"}]

    method = args.get("method", "POST").upper()
    hdr_dict = args.get("headers", {})
    body = args.get("body", "")
    cookie_dict = args.get("cookies", {})
    concurrent_users = _bounded_int(args.get("concurrent_users", 50), 50, 1, 5000)
    duration = _bounded_int(args.get("duration", 300), 300, 1, 172800)
    spawn_rate = _bounded_int(args.get("spawn_rate", 30), 30, 1, 10000)
    task_name = args.get("name", "")

    # Auto-generate task name
    if not task_name:
        parsed = urlparse(url)
        task_name = f"{parsed.netloc}{parsed.path}"[:80]

    # Detect API type
    is_llm, api_type, target_host, api_path = _detect_llm_api(url)

    parts: list[str] = []
    type_label = "🤖 LLM API" if is_llm else "🌐 HTTP API"
    parts.append(f"🔍 API type: {type_label}")

    # Build KV lists
    header_list = [
        {"key": k, "value": v}
        for k, v in hdr_dict.items()
        if k.lower() != "content-type"
    ]
    cookie_list = [{"key": k, "value": v} for k, v in cookie_dict.items()]

    temp_task_id = f"mcp_{uuid.uuid4().hex[:8]}"

    with httpx.Client(timeout=TIMEOUT, verify=False) as client:
        if is_llm:
            # ── LLM API flow ──
            # Resolve model from args or body
            model = args.get("model", "")
            if not model and body:
                try:
                    model = json.loads(body).get("model", "")
                except (json.JSONDecodeError, AttributeError):
                    pass

            stream_mode = args.get("stream_mode", True)

            parts.append(f"   Target: {target_host}")
            parts.append(f"   Path:   {api_path}")
            parts.append(f"   Model:  {model or '(auto)'}")
            parts.append(f"   Stream: {stream_mode}")

            # Step 1: Pre-check
            parts.append("\n🔗 Pre-checking connectivity ...")
            try:
                test_resp = client.post(
                    f"{BASE_URL}/api/llm-tasks/test",
                    headers=_headers(),
                    json={
                        "target_host": target_host,
                        "api_path": api_path,
                        "model": model,
                        "stream_mode": stream_mode,
                        "headers": header_list,
                        "cookies": cookie_list,
                        "request_payload": body,
                        "api_type": api_type,
                    },
                )
                if test_resp.status_code != 200:
                    parts.append(f"❌ Pre-check failed: HTTP {test_resp.status_code}")
                    return [{"type": "text", "text": "\n".join(parts)}]
                test_data = test_resp.json()
                if test_data.get("status") != "success":
                    parts.append(
                        f"❌ Pre-check failed: {test_data.get('error', 'N/A')}"
                    )
                    return [{"type": "text", "text": "\n".join(parts)}]
                parts.append(
                    f"  ✅ Connected → HTTP {test_data.get('http_status', '?')}"
                )
            except Exception as e:
                parts.append(_classify_http_error(e, "LLM API 预检"))
                return [{"type": "text", "text": "\n".join(parts)}]

            # Step 2: Create task
            parts.append("\n🚀 Creating LLM loadtest task ...")
            try:
                create_resp = client.post(
                    f"{BASE_URL}/api/llm-tasks",
                    headers=_headers(),
                    json={
                        "temp_task_id": temp_task_id,
                        "name": task_name,
                        "target_host": target_host,
                        "api_path": api_path,
                        "model": model,
                        "duration": duration,
                        "concurrent_users": concurrent_users,
                        "spawn_rate": spawn_rate,
                        "stream_mode": stream_mode,
                        "headers": header_list,
                        "cookies": cookie_list,
                        "request_payload": body,
                        "api_type": api_type,
                        "chat_type": 0,
                        "warmup_enabled": True,
                        "warmup_duration": 120,
                        "load_mode": "fixed",
                    },
                )
                create_resp.raise_for_status()
                task_id = create_resp.json().get("task_id", "")
                parts.append(f"  ✅ Task created → task_id: {task_id}")
                parts.append(f"📊 Report: {_report_url(task_id, 'llm')}")
                parts.append(
                    "💡 Use get_loadtest_results with task_type='llm' to view metrics"
                )
            except Exception as e:
                parts.append(_classify_http_error(e, "创建 LLM 任务"))

        else:
            # ── Common HTTP API flow ──
            parts.append(f"   Method: {method}")
            parts.append(f"   URL:    {url}")

            # Step 1: Pre-check
            parts.append("\n🔗 Pre-checking connectivity ...")
            try:
                test_resp = client.post(
                    f"{BASE_URL}/api/http-tasks/test",
                    headers=_headers(),
                    json={
                        "method": method,
                        "target_url": url,
                        "headers": header_list,
                        "cookies": cookie_list,
                        "request_body": body,
                    },
                )
                if test_resp.status_code != 200:
                    parts.append(f"❌ Pre-check failed: HTTP {test_resp.status_code}")
                    return [{"type": "text", "text": "\n".join(parts)}]
                test_data = test_resp.json()
                if test_data.get("status") != "success":
                    parts.append(
                        f"❌ Pre-check failed: {test_data.get('error', 'N/A')}"
                    )
                    return [{"type": "text", "text": "\n".join(parts)}]
                parts.append(
                    f"  ✅ Connected → HTTP {test_data.get('http_status', '?')}"
                )
            except Exception as e:
                parts.append(_classify_http_error(e, "HTTP API 预检"))
                return [{"type": "text", "text": "\n".join(parts)}]

            # Step 2: Create task
            parts.append("\n🚀 Creating HTTP loadtest task ...")
            try:
                create_resp = client.post(
                    f"{BASE_URL}/api/http-tasks",
                    headers=_headers(),
                    json={
                        "temp_task_id": temp_task_id,
                        "name": task_name,
                        "method": method,
                        "target_url": url,
                        "headers": header_list,
                        "cookies": cookie_list,
                        "request_body": body,
                        "concurrent_users": concurrent_users,
                        "duration": duration,
                        "spawn_rate": spawn_rate,
                        "load_mode": "fixed",
                    },
                )
                create_resp.raise_for_status()
                task_id = create_resp.json().get("task_id", "")
                parts.append(f"  ✅ Task created → task_id: {task_id}")
                parts.append(f"📊 Report: {_report_url(task_id, 'common')}")
                parts.append(
                    "💡 Use get_loadtest_results tool to view detailed metrics"
                )
            except Exception as e:
                parts.append(_classify_http_error(e, "创建 HTTP 任务"))

    return [{"type": "text", "text": "\n".join(parts)}]


def _handle_get_loadtest_results(args: dict) -> list:
    """Execute the get_loadtest_results tool by calling backend APIs."""
    # ── Preflight ────────────────────────────────────────────────────────
    err = _preflight_check()
    if err:
        return [{"type": "text", "text": err}]

    task_id = args.get("task_id", "")
    task_type = args.get("task_type", "common")
    if not task_id:
        return [{"type": "text", "text": "❌ Task ID is required"}]

    prefix = _api_prefix(task_type)

    with httpx.Client(timeout=30.0, verify=False) as client:
        # Get task detail
        try:
            detail_resp = client.get(f"{prefix}/{task_id}", headers=_headers())
            detail_resp.raise_for_status()
            detail = detail_resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                type_hint = "LLM" if task_type == "llm" else "HTTP"
                other = "llm" if task_type == "common" else "common"
                return [
                    {
                        "type": "text",
                        "text": (
                            f"❌ **任务不存在** — task_id `{task_id}` 在 {type_hint} 任务中未找到。\n\n"
                            f"💡 请确认：\n"
                            f"1. task_id 是否正确\n"
                            f"2. 任务类型是否匹配（当前 task_type=`{task_type}`，"
                            f"可尝试 task_type=`{other}`）"
                        ),
                    }
                ]
            return [{"type": "text", "text": _classify_http_error(e, "获取任务详情")}]
        except Exception as e:
            return [{"type": "text", "text": _classify_http_error(e, "获取任务详情")}]

        # Get results
        try:
            results_resp = client.get(f"{prefix}/{task_id}/results", headers=_headers())
            results_resp.raise_for_status()
            results_data = results_resp.json()
        except Exception as e:
            return [{"type": "text", "text": _classify_http_error(e, "获取压测结果")}]

        results = results_data.get("results", [])
        if not results:
            status = detail.get("status", "unknown")
            report = _report_url(task_id, task_type)
            return [
                {
                    "type": "text",
                    "text": f"⚠️ 暂无结果（任务状态: {status}）\n📊 报告地址: {report}",
                }
            ]

        # Find total row
        total = None
        for r in results:
            if r.get("metric_type", "").lower() == "total":
                total = r
                break
        if not total:
            total = results[-1]

        req_count = total.get("request_count", 0)
        fail_count = total.get("failure_count", 0)
        rps = total.get("rps", 0.0)
        avg_rt = total.get("avg_response_time", 0.0)
        p95 = total.get("percentile_95_response_time", 0.0)
        min_rt = total.get("min_response_time", 0.0)
        max_rt = total.get("max_response_time", 0.0)
        median = total.get("median_response_time", 0.0)
        err_rate = (fail_count / req_count * 100) if req_count > 0 else 0.0

        # Assessment
        assessments = []
        if rps >= 100:
            assessments.append(f"🟢 TPS: {rps:.2f} (良好)")
        elif rps >= 10:
            assessments.append(f"🟡 TPS: {rps:.2f} (一般)")
        else:
            assessments.append(f"🔴 TPS: {rps:.2f} (偏低)")

        if avg_rt <= 200:
            assessments.append(f"🟢 平均响应: {avg_rt:.0f}ms")
        elif avg_rt <= 1000:
            assessments.append(f"🟡 平均响应: {avg_rt:.0f}ms")
        else:
            assessments.append(f"🔴 平均响应: {avg_rt:.0f}ms")

        if err_rate == 0:
            assessments.append("🟢 错误率: 0%")
        elif err_rate < 1:
            assessments.append(f"🟡 错误率: {err_rate:.2f}%")
        else:
            assessments.append(f"🔴 错误率: {err_rate:.2f}%")

        # Build target info based on task type
        if task_type == "llm":
            target_info = (
                f"{detail.get('target_host', 'N/A')}{detail.get('api_path', '')}"
            )
        else:
            target_info = detail.get("target_url", "N/A")

        report = f"""## LMeterX 压测报告

**任务**: {detail.get('name', 'N/A')} (`{task_id}`)
**URL**: {target_info}
**并发**: {detail.get('concurrent_users', 'N/A')} 用户 | **时长**: {detail.get('duration', 'N/A')}s | **状态**: {detail.get('status', 'N/A')}
**报告地址**: {_report_url(task_id, task_type)}

### 核心指标
| 指标 | 值 |
|------|------|
| 总请求数 | {req_count:,} |
| 失败请求 | {fail_count:,} |
| 错误率 | {err_rate:.2f}% |
| TPS/QPS | {rps:.2f} |
| 平均响应 | {avg_rt:.2f}ms |
| 中位数 | {median:.2f}ms |
| P95 | {p95:.2f}ms |
| 最小/最大 | {min_rt:.2f}ms / {max_rt:.2f}ms |

### 评级
{chr(10).join(assessments)}"""

        return [{"type": "text", "text": report}]


# ─────────────────────────────────────────────────────────────────────────────
# JSON-RPC / MCP protocol handler
# ─────────────────────────────────────────────────────────────────────────────

_TOOL_HANDLERS = {
    "web_api_loadtest": _handle_web_api_loadtest,
    "api_loadtest": _handle_api_loadtest,
    "get_loadtest_results": _handle_get_loadtest_results,
}


def _jsonrpc_response(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _jsonrpc_error(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _handle_request(req: dict) -> dict | None:
    method = req.get("method", "")
    id_ = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return _jsonrpc_response(
            id_,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _jsonrpc_response(id_, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = _TOOL_HANDLERS.get(tool_name)
        if not handler:
            return _jsonrpc_error(id_, -32601, f"Unknown tool: {tool_name}")

        content = handler(arguments)
        return _jsonrpc_response(id_, {"content": content, "isError": False})

    return _jsonrpc_error(id_, -32601, f"Method not found: {method}")


def main():
    """Run MCP server on stdio (JSON-RPC)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = _handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            err = _jsonrpc_error(None, -32700, "Parse error")
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err = _jsonrpc_error(None, -32603, str(e))
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
