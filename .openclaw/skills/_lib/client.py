"""
Shared HTTP client utilities for LMeterX OpenClaw skills.

Provides:
  - Unified env-file loading (priority: skills/.env > .openclaw/.env)
  - Unified auth-token normalization
  - Common HTTP helpers (headers, fetch task data, pick total row)
  - Preflight check (backend reachability + auth token validation)
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx

# ── Path constants ──────────────────────────────────────────────────────────

SKILLS_ROOT = Path(__file__).resolve().parents[1]  # .openclaw/skills/
OPENCLAW_ROOT = SKILLS_ROOT.parent  # .openclaw/
ARTIFACT_ROOT = SKILLS_ROOT / ".artifacts" / "loadtest-batches"

TERMINAL_STATUSES = {"completed", "failed_requests", "failed", "stopped", "cancelled"}


def bounded_int(value, default: int, lo: int, hi: int) -> int:
    """Convert *value* to int and clamp into [lo, hi]."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(v, hi))


# ── Env-file loading ────────────────────────────────────────────────────────


def _load_env_file(path: Path) -> None:
    """Load key=value pairs from *path* into ``os.environ`` (existing keys win)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


for _p in [
    SKILLS_ROOT / ".env",
    SKILLS_ROOT / ".env.local",
    OPENCLAW_ROOT / ".env",
    OPENCLAW_ROOT / ".env.local",
]:
    _load_env_file(_p)

BASE_URL: str = os.getenv("LMETERX_BASE_URL", "")
AUTH_TOKEN: str = os.getenv("LMETERX_AUTH_TOKEN", "")

# ── Auth helpers ────────────────────────────────────────────────────────────


def _normalize_auth_token(raw: str) -> str:
    """Ensure token has exactly one ``Bearer`` prefix."""
    token = (raw or "").strip()
    if not token:
        return ""
    if token.lower().startswith("bearer "):
        payload = token[7:].strip()
        return f"Bearer {payload}" if payload else ""
    return f"Bearer {token}"


def headers() -> dict:
    """Return common request headers (Content-Type + auth)."""
    h: Dict[str, str] = {"Content-Type": "application/json"}
    normalized = _normalize_auth_token(AUTH_TOKEN)
    if normalized:
        h["Authorization"] = normalized
        h["X-Authorization"] = normalized
    return h


# ── Preflight check ─────────────────────────────────────────────────────────

_ENV_FILE_HINT = (
    "   配置方式:\n"
    "     1. 在 .openclaw/.env 或 .openclaw/skills/.env 中添加:\n"
    "        LMETERX_AUTH_TOKEN=<your-jwt-token>\n"
    "     2. 或设置环境变量:\n"
    "        export LMETERX_AUTH_TOKEN=<your-jwt-token>\n"
    "\n"
    "   获取 Token:\n"
    "     curl -X POST {base_url}/api/auth/login \\\n"
    "       -H 'Content-Type: application/json' \\\n"
    '       -d \'{{"username":"<user>","password":"<pass>"}}\'\n'
)


def preflight_check(*, timeout: float = 10.0) -> None:
    """Step 0: verify backend reachability and auth token validity.

    Exits the process with a helpful message when something is wrong.
    """
    # ── 1. BASE_URL must be set ──────────────────────────────────────────
    if not BASE_URL:
        print("\n❌ LMETERX_BASE_URL 未配置。")
        print("   请在 .openclaw/.env 中设置 LMETERX_BASE_URL=<后端地址>")
        print("   例如: LMETERX_BASE_URL=http://localhost:5001")
        sys.exit(1)

    # ── 2. Backend reachable? ────────────────────────────────────────────
    try:
        resp = httpx.get(
            f"{BASE_URL}/health",
            timeout=timeout,
            verify=False,
        )
        if resp.status_code != 200:
            print(f"\n❌ 后端健康检查异常: HTTP {resp.status_code}")
            print(f"   请确认 LMETERX_BASE_URL={BASE_URL} 是否正确。")
            sys.exit(1)
    except httpx.ConnectError:
        print(f"\n❌ 无法连接后端: {BASE_URL}")
        print("   请确认:")
        print(f"     • LMETERX_BASE_URL={BASE_URL} 是否正确")
        print("     • 后端服务是否已启动")
        print("     • 网络/防火墙是否畅通")
        sys.exit(1)
    except httpx.TimeoutException:
        print(f"\n❌ 连接后端超时: {BASE_URL}")
        print("   请确认后端服务是否正常运行。")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 连接后端失败: {e}")
        sys.exit(1)

    # ── 3. Auth token valid? ─────────────────────────────────────────────
    try:
        profile_resp = httpx.get(
            f"{BASE_URL}/api/auth/profile",
            headers=headers(),
            timeout=timeout,
            verify=False,
        )

        if profile_resp.status_code == 200:
            profile = profile_resp.json()
            user = profile.get("username", profile.get("display_name", ""))
            if user and user not in ("anonymous", "-"):
                print(f"   👤 已认证用户: {user}")
            return  # Auth OK (or LDAP disabled → anonymous)

        if profile_resp.status_code == 401:
            if not AUTH_TOKEN:
                print("\n❌ 后端已启用 LDAP 认证，但未配置 LMETERX_AUTH_TOKEN。")
            else:
                print("\n❌ LMETERX_AUTH_TOKEN 无效或已过期。")
            print(_ENV_FILE_HINT.format(base_url=BASE_URL))
            sys.exit(1)

        # Other status codes — warn but don't block
        print(f"\n⚠️ 认证检查返回 HTTP {profile_resp.status_code}，继续执行...")

    except Exception as e:
        # If profile endpoint fails for non-auth reasons, warn and continue
        print(f"\n⚠️ 认证检查异常 ({e})，继续执行...")


# ── Pre-check failure classification ─────────────────────────────────────────

# (emoji_label, hint) indexed by category key
_FAILURE_CATEGORIES: Dict[str, Tuple[str, str]] = {
    # HTTP status-code based
    "401": (
        "🔐 认证失败 (401)",
        "目标 API 需要认证，请检查 Headers 中的 Authorization 或 API Key",
    ),
    "403": ("🚫 权限不足 (403)", "已认证但无访问权限，请确认账号权限或 IP 白名单"),
    "404": ("🔗 地址无效 (404)", "API 路径不存在，可能是死链或爬虫抓取了无效地址"),
    "405": ("⛔ 方法不允许 (405)", "HTTP 方法不匹配，请检查 GET/POST 等是否正确"),
    "429": ("⏳ 请求限流 (429)", "目标 API 限流中，请稍后重试或降低并发"),
    "4xx": ("⚠️ 客户端错误 (4xx)", "目标 API 返回客户端错误"),
    "5xx": ("💥 服务端错误 (5xx)", "目标服务内部异常"),
    # Connection-level
    "connection": ("🌐 连接失败", "无法连接目标主机，请检查 URL 和网络"),
    "timeout": ("⏱ 请求超时", "目标 API 响应超时"),
    "ssl": ("🔒 SSL/TLS 错误", "证书验证或 TLS 握手失败"),
    "unknown": ("❓ 未知错误", "发生意外错误"),
}


def classify_precheck_failure(
    *,
    http_status: Optional[int] = None,
    error_msg: str = "",
) -> Tuple[str, str, str]:
    """Classify a pre-check failure into a category.

    Call this when the pre-check did **not** pass (either a non-2xx/3xx
    ``http_status`` was returned, or a connection-level ``error_msg`` was
    received from the backend).

    Returns:
        ``(category_key, emoji_label, hint)``
    """
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
        # Unexpected code (1xx, etc.)
        return "unknown", f"❓ 异常状态码 ({http_status})", ""

    # Connection-level error — classify by error message prefix
    err = error_msg.lower()
    if "connection error" in err:
        cat = "connection"
    elif "timeout" in err:
        cat = "timeout"
    elif "ssl" in err:
        cat = "ssl"
    else:
        cat = "unknown"
    label, hint = _FAILURE_CATEGORIES[cat]
    return cat, label, hint


def print_failure_summary(
    failures: List[Tuple[str, str, str]],
) -> None:
    """Print a categorised summary of pre-check failures.

    Args:
        failures: list of ``(api_name, category_key, detail_msg)`` tuples.
    """
    if not failures:
        return

    # Group by category
    by_cat: Dict[str, List[Tuple[str, str]]] = {}
    for name, cat_key, detail in failures:
        by_cat.setdefault(cat_key, []).append((name, detail))

    print(f"\n{'─' * 60}")
    print("  📋 预检失败归类")
    print(f"{'─' * 60}")
    for cat_key, items in by_cat.items():
        label, hint = _FAILURE_CATEGORIES.get(cat_key, ("❓", ""))
        print(f"\n  {label}  ({len(items)} 个)")
        if hint:
            print(f"  💡 {hint}")
        for api_name, detail in items:
            print(f"     • {api_name}: {detail}")
    print(f"{'─' * 60}")


# ── Data helpers ────────────────────────────────────────────────────────────


def pick_total_row(results: List[Dict]) -> Dict:
    """Return the *Total* metric row from a results list."""
    for row in results:
        if str(row.get("metric_type", "")).lower() == "total":
            return row
    return results[-1] if results else {}


def fetch_task_data(
    client: httpx.Client, task_id: str, task_type: str = "http"
) -> Dict:
    """Fetch task detail + performance results from the backend.

    Args:
        client: httpx client instance.
        task_id: The task ID to fetch.
        task_type: "http" for regular HTTP tasks, "llm" for LLM API tasks.
    """
    if task_type == "llm":
        base_path = f"{BASE_URL}/api/llm-tasks"
    else:
        base_path = f"{BASE_URL}/api/http-tasks"

    detail_resp = client.get(
        f"{base_path}/{task_id}",
        headers=headers(),
    )
    detail_resp.raise_for_status()

    results_resp = client.get(
        f"{base_path}/{task_id}/results",
        headers=headers(),
    )
    results_resp.raise_for_status()

    return {
        "detail": detail_resp.json(),
        "results": results_resp.json().get("results", []),
    }
