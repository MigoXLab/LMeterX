#!/usr/bin/env python3
"""
lmeterx-web-loadtest — LMeterX Web Load Test Skill Script.

Workflow:
  1. POST /api/skills/analyze-url  → Analyze page, discover APIs and generate load test configurations
  2. POST /api/http-tasks/test     → Concurrent pre-check the connectivity of each API
  3. POST /api/http-tasks          → Concurrent create load test tasks

Security constraints:
  - Only allow calling the above 3 whitelisted interfaces
  - All requests automatically inject X-Authorization: <LMETERX_AUTH_TOKEN>
  - Concurrent number limit [1, 5000], URL must start with http(s)://
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ── Global configuration ──────────────────────────────────────────────────────

LMETERX_BASE_URL: str = os.getenv("LMETERX_BASE_URL", "https://localhost:8080").rstrip(
    "/"
)

# Prioritize getting Service Token from environment variables; if not configured, use the built-in default value "localhost_lmeterx".
LMETERX_AUTH_TOKEN: str = os.getenv("LMETERX_AUTH_TOKEN") or "localhost_lmeterx"

# Only allow calling the following 3 whitelisted interface paths
_ALLOWED_PATHS = frozenset(
    {
        "/api/skills/analyze-url",
        "/api/http-tasks/test",
        "/api/http-tasks",
    }
)

# Timeout control (seconds)
TIMEOUT_ANALYZE = 60.0  # Analyze interface is slow (Playwright rendering)
TIMEOUT_DEFAULT = 30.0  # Other interfaces

# Concurrent number limit
MAX_CONCURRENT_USERS = 5000
MIN_CONCURRENT_USERS = 1

# Concurrent worker thread limit
MAX_WORKERS = 10

# ── Pre-check failure classification ─────────────────────────────────────────

_FAILURE_CATEGORIES: Dict[str, Tuple[str, str]] = {
    "401": (
        "🔐 Authentication failed (401)",
        "The target API requires authentication, check X-Authorization in Headers",
    ),
    "403": (
        "🚫 Permission denied (403)",
        "Authenticated but no access, confirm account permissions or IP whitelist",
    ),
    "404": (
        "🔗 Address invalid (404)",
        "API path does not exist, possibly a dead link",
    ),
    "405": (
        "⛔ Method not allowed (405)",
        "HTTP method does not match, check GET/POST",
    ),
    "429": ("⏳ Request throttled (429)", "Target API is throttled, try again later"),
    "4xx": ("⚠️ Client error (4xx)", "Target API returned client error"),
    "5xx": ("💥 Server error (5xx)", "Target service internal exception"),
    "connection": (
        "🌐 Connection failed",
        "Cannot connect to target host, check URL and network",
    ),
    "timeout": ("⏱ Request timeout", "Target API response timeout"),
    "ssl": ("🔒 SSL/TLS error", "Certificate verification or TLS handshake failed"),
    "unknown": ("❓ Unknown error", "Unexpected error occurred"),
}


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _classify_failure(
    *, http_status: Optional[int] = None, error_msg: str = ""
) -> Tuple[str, str, str]:
    """Classify pre-check failures into (category_key, emoji_label, hint)."""
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
        return "unknown", f"❓ Unexpected status code ({http_status})", ""

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


def _validate_url(url: str) -> str:
    """Validate URL format, must start with http(s)://."""
    if not re.match(r"^https?://", url):
        print(f"❌ Invalid URL format: {url} (must start with http:// or https://)")
        sys.exit(1)
    return url


def _validate_concurrency(n: int) -> int:
    """Validate concurrency number is in the range [1, 5000]."""
    if not (MIN_CONCURRENT_USERS <= n <= MAX_CONCURRENT_USERS):
        print(
            f"❌ Concurrency number {n} out of range [{MIN_CONCURRENT_USERS}, {MAX_CONCURRENT_USERS}]"
        )
        sys.exit(1)
    return n


def _clamp(value: Any, default: int, lo: int, hi: int) -> int:
    """Convert value to int and limit it in the range [lo, hi]."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = default
    return max(lo, min(v, hi))


# ── HTTP security encapsulation ────────────────────────────────────────────────


def _safe_request(
    client: httpx.Client,
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP security encapsulation: whitelist validation + Auth injection + exception handling.

    All requests to the LMeterX backend must be sent through this function.
    """
    # 1. Whitelist forced validation
    if path not in _ALLOWED_PATHS:
        print(
            f"❌ [Security intercept] Path {path} is not in the authorized whitelist, request blocked."
        )
        sys.exit(1)

    # 2. Assemble URL & Headers
    url = f"{LMETERX_BASE_URL}{path}"
    req_headers = kwargs.pop("headers", {})
    req_headers.update(
        {
            "Content-Type": "application/json",
            "X-Authorization": f"{LMETERX_AUTH_TOKEN}",
        }
    )

    # 3. Select timeout
    timeout = TIMEOUT_ANALYZE if "analyze" in path else TIMEOUT_DEFAULT

    # 4. Send request + error classification
    try:
        resp = client.request(
            method, url, headers=req_headers, timeout=timeout, **kwargs
        )
    except httpx.ConnectError:
        print(
            f"❌ Cannot connect to LMeterX service ({LMETERX_BASE_URL}), check network."
        )
        sys.exit(1)
    except httpx.TimeoutException:
        print(
            f"❌ Request timeout ({path}), target page may be too complex, please缩小分析范围。"
        )
        sys.exit(1)

    if resp.status_code in (401, 403):
        print(
            "❌ LMeterX Token invalid or expired, check LMETERX_AUTH_TOKEN configuration."
        )
        sys.exit(1)
    if resp.status_code >= 500:
        print(
            f"❌ LMeterX platform service exception (HTTP {resp.status_code}), please try again later."
        )
        sys.exit(1)

    resp.raise_for_status()
    return resp


# ── Step 1: Analyze page ─────────────────────────────────────────────────────


def analyze_page(
    client: httpx.Client,
    url: str,
    concurrent_users: int,
    duration: int,
    spawn_rate: int,
) -> Tuple[List[Dict], str]:
    """Call /api/skills/analyze-url to analyze the page.

    Returns:
        (loadtest_configs, analysis_summary)
    """
    resp = _safe_request(
        client,
        "POST",
        "/api/skills/analyze-url",
        json={
            "target_url": url,
            "concurrent_users": concurrent_users,
            "duration": duration,
            "spawn_rate": spawn_rate,
        },
    )
    data = resp.json()

    if data.get("status") != "success":
        print(f"❌ Page analysis failed: {data.get('message', 'Unknown error')}")
        sys.exit(1)

    configs: List[Dict] = data.get("loadtest_configs", [])
    if not configs:
        print("⚠️ No testable API found, process terminated.")
        sys.exit(0)

    summary = data.get("analysis_summary", "")
    return configs, summary


# ── Step 2: Concurrent pre-check ─────────────────────────────────────────────


def _precheck_one(client: httpx.Client, cfg: Dict) -> Tuple[Dict, bool, str, str, str]:
    """Pre-check the connectivity of a single API.

    Returns:
        (cfg, passed, message, category_key, detail)
    """
    name = cfg.get("name", cfg.get("target_url", ""))
    try:
        resp = _safe_request(
            client,
            "POST",
            "/api/http-tasks/test",
            json={
                "method": cfg["method"],
                "target_url": cfg["target_url"],
                "headers": cfg.get("headers", []),
                "cookies": cfg.get("cookies", []),
                "request_body": cfg.get("request_body", ""),
            },
        )
        result = resp.json()

        if result.get("status") == "success":
            http_code = result.get("http_status")
            if isinstance(http_code, int) and http_code >= 400:
                cat_key, label, _ = _classify_failure(http_status=http_code)
                return (
                    cfg,
                    False,
                    f"❌ {name} → HTTP {http_code} ({label})",
                    cat_key,
                    f"HTTP {http_code}",
                )
            return cfg, True, f"✅ {name} → HTTP {http_code or '?'}", "", ""
        else:
            error = result.get("error", "Failed")
            cat_key, label, _ = _classify_failure(error_msg=error)
            return cfg, False, f"❌ {name} → {error}", cat_key, error
    except SystemExit:
        raise
    except Exception as e:
        cat_key, label, _ = _classify_failure(error_msg=str(e))
        return cfg, False, f"❌ {name} → {e}", cat_key, str(e)


def precheck_apis(
    client: httpx.Client, configs: List[Dict]
) -> Tuple[List[Dict], List[Tuple[str, str, str]]]:
    """Concurrent pre-check all candidate APIs.

    Returns:
        (passed_configs, failures)
        failures: list of (api_name, category_key, detail)
    """
    n_workers = min(MAX_WORKERS, len(configs))
    passed: List[Dict] = []
    failures: List[Tuple[str, str, str]] = []

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_precheck_one, client, cfg): cfg for cfg in configs}
        for future in as_completed(futures):
            cfg, ok, msg, cat_key, detail = future.result()
            print(f"   {msg}")
            if ok:
                passed.append(cfg)
            else:
                api_name = cfg.get("name", cfg.get("target_url", "?"))
                failures.append((api_name, cat_key, detail))

    return passed, failures


# ── Step 3: Concurrent create tasks ───────────────────────────────────────────


def _create_one(client: httpx.Client, cfg: Dict) -> Tuple[str, bool, str, Dict]:
    """Create a single load test task.

    Returns:
        (name, success, message, task_info_dict)
    """
    name = cfg.get("name", "")
    try:
        resp = _safe_request(
            client,
            "POST",
            "/api/http-tasks",
            json={
                "temp_task_id": cfg.get("temp_task_id", ""),
                "name": cfg.get("name", ""),
                "method": cfg["method"],
                "target_url": cfg["target_url"],
                "headers": cfg.get("headers", []),
                "cookies": cfg.get("cookies", []),
                "request_body": cfg.get("request_body", ""),
                "concurrent_users": _clamp(
                    cfg.get("concurrent_users", 50), 50, 1, 5000
                ),
                "duration": _clamp(cfg.get("duration", 300), 300, 1, 172800),
                "spawn_rate": _clamp(cfg.get("spawn_rate", 30), 30, 1, 10000),
                "load_mode": cfg.get("load_mode", "fixed"),
            },
        )
        result = resp.json()
        task_id = result.get("task_id", "")
        return (
            name,
            True,
            f"✅ {name} → task_id={task_id}",
            {
                "task_id": task_id,
                "name": name,
                "target_url": cfg["target_url"],
                "method": cfg["method"],
            },
        )
    except SystemExit:
        raise
    except Exception as e:
        return name, False, f"❌ {name} → {e}", {}


def create_tasks(client: httpx.Client, configs: List[Dict]) -> List[Dict]:
    """Concurrent create load test tasks for all pre-checked APIs."""
    n_workers = min(MAX_WORKERS, len(configs))
    created: List[Dict] = []

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_create_one, client, cfg): cfg for cfg in configs}
        for future in as_completed(futures):
            name, ok, msg, task_info = future.result()
            print(f"   {msg}")
            if ok:
                created.append(task_info)

    return created


# ── Output ─────────────────────────────────────────────────────────────────────


def _print_failure_summary(failures: List[Tuple[str, str, str]]) -> None:
    """Print pre-check failure summary by category."""
    if not failures:
        return

    by_cat: Dict[str, List[Tuple[str, str]]] = {}
    for name, cat_key, detail in failures:
        by_cat.setdefault(cat_key, []).append((name, detail))

    print(f"\n{'─' * 60}")
    print("  📋 Pre-check failure classification")
    print(f"{'─' * 60}")
    for cat_key, items in by_cat.items():
        label, hint = _FAILURE_CATEGORIES.get(cat_key, ("❓", ""))
        print(f"\n  {label}  ({len(items)} items)")
        if hint:
            print(f"  💡 {hint}")
        for api_name, detail in items:
            print(f"     • {api_name}: {detail}")
    print(f"{'─' * 60}")


def print_summary(
    url: str,
    total_configs: int,
    passed_count: int,
    failures: List[Tuple[str, str, str]],
    created_tasks: List[Dict],
) -> None:
    """Print final execution summary."""
    if failures:
        _print_failure_summary(failures)

    task_ids = [t["task_id"] for t in created_tasks]

    print(f"\n{'=' * 60}")
    print("  📊 Execution summary")
    print(f"{'=' * 60}")
    print(f"  Target URL:    {url}")
    print(f"  Discovered APIs:    {total_configs} APIs")
    print(f"  Pre-checked:    {passed_count}/{total_configs}")
    print(f"  Created tasks:    {len(task_ids)} tasks")

    if task_ids:
        print(f"  Task IDs:     {', '.join(task_ids)}")
        print(f"\n  📈 View report:")
        for t in created_tasks:
            print(f"     {t['name']}")
            print(f"     → {LMETERX_BASE_URL}/http-results/{t['task_id']}")
    else:
        print("\n  ⚠️ No tasks created.")

    print()


# ── Main entry ─────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LMeterX Web Load Test Tool",
        epilog="Example: python run.py --url https://example.com --concurrent-users 10",
    )
    parser.add_argument("--url", required=True, help="Target webpage URL")
    parser.add_argument(
        "--concurrent-users", type=int, default=10, help="Concurrent users (default 10)"
    )
    parser.add_argument(
        "--duration", type=int, default=300, help="Duration in seconds (default 300)"
    )
    parser.add_argument(
        "--spawn-rate", type=int, default=10, help="User spawn rate (default 10)"
    )
    args = parser.parse_args()

    # Parameter validation
    _validate_url(args.url)
    _validate_concurrency(args.concurrent_users)

    with httpx.Client(verify=False) as client:
        # Step 1: Analyze page
        print(f"\n🔍 Step 1/3: Analyze page {args.url} ...")
        configs, summary = analyze_page(
            client, args.url, args.concurrent_users, args.duration, args.spawn_rate
        )
        print(f"   ✅ Discovered {len(configs)} candidate APIs")
        if summary:
            print(f"   📝 {summary}")

        # Step 2: Concurrent pre-check
        print(f"\n🔗 Step 2/3: Pre-check {len(configs)} APIs connectivity ...")
        passed, failures = precheck_apis(client, configs)
        print(f"\n   📊 Pre-checked: {len(passed)}/{len(configs)}")

        if not passed:
            _print_failure_summary(failures)
            print("\n❌ All APIs pre-check failed, process terminated.")
            sys.exit(1)

        # Step 3: Concurrent create tasks
        print(f"\n🚀 Step 3/3: Create {len(passed)} load test tasks ...")
        created_tasks = create_tasks(client, passed)

        # Output summary
        print_summary(args.url, len(configs), len(passed), failures, created_tasks)


if __name__ == "__main__":
    main()
