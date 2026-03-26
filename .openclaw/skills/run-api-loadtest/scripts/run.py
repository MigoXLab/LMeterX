#!/usr/bin/env python3
"""
run-api-loadtest skill — thin client for LMeterX backend.

Workflow:
  1. Parse input (curl command or --url/--method/--body/--header params)
  2. Detect API type:
     - /v1/chat/completions  → LLM API (OpenAI)
     - /v1/messages          → LLM API (Claude)
     - Other                 → Regular HTTP API
  3. Pre-check connectivity via /api/llm-tasks/test or /api/http-tasks/test
  4. Create loadtest task via /api/llm-tasks or /api/http-tasks

All heavy lifting lives on the backend; this script only calls APIs.
"""

import argparse
import json
import re
import shlex
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

# ── shared lib ──────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _lib.client import BASE_URL  # noqa: E402
from _lib.client import bounded_int  # noqa: E402
from _lib.client import (
    ARTIFACT_ROOT,
    classify_precheck_failure,
    headers,
    preflight_check,
)

TIMEOUT = 60.0

# ── LLM path patterns ──────────────────────────────────────────────────────

LLM_PATTERNS: List[Tuple[str, str]] = [
    ("/v1/chat/completions", "openai-chat"),
    ("/v1/messages", "claude-chat"),
]


# ── curl parser ─────────────────────────────────────────────────────────────


def _parse_curl(curl_cmd: str) -> Dict[str, Any]:
    """
    Parse a curl command string into structured components.

    Returns dict with keys: url, method, headers, body, cookies.
    """
    # Normalize: remove line continuations and collapse whitespace
    cmd = curl_cmd.replace("\\\n", " ").replace("\\\r\n", " ").strip()

    # Strip leading "curl" keyword
    if re.match(r"^curl\s", cmd, re.IGNORECASE):
        cmd = re.sub(r"^curl\s+", "", cmd, count=1, flags=re.IGNORECASE)

    try:
        tokens = shlex.split(cmd)
    except ValueError:
        # Fallback for unmatched quotes
        tokens = cmd.split()

    url = ""
    method = ""
    req_headers: Dict[str, str] = {}
    body = ""
    cookies: Dict[str, str] = {}

    # Flags to skip
    SKIP_FLAGS_WITH_ARG = {
        "--connect-timeout",
        "--max-time",
        "-m",
        "--retry",
        "-o",
        "--output",
        "-u",
        "--user",
        "-e",
        "--referer",
        "-A",
        "--user-agent",
        "--proxy",
        "-x",
        "--cert",
        "--key",
        "--cacert",
    }
    SKIP_FLAGS_NO_ARG = {
        "--compressed",
        "--insecure",
        "-k",
        "-v",
        "--verbose",
        "-s",
        "--silent",
        "-S",
        "--show-error",
        "-L",
        "--location",
        "-i",
        "--include",
        "-f",
        "--fail",
        "-N",
        "--no-buffer",
    }

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok in ("-X", "--request"):
            i += 1
            if i < len(tokens):
                method = tokens[i].upper()

        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                hdr = tokens[i]
                if ":" in hdr:
                    key, val = hdr.split(":", 1)
                    req_headers[key.strip()] = val.strip()

        elif tok in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
            i += 1
            if i < len(tokens):
                body = tokens[i]

        elif tok in ("-b", "--cookie"):
            i += 1
            if i < len(tokens):
                for part in tokens[i].split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

        elif tok in SKIP_FLAGS_NO_ARG:
            pass  # ignore

        elif tok in SKIP_FLAGS_WITH_ARG:
            i += 1  # skip next token too

        elif tok.startswith("http://") or tok.startswith("https://"):
            url = tok

        elif not tok.startswith("-") and not url:
            # Might be URL without quotes
            if "://" in tok or tok.startswith("http"):
                url = tok

        i += 1

    # Auto-detect method
    if not method:
        method = "POST" if body else "GET"

    return {
        "url": url,
        "method": method,
        "headers": req_headers,
        "body": body,
        "cookies": cookies,
    }


# ── API type detection ──────────────────────────────────────────────────────


def _detect_api_type(url: str) -> Tuple[bool, str]:
    """
    Detect if URL points to a known LLM API.

    Returns (is_llm, api_type).
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    for pattern, api_type in LLM_PATTERNS:
        if path.endswith(pattern):
            return True, api_type

    return False, ""


def _split_llm_url(url: str, api_type: str) -> Tuple[str, str]:
    """
    Split LLM URL into (target_host, api_path).

    Examples:
      https://api.openai.com/v1/chat/completions
        → ("https://api.openai.com/v1", "/chat/completions")
      https://api.anthropic.com/v1/messages
        → ("https://api.anthropic.com/v1", "/messages")
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    if api_type == "openai-chat":
        suffix = "/chat/completions"
    elif api_type == "claude-chat":
        suffix = "/messages"
    else:
        # Fallback: use the whole path
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base, path or "/"

    idx = path.rfind(suffix)
    if idx >= 0:
        prefix_path = path[:idx]
        target_host = f"{parsed.scheme}://{parsed.netloc}{prefix_path}"
        return target_host, suffix
    else:
        # Should not happen if _detect_api_type matched
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base, path or "/"


# ── helpers ─────────────────────────────────────────────────────────────────


def _print_section(label: str, data: Any = None) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    if data is not None:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def _headers_to_kv_list(hdr_dict: Dict[str, str]) -> List[Dict[str, str]]:
    """Convert {key: value} dict into [{key: ..., value: ...}] list."""
    return [{"key": k, "value": v} for k, v in hdr_dict.items()]


def _cookies_to_kv_list(cookie_dict: Dict[str, str]) -> List[Dict[str, str]]:
    """Convert {key: value} dict into [{key: ..., value: ...}] list."""
    return [{"key": k, "value": v} for k, v in cookie_dict.items()]


def _extract_model_from_body(body: str) -> str:
    """Try to extract model name from JSON body."""
    if not body:
        return ""
    try:
        data = json.loads(body)
        return data.get("model", "")
    except (json.JSONDecodeError, AttributeError):
        return ""


def _extract_stream_from_body(body: str) -> Optional[bool]:
    """Try to extract stream flag from JSON body."""
    if not body:
        return None
    try:
        data = json.loads(body)
        val = data.get("stream")
        if isinstance(val, bool):
            return val
        return None
    except (json.JSONDecodeError, AttributeError):
        return None


def _persist_batch(
    batch_id: str,
    source_info: str,
    task_type: str,
    tasks: list,
) -> Path:
    """Save a batch manifest JSON for later use by fetch-loadtest-results."""
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_ROOT / f"{batch_id}.json"
    path.write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "source_info": source_info,
                "task_type": task_type,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "tasks": tasks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


# ── LLM API flow ───────────────────────────────────────────────────────────


def _run_llm_flow(
    client: httpx.Client,
    url: str,
    api_type: str,
    model: str,
    stream_mode: bool,
    req_headers: Dict[str, str],
    cookies: Dict[str, str],
    body: str,
    concurrent_users: int,
    duration: int,
    spawn_rate: int,
    task_name: str,
) -> Optional[Dict]:
    """
    LLM API flow:
      1. POST /api/llm-tasks/test  → connectivity check
      2. POST /api/llm-tasks       → create loadtest task
    """
    target_host, api_path = _split_llm_url(url, api_type)

    # Filter out Content-Type from headers (backend adds it)
    filtered_headers = {
        k: v for k, v in req_headers.items() if k.lower() != "content-type"
    }

    api_type_label = "OpenAI Chat" if api_type == "openai-chat" else "Claude Chat"
    print(f"   API 类型: {api_type_label}")
    print(f"   目标主机: {target_host}")
    print(f"   API 路径: {api_path}")
    print(f"   模型:     {model or '(auto)'}")
    print(f"   流式:     {stream_mode}")

    # ── Step 1: Pre-check ──────────────────────────────────────────────────
    print(f"\n🔗 Step 1/2: 预检 API 连通性 ...")

    test_payload = {
        "target_host": target_host,
        "api_path": api_path,
        "model": model,
        "stream_mode": stream_mode,
        "headers": _headers_to_kv_list(filtered_headers),
        "cookies": _cookies_to_kv_list(cookies),
        "request_payload": body or "",
        "api_type": api_type,
    }

    try:
        test_resp = client.post(
            f"{BASE_URL}/api/llm-tasks/test",
            headers=headers(),
            json=test_payload,
        )

        if test_resp.status_code != 200:
            print(f"\n❌ 连通性测试失败: HTTP {test_resp.status_code}")
            try:
                err_data = test_resp.json()
                print(f"   详情: {json.dumps(err_data, ensure_ascii=False)}")
            except Exception:
                print(f"   响应: {test_resp.text[:500]}")
            return None

        test_data = test_resp.json()
        if test_data.get("status") == "success":
            http_code = test_data.get("http_status")
            if isinstance(http_code, int) and http_code >= 400:
                cat_key, label, hint = classify_precheck_failure(http_status=http_code)
                print(f"\n❌ 连通性测试未通过: {label}")
                print(f"   HTTP 状态码: {http_code}")
                if hint:
                    print(f"   💡 {hint}")
                return None
            print(f"   ✅ 连通性正常 → HTTP {http_code or '?'}")
        elif test_data.get("status") != "success":
            error = test_data.get("error", "N/A")
            cat_key, label, hint = classify_precheck_failure(error_msg=error)
            print(f"\n❌ 连通性测试未通过: {label}")
            print(f"   错误: {error}")
            if hint:
                print(f"   💡 {hint}")
            return None

    except Exception as e:
        cat_key, label, hint = classify_precheck_failure(error_msg=str(e))
        print(f"\n❌ 连通性测试异常: {label}")
        print(f"   详情: {e}")
        if hint:
            print(f"   💡 {hint}")
        return None

    # ── Step 2: Create task ────────────────────────────────────────────────
    print(f"\n🚀 Step 2/2: 创建 LLM 压测任务 ...")

    temp_task_id = f"direct_{uuid.uuid4().hex[:8]}"
    create_payload = {
        "temp_task_id": temp_task_id,
        "name": task_name,
        "target_host": target_host,
        "api_path": api_path,
        "model": model,
        "duration": duration,
        "concurrent_users": concurrent_users,
        "spawn_rate": spawn_rate,
        "stream_mode": stream_mode,
        "headers": _headers_to_kv_list(filtered_headers),
        "cookies": _cookies_to_kv_list(cookies),
        "request_payload": body or "",
        "api_type": api_type,
        "chat_type": 0,
        "warmup_enabled": True,
        "warmup_duration": 120,
        "load_mode": "fixed",
    }

    try:
        create_resp = client.post(
            f"{BASE_URL}/api/llm-tasks",
            headers=headers(),
            json=create_payload,
        )
        create_resp.raise_for_status()
        result = create_resp.json()
        task_id = result.get("task_id", "")
        print(f"   ✅ 任务创建成功 → task_id={task_id}")
        return {
            "task_id": task_id,
            "name": task_name,
            "target_url": url,
            "method": "POST",
            "duration": duration,
        }
    except Exception as e:
        print(f"   ❌ 任务创建失败: {e}")
        return None


# ── Common HTTP API flow ────────────────────────────────────────────────────


def _run_common_flow(
    client: httpx.Client,
    url: str,
    method: str,
    req_headers: Dict[str, str],
    cookies: Dict[str, str],
    body: str,
    concurrent_users: int,
    duration: int,
    spawn_rate: int,
    task_name: str,
) -> Optional[Dict]:
    """
    Common HTTP API flow:
      1. POST /api/http-tasks/test  → connectivity check
      2. POST /api/http-tasks       → create loadtest task
    """
    print(f"   请求方法: {method}")
    print(f"   目标 URL: {url}")

    # ── Step 1: Pre-check ──────────────────────────────────────────────────
    print(f"\n🔗 Step 1/2: 预检 API 连通性 ...")

    test_payload = {
        "method": method,
        "target_url": url,
        "headers": _headers_to_kv_list(req_headers),
        "cookies": _cookies_to_kv_list(cookies),
        "request_body": body or "",
    }

    try:
        test_resp = client.post(
            f"{BASE_URL}/api/http-tasks/test",
            headers=headers(),
            json=test_payload,
        )

        if test_resp.status_code != 200:
            print(f"\n❌ 连通性测试失败: HTTP {test_resp.status_code}")
            try:
                err_data = test_resp.json()
                print(f"   详情: {json.dumps(err_data, ensure_ascii=False)}")
            except Exception:
                print(f"   响应: {test_resp.text[:500]}")
            return None

        test_data = test_resp.json()
        if test_data.get("status") == "success":
            http_code = test_data.get("http_status")
            if isinstance(http_code, int) and http_code >= 400:
                cat_key, label, hint = classify_precheck_failure(http_status=http_code)
                print(f"\n❌ 连通性测试未通过: {label}")
                print(f"   HTTP 状态码: {http_code}")
                if hint:
                    print(f"   💡 {hint}")
                return None
            print(f"   ✅ 连通性正常 → HTTP {http_code or '?'}")
        elif test_data.get("status") != "success":
            error = test_data.get("error", "N/A")
            cat_key, label, hint = classify_precheck_failure(error_msg=error)
            print(f"\n❌ 连通性测试未通过: {label}")
            print(f"   错误: {error}")
            if hint:
                print(f"   💡 {hint}")
            return None

    except Exception as e:
        cat_key, label, hint = classify_precheck_failure(error_msg=str(e))
        print(f"\n❌ 连通性测试异常: {label}")
        print(f"   详情: {e}")
        if hint:
            print(f"   💡 {hint}")
        return None

    # ── Step 2: Create task ────────────────────────────────────────────────
    print(f"\n🚀 Step 2/2: 创建 HTTP 压测任务 ...")

    temp_task_id = f"direct_{uuid.uuid4().hex[:8]}"
    create_payload = {
        "temp_task_id": temp_task_id,
        "name": task_name,
        "method": method,
        "target_url": url,
        "headers": _headers_to_kv_list(req_headers),
        "cookies": _cookies_to_kv_list(cookies),
        "request_body": body or "",
        "concurrent_users": concurrent_users,
        "duration": duration,
        "spawn_rate": spawn_rate,
        "load_mode": "fixed",
    }

    try:
        create_resp = client.post(
            f"{BASE_URL}/api/http-tasks",
            headers=headers(),
            json=create_payload,
        )
        create_resp.raise_for_status()
        result = create_resp.json()
        task_id = result.get("task_id", "")
        print(f"   ✅ 任务创建成功 → task_id={task_id}")
        return {
            "task_id": task_id,
            "name": task_name,
            "target_url": url,
            "method": method,
            "duration": duration,
        }
    except Exception as e:
        print(f"   ❌ 任务创建失败: {e}")
        return None


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LMeterX: Direct API Load Test (LLM & HTTP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # curl 命令模式
  python run.py --curl 'curl https://api.openai.com/v1/chat/completions \\
    -H "Authorization: Bearer sk-xxx" \\
    -d \\'{\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\"Hi\"}]}\\''

  # 参数模式 (LLM API)
  python run.py --url https://api.openai.com/v1/chat/completions \\
    --header "Authorization: Bearer sk-xxx" \\
    --body '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}'

  # 参数模式 (普通 HTTP API)
  python run.py --url https://api.example.com/users --method GET
        """,
    )

    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--curl", help="Complete curl command string")
    input_group.add_argument("--url", help="API endpoint URL")

    # HTTP params (used with --url)
    parser.add_argument("--method", default="POST", help="HTTP method (default: POST)")
    parser.add_argument("--body", default="", help="Request body (JSON string)")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="Request header (repeatable, format: 'Key: Value')",
    )
    parser.add_argument(
        "--cookie",
        action="append",
        default=[],
        help="Cookie (repeatable, format: 'Key=Value')",
    )

    # LLM-specific
    parser.add_argument("--model", default="", help="Model name (LLM API)")
    parser.add_argument(
        "--stream",
        dest="stream_mode",
        action="store_true",
        default=None,
        help="Enable streaming (LLM API, default: True)",
    )
    parser.add_argument(
        "--no-stream",
        dest="stream_mode",
        action="store_false",
        help="Disable streaming (LLM API)",
    )

    # Load test params
    parser.add_argument(
        "--concurrent-users",
        type=int,
        default=50,
        help="Concurrent users (default 50)",
    )
    parser.add_argument(
        "--duration", type=int, default=300, help="Duration in seconds (default 300)"
    )
    parser.add_argument(
        "--spawn-rate", type=int, default=30, help="Spawn rate (default 30)"
    )
    parser.add_argument(
        "--name", default="", help="Task name (auto-generated if empty)"
    )

    args = parser.parse_args()

    # ── Step 0: Preflight check ──────────────────────────────────────────
    print("\n🔑 Step 0: 检查后端连通性与认证状态 ...")
    preflight_check()
    print("   ✅ 后端连通，认证正常")

    # ── Parse input ────────────────────────────────────────────────────────
    if args.curl:
        parsed = _parse_curl(args.curl)
        url = parsed["url"]
        method = parsed["method"]
        req_headers = parsed["headers"]
        body = parsed["body"]
        cookies = parsed["cookies"]

        if not url:
            print("❌ 无法从 curl 命令中解析出 URL")
            sys.exit(1)

        print(f"\n📋 已解析 curl 命令:")
        print(f"   URL:    {url}")
        print(f"   Method: {method}")
        print(f"   Headers: {len(req_headers)} 个")
        if body:
            print(f"   Body:   {body[:100]}{'...' if len(body) > 100 else ''}")
    else:
        url = args.url
        method = args.method.upper()
        body = args.body

        # Parse --header flags
        req_headers: Dict[str, str] = {}
        for h in args.header:
            if ":" in h:
                k, v = h.split(":", 1)
                req_headers[k.strip()] = v.strip()

        # Parse --cookie flags
        cookies: Dict[str, str] = {}
        for c in args.cookie:
            if "=" in c:
                k, v = c.split("=", 1)
                cookies[k.strip()] = v.strip()

    # ── Detect API type ───────────────────────────────────────────────────
    is_llm, api_type = _detect_api_type(url)
    type_label = "🤖 LLM API" if is_llm else "🌐 普通 HTTP 业务 API"
    print(f"\n🔍 API 类型识别: {type_label}")

    # ── Prepare parameters ────────────────────────────────────────────────
    concurrent_users = bounded_int(args.concurrent_users, 50, 1, 5000)
    duration = bounded_int(args.duration, 300, 1, 172800)
    spawn_rate = bounded_int(args.spawn_rate, 30, 1, 10000)
    batch_id = f"batch_{uuid.uuid4().hex[:10]}"

    # Auto-generate task name
    parsed_url = urlparse(url)
    auto_name = f"{parsed_url.netloc}{parsed_url.path}"
    if len(auto_name) > 80:
        auto_name = auto_name[:80]
    task_name = args.name or auto_name

    # ── Execute flow ──────────────────────────────────────────────────────
    with httpx.Client(timeout=TIMEOUT, verify=False) as client:
        if is_llm:
            # Resolve model
            model = args.model or _extract_model_from_body(body)

            # Resolve stream mode
            if args.stream_mode is not None:
                stream_mode = args.stream_mode
            else:
                extracted = _extract_stream_from_body(body)
                stream_mode = extracted if extracted is not None else True

            task_result = _run_llm_flow(
                client=client,
                url=url,
                api_type=api_type,
                model=model,
                stream_mode=stream_mode,
                req_headers=req_headers,
                cookies=cookies,
                body=body,
                concurrent_users=concurrent_users,
                duration=duration,
                spawn_rate=spawn_rate,
                task_name=task_name,
            )
            task_type = "llm"
        else:
            task_result = _run_common_flow(
                client=client,
                url=url,
                method=method,
                req_headers=req_headers,
                cookies=cookies,
                body=body,
                concurrent_users=concurrent_users,
                duration=duration,
                spawn_rate=spawn_rate,
                task_name=task_name,
            )
            task_type = "http"

    # ── Summary ───────────────────────────────────────────────────────────
    manifest_path = None
    if task_result:
        created_tasks = [task_result]
        manifest_path = _persist_batch(batch_id, url, task_type, created_tasks)
    else:
        created_tasks = []

    task_ids = [t["task_id"] for t in created_tasks]

    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Batch ID:      {batch_id}")
    print(f"  API Type:      {'LLM' if is_llm else 'HTTP'}")
    print(f"  Target URL:    {url}")
    print(f"  Concurrency:   {concurrent_users}")
    print(f"  Duration:      {duration}s")

    if task_ids:
        print(f"  Task ID:       {task_ids[0]}")
        if manifest_path:
            print(f"  Batch File:    {manifest_path}")

        print(f"\n💡 使用 fetch-loadtest-results 拉取报告:")
        if task_type == "llm":
            print(
                f"   python scripts/fetch.py --task-id {task_ids[0]} --task-type llm --watch"
            )
        else:
            print(f"   python scripts/fetch.py --task-id {task_ids[0]} --watch")
        print(f"   python scripts/fetch.py --batch-id {batch_id} --watch")
    else:
        print("  Status:        ❌ 未创建任务（连通性检测未通过）")

    print()


if __name__ == "__main__":
    main()
