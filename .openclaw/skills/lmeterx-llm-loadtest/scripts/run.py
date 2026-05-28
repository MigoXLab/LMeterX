#!/usr/bin/env python3
"""
lmeterx-llm-loadtest — LMeterX LLM API Load Test Skill Script.

Workflow:
  1. Parse input (curl command or --url/--header/--body params)
  2. Detect LLM API type: openai-chat (/v1/chat/completions) or claude-chat (/v1/messages)
  3. Split URL into target_host + api_path
  4. POST /api/llm-tasks/test → Pre-check connectivity
  5. POST /api/llm-tasks      → Create load test task

Security constraints:
  - Only calls 3 whitelisted LMeterX paths: /health, /api/auth/profile, /api/llm-tasks/*
  - All requests automatically inject X-Authorization: <LMETERX_AUTH_TOKEN>
  - Concurrent number limit [1, 5000], duration limit [1, 172800]
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEPS_DIR = os.path.join(_SCRIPT_DIR, ".deps")

def _ensure_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        pass
    if os.path.isdir(_DEPS_DIR):
        sys.path.insert(0, _DEPS_DIR)
        try:
            import httpx
            return httpx
        except ImportError:
            pass
    print("📦 首次运行，自动安装依赖 httpx ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "httpx", "-t", _DEPS_DIR, "-q"],
        stdout=subprocess.DEVNULL,
    )
    sys.path.insert(0, _DEPS_DIR)
    import httpx
    return httpx

httpx = _ensure_httpx()

# ── Global configuration ──────────────────────────────────────────────────────

LMETERX_BASE_URL: str = os.getenv(
    "LMETERX_BASE_URL", "<YOUR_LMETERX_BASE_URL>"
).rstrip("/")

LMETERX_AUTH_TOKEN: str = os.getenv("LMETERX_AUTH_TOKEN") or "<YOUR_AUTH_TOKEN>"

TIMEOUT = 60.0

# ── LLM path patterns ────────────────────────────────────────────────────────

LLM_PATTERNS: List[Tuple[str, str]] = [
    ("/v1/chat/completions", "openai-chat"),
    ("/v1/messages", "claude-chat"),
]

# ── Pre-check failure classification ─────────────────────────────────────────

_FAILURE_CATEGORIES: Dict[str, Tuple[str, str]] = {
    "401": ("🔐 认证失败 (401)", "目标 API 需要认证，请检查 Authorization 或 API Key"),
    "403": ("🚫 权限不足 (403)", "已认证但无访问权限，请确认账号权限"),
    "404": ("🔗 地址无效 (404)", "API 路径不存在，请检查 URL"),
    "405": ("⛔ 方法不允许 (405)", "HTTP 方法不匹配"),
    "429": ("⏳ 请求限流 (429)", "目标 API 限流中，稍后重试"),
    "4xx": ("⚠️ 客户端错误 (4xx)", "目标 API 返回客户端错误"),
    "5xx": ("💥 服务端错误 (5xx)", "目标服务内部异常"),
    "connection": ("🌐 连接失败", "无法连接目标主机，请检查 URL 和网络"),
    "timeout": ("⏱ 请求超时", "目标 API 响应超时"),
    "ssl": ("🔒 SSL/TLS 错误", "证书验证或 TLS 握手失败"),
    "unknown": ("❓ 未知错误", "发生意外错误"),
}


def _classify_failure(
    *, http_status: Optional[int] = None, error_msg: str = ""
) -> Tuple[str, str, str]:
    if http_status is not None:
        key = str(http_status)
        if key in _FAILURE_CATEGORIES:
            label, hint = _FAILURE_CATEGORIES[key]
            return key, label, hint
        if 400 <= http_status < 500:
            label, hint = _FAILURE_CATEGORIES["4xx"]
            return "4xx", f"{label} ({http_status})", hint
        if http_status >= 500:
            label, hint = _FAILURE_CATEGORIES["5xx"]
            return "5xx", f"{label} ({http_status})", hint
        return "unknown", f"❓ 异常状态码 ({http_status})", ""

    err = error_msg.lower()
    if "timeout" in err:
        cat = "timeout"
    elif "connection" in err:
        cat = "connection"
    elif "ssl" in err:
        cat = "ssl"
    else:
        cat = "unknown"
    label, hint = _FAILURE_CATEGORIES[cat]
    return cat, label, hint


# ── Utility functions ─────────────────────────────────────────────────────────


def _bounded_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(v, hi))


def _headers_to_kv_list(hdr_dict: Dict[str, str]) -> List[Dict[str, str]]:
    return [{"key": k, "value": v} for k, v in hdr_dict.items()]


def _cookies_to_kv_list(cookie_dict: Dict[str, str]) -> List[Dict[str, str]]:
    return [{"key": k, "value": v} for k, v in cookie_dict.items()]


def _make_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Authorization": LMETERX_AUTH_TOKEN,
    }


# ── curl parser ───────────────────────────────────────────────────────────────


def _parse_curl(curl_cmd: str) -> Dict[str, Any]:
    cmd = curl_cmd.replace("\\\n", " ").replace("\\\r\n", " ").strip()
    if re.match(r"^curl\s", cmd, re.IGNORECASE):
        cmd = re.sub(r"^curl\s+", "", cmd, count=1, flags=re.IGNORECASE)

    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()

    url = ""
    method = ""
    req_headers: Dict[str, str] = {}
    body = ""
    cookies: Dict[str, str] = {}

    SKIP_FLAGS_WITH_ARG = {
        "--connect-timeout", "--max-time", "-m", "--retry", "-o", "--output",
        "-u", "--user", "-e", "--referer", "-A", "--user-agent", "--proxy",
        "-x", "--cert", "--key", "--cacert",
    }
    SKIP_FLAGS_NO_ARG = {
        "--compressed", "--insecure", "-k", "-v", "--verbose", "-s", "--silent",
        "-S", "--show-error", "-L", "--location", "-i", "--include", "-f",
        "--fail", "-N", "--no-buffer",
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
            if i < len(tokens) and ":" in tokens[i]:
                key, val = tokens[i].split(":", 1)
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
            pass
        elif tok in SKIP_FLAGS_WITH_ARG:
            i += 1
        elif tok.startswith("http://") or tok.startswith("https://"):
            url = tok
        elif not tok.startswith("-") and not url and "://" in tok:
            url = tok
        i += 1

    if not method:
        method = "POST" if body else "GET"

    return {"url": url, "method": method, "headers": req_headers, "body": body, "cookies": cookies}


# ── LLM API detection and URL splitting ───────────────────────────────────────


def _detect_llm_type(url: str) -> Tuple[bool, str]:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    for pattern, api_type in LLM_PATTERNS:
        if path.endswith(pattern):
            return True, api_type
    return False, ""


def _split_llm_url(url: str, api_type: str) -> Tuple[str, str]:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")

    if api_type == "openai-chat":
        suffix = "/chat/completions"
    elif api_type == "claude-chat":
        suffix = "/messages"
    else:
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base, path or "/"

    idx = path.rfind(suffix)
    if idx >= 0:
        prefix_path = path[:idx]
        target_host = f"{parsed.scheme}://{parsed.netloc}{prefix_path}"
        return target_host, suffix
    else:
        base = f"{parsed.scheme}://{parsed.netloc}"
        return base, path or "/"


def _extract_model_from_body(body: str) -> str:
    if not body:
        return ""
    try:
        return json.loads(body).get("model", "")
    except (json.JSONDecodeError, AttributeError):
        return ""


def _extract_stream_from_body(body: str) -> Optional[bool]:
    if not body:
        return None
    try:
        val = json.loads(body).get("stream")
        return val if isinstance(val, bool) else None
    except (json.JSONDecodeError, AttributeError):
        return None


# ── Preflight check ───────────────────────────────────────────────────────────


def _preflight_check() -> None:
    try:
        resp = httpx.get(f"{LMETERX_BASE_URL}/health", timeout=10.0, verify=False)
        if resp.status_code != 200:
            print(f"❌ LMeterX 后端健康检查异常: HTTP {resp.status_code}")
            print(f"   请确认 LMETERX_BASE_URL={LMETERX_BASE_URL} 是否正确")
            sys.exit(1)
    except httpx.ConnectError:
        print(f"❌ 无法连接 LMeterX 后端: {LMETERX_BASE_URL}")
        print("   请确认后端服务已启动且网络畅通")
        sys.exit(1)
    except httpx.TimeoutException:
        print(f"❌ 连接 LMeterX 后端超时: {LMETERX_BASE_URL}")
        sys.exit(1)

    try:
        profile_resp = httpx.get(
            f"{LMETERX_BASE_URL}/api/auth/profile",
            headers=_make_headers(),
            timeout=10.0,
            verify=False,
        )
        if profile_resp.status_code == 200:
            profile = profile_resp.json()
            user = profile.get("username", "")
            if user and user not in ("anonymous", "-"):
                print(f"   👤 已认证用户: {user}")
        elif profile_resp.status_code == 401:
            if not os.getenv("LMETERX_AUTH_TOKEN"):
                print("❌ LMeterX 后端已启用认证，但未配置 LMETERX_AUTH_TOKEN")
            else:
                print("❌ LMETERX_AUTH_TOKEN 无效或已过期")
            sys.exit(1)
    except Exception as e:
        print(f"⚠️ 认证检查异常 ({e})，继续执行...")


# ── Main flow ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LMeterX LLM API Load Test (OpenAI / Claude compatible)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # URL mode
  python run.py --url https://api.openai.com/v1/chat/completions \\
    --header "Authorization: Bearer sk-xxx" \\
    --body '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}'

  # curl mode
  python run.py --curl 'curl https://api.openai.com/v1/chat/completions \\
    -H "Authorization: Bearer sk-xxx" \\
    -d \\'{\"model\":\"gpt-4\",\"messages\":[{\"role\":\"user\",\"content\":\"Hi\"}]}\\''
""",
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--curl", help="Complete curl command string")
    input_group.add_argument("--url", help="LLM API endpoint URL")

    parser.add_argument("--body", default="", help="Request body (JSON string)")
    parser.add_argument(
        "--header", action="append", default=[], help="Request header (repeatable, format: 'Key: Value')"
    )
    parser.add_argument(
        "--cookie", action="append", default=[], help="Cookie (repeatable, format: 'Key=Value')"
    )
    parser.add_argument("--model", default="", help="Model name (auto-extracted from body if not set)")
    parser.add_argument("--stream", dest="stream_mode", action="store_true", default=None, help="Enable streaming")
    parser.add_argument("--no-stream", dest="stream_mode", action="store_false", help="Disable streaming")
    parser.add_argument("--concurrent-users", type=int, default=50, help="Concurrent users (default 50)")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds (default 300)")
    parser.add_argument("--spawn-rate", type=int, default=30, help="Spawn rate (default 30)")
    parser.add_argument("--name", default="", help="Task name (auto-generated if empty)")
    parser.add_argument(
        "--test-data", default="",
        help="Test dataset: '' for none (default), 'default' for built-in dataset"
    )

    args = parser.parse_args()

    # ── Step 0: Preflight ─────────────────────────────────────────────────
    print("\n🔑 Step 0: 检查 LMeterX 后端连通性与认证 ...")
    _preflight_check()
    print("   ✅ 后端连通，认证正常")

    # ── Parse input ───────────────────────────────────────────────────────
    if args.curl:
        parsed = _parse_curl(args.curl)
        url = parsed["url"]
        req_headers = parsed["headers"]
        body = parsed["body"]
        cookies = parsed["cookies"]
        if not url:
            print("❌ 无法从 curl 命令中解析出 URL")
            sys.exit(1)
        print(f"\n📋 已解析 curl 命令:")
        print(f"   URL:     {url}")
        print(f"   Headers: {len(req_headers)} 个")
    else:
        url = args.url
        body = args.body
        req_headers: Dict[str, str] = {}
        for h in args.header:
            if ":" in h:
                k, v = h.split(":", 1)
                req_headers[k.strip()] = v.strip()
        cookies: Dict[str, str] = {}
        for c in args.cookie:
            if "=" in c:
                k, v = c.split("=", 1)
                cookies[k.strip()] = v.strip()

    # ── Validate LLM URL ──────────────────────────────────────────────────
    is_llm, api_type = _detect_llm_type(url)
    if not is_llm:
        print(f"\n❌ URL 不是 LLM API 端点: {url}")
        print("   LLM API 必须以 /v1/chat/completions 或 /v1/messages 结尾")
        print("   如需压测普通 HTTP API，请使用 lmeterx-http-loadtest")
        sys.exit(1)

    target_host, api_path = _split_llm_url(url, api_type)
    model = args.model or _extract_model_from_body(body)

    if args.stream_mode is not None:
        stream_mode = args.stream_mode
    else:
        extracted = _extract_stream_from_body(body)
        stream_mode = extracted if extracted is not None else True

    # Filter Content-Type from user headers
    filtered_headers = {k: v for k, v in req_headers.items() if k.lower() != "content-type"}

    api_type_label = "OpenAI Chat" if api_type == "openai-chat" else "Claude Chat"
    print(f"\n🔍 API 类型: 🤖 {api_type_label}")
    print(f"   目标主机: {target_host}")
    print(f"   API 路径: {api_path}")
    print(f"   模型:     {model or '(auto)'}")
    print(f"   流式:     {stream_mode}")

    # ── Prepare parameters ────────────────────────────────────────────────
    concurrent_users = _bounded_int(args.concurrent_users, 50, 1, 5000)
    duration = _bounded_int(args.duration, 300, 1, 172800)
    spawn_rate = _bounded_int(args.spawn_rate, 30, 1, 10000)

    parsed_url = urlparse(url)
    auto_name = f"{parsed_url.netloc}{parsed_url.path}"
    if len(auto_name) > 80:
        auto_name = auto_name[:80]
    task_name = args.name or auto_name

    # ── Step 1: Pre-check ─────────────────────────────────────────────────
    print(f"\n🔗 Step 1/2: 预检 LLM API 连通性 ...")

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

    with httpx.Client(timeout=TIMEOUT, verify=False) as client:
        try:
            test_resp = client.post(
                f"{LMETERX_BASE_URL}/api/llm-tasks/test",
                headers=_make_headers(),
                json=test_payload,
            )

            if test_resp.status_code != 200:
                print(f"   ❌ 连通性测试失败: HTTP {test_resp.status_code}")
                try:
                    err_data = test_resp.json()
                    print(f"   详情: {json.dumps(err_data, ensure_ascii=False)}")
                except Exception:
                    print(f"   响应: {test_resp.text[:500]}")
                sys.exit(1)

            test_data = test_resp.json()
            if test_data.get("status") == "success":
                http_code = test_data.get("http_status")
                if isinstance(http_code, int) and http_code >= 400:
                    _, label, hint = _classify_failure(http_status=http_code)
                    print(f"   ❌ 连通性测试未通过: {label}")
                    if hint:
                        print(f"   💡 {hint}")
                    sys.exit(1)
                print(f"   ✅ 连通性正常 → HTTP {http_code or '?'}")
            else:
                error = test_data.get("error", "N/A")
                _, label, hint = _classify_failure(error_msg=error)
                print(f"   ❌ 连通性测试未通过: {label}")
                print(f"   错误: {error}")
                if hint:
                    print(f"   💡 {hint}")
                sys.exit(1)

        except SystemExit:
            raise
        except Exception as e:
            _, label, hint = _classify_failure(error_msg=str(e))
            print(f"   ❌ 连通性测试异常: {label}")
            print(f"   详情: {e}")
            if hint:
                print(f"   💡 {hint}")
            sys.exit(1)

        # ── Step 2: Create task ───────────────────────────────────────────
        print(f"\n🚀 Step 2/2: 创建 LLM 压测任务 ...")

        temp_task_id = f"llm_{uuid.uuid4().hex[:8]}"
        test_data = args.test_data
        chat_type = 2 if test_data else 0
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
            "test_data": test_data,
            "chat_type": chat_type,
            "warmup_enabled": True,
            "warmup_duration": 120,
            "load_mode": "fixed",
        }

        try:
            create_resp = client.post(
                f"{LMETERX_BASE_URL}/api/llm-tasks",
                headers=_make_headers(),
                json=create_payload,
            )
            create_resp.raise_for_status()
            result = create_resp.json()
            task_id = result.get("task_id", "")
        except Exception as e:
            print(f"   ❌ 任务创建失败: {e}")
            sys.exit(1)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  📊 执行摘要")
    print(f"{'=' * 60}")
    print(f"  API 类型:     🤖 {api_type_label}")
    print(f"  目标主机:     {target_host}")
    print(f"  模型:         {model or '(auto)'}")
    print(f"  数据集:       {test_data or '(无，使用 request_payload)'}")
    print(f"  并发用户:     {concurrent_users}")
    print(f"  持续时间:     {duration}s")
    print(f"  Task ID:      {task_id}")
    print(f"\n  📈 查看报告:")
    print(f"     → {LMETERX_BASE_URL}/results/{task_id}")
    print()


if __name__ == "__main__":
    main()
