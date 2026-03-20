"""
Skill Service — Web URL analysis and loadtest config generation.

Workflow:
  1. Use Playwright to load the target page and capture XHR/Fetch requests
  2. Filter out static resources, tracking, probes → core business APIs
  3. If LLM is configured, call LLM to generate smart loadtest configs;
     otherwise, assign fixed defaults (concurrent=50, duration=300s)
  4. Return discovered APIs + ready-to-use loadtest configs

Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import Request

from model.skill import (
    AnalyzeUrlRequest,
    AnalyzeUrlResponse,
    DiscoveredApiItem,
    LoadtestConfigItem,
)
from utils.logger import logger

# Keep generated configs aligned with common-task model constraints.
_MIN_CONCURRENT_USERS = 1
_MAX_CONCURRENT_USERS = 5000
_MIN_DURATION_SECONDS = 1
_MAX_DURATION_SECONDS = 172800
_MIN_SPAWN_RATE = 1
_MAX_SPAWN_RATE = 10000


def _coerce_int_range(value: Any, default: int, min_value: int, max_value: int) -> int:
    """Convert value to int and clamp into [min_value, max_value]."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(parsed, max_value))


# ─────────────────────────────────────────────────────────────────────────────
# Filtering rules (ported from skills/analyzer.py)
# ─────────────────────────────────────────────────────────────────────────────

_STATIC_EXTENSIONS: Set[str] = {
    ".js",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".map",
    ".webp",
    ".avif",
    ".mp4",
    ".mp3",
    ".webm",
}

_TRACKING_DOMAINS: Set[str] = {
    "google-analytics.com",
    "googletagmanager.com",
    "analytics.google.com",
    "www.google-analytics.com",
    "stats.g.doubleclick.net",
    "facebook.com",
    "connect.facebook.net",
    "graph.facebook.com",
    "px.ads.linkedin.com",
    "snap.licdn.com",
    "bat.bing.com",
    "clarity.ms",
    "hotjar.com",
    "static.hotjar.com",
    "script.hotjar.com",
    "cdn.segment.com",
    "api.segment.io",
    "sentry.io",
    "browser.sentry-cdn.com",
    "mixpanel.com",
    "api-js.mixpanel.com",
    "amplitude.com",
    "api.amplitude.com",
    "fullstory.com",
    "rs.fullstory.com",
    "intercom.io",
    "widget.intercom.io",
    "crisp.chat",
    "client.crisp.chat",
    "hm.baidu.com",
    "tongji.baidu.com",
    "cnzz.com",
    "s4.cnzz.com",
    "s9.cnzz.com",
    "growingio.com",
    "sensors.data",
    "umeng.com",
}

_PROBE_PATTERNS: List[re.Pattern] = [
    re.compile(r"/healthz?$", re.IGNORECASE),
    re.compile(r"/ping$", re.IGNORECASE),
    re.compile(r"/favicon", re.IGNORECASE),
    re.compile(r"/robots\.txt$", re.IGNORECASE),
    re.compile(r"/sitemap.*\.xml$", re.IGNORECASE),
    re.compile(r"/manifest\.json$", re.IGNORECASE),
    re.compile(r"/sw\.js$", re.IGNORECASE),
    re.compile(r"/service-worker", re.IGNORECASE),
    re.compile(r"/sockjs-node", re.IGNORECASE),
    re.compile(r"/__webpack", re.IGNORECASE),
    re.compile(r"/hot-update", re.IGNORECASE),
    re.compile(r"\.chunk\.", re.IGNORECASE),
    re.compile(r"/sourcemap", re.IGNORECASE),
]

_FORWARD_HEADER_KEYS: Set[str] = {
    "authorization",
    "content-type",
    "accept",
    "x-api-key",
    "x-requested-with",
    "x-csrf-token",
    "x-xsrf-token",
}

_JS_SCAN_TIMEOUT_SECONDS = 10.0
_MAX_JS_FILES_TO_SCAN = 20
_MAX_JS_SIZE_BYTES = 1_000_000
_JS_API_LITERAL_RE = re.compile(
    r"""(?P<quote>['"])(?P<url>(?:https?://[^"'`\s]+|/[A-Za-z0-9_\-/\.\?\=&%]*?(?:api|v\d+)[A-Za-z0-9_\-/\.\?\=&%]*))(?P=quote)""",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Internal data class for captured requests
# ─────────────────────────────────────────────────────────────────────────────


class _CapturedRequest:
    """A single network request captured by the browser."""

    __slots__ = ("url", "method", "resource_type", "headers", "post_data", "status")

    def __init__(
        self,
        url: str,
        method: str,
        resource_type: str,
        headers: Dict[str, str],
        post_data: Optional[str] = None,
        status: Optional[int] = None,
    ) -> None:
        self.url = url
        self.method = method.upper()
        self.resource_type = resource_type
        self.headers = headers
        self.post_data = post_data
        self.status = status


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Playwright page analysis
# ─────────────────────────────────────────────────────────────────────────────


def _load_playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is required for page analysis. "
            "Install it with: pip install playwright && playwright install chromium"
        )
    return async_playwright


def _build_context_options(
    target_url: str, browser_context: Optional[List[Dict[str, Any]]]
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    ctx_opts: Dict[str, Any] = {
        "ignore_https_errors": True,
        "user_agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    extra_headers: Dict[str, str] = {}
    cookies_to_add: List[Dict[str, Any]] = []
    if not browser_context:
        return ctx_opts, cookies_to_add

    for item in browser_context:
        item_type = item.get("type", "").lower()
        if item_type == "header":
            extra_headers[item["name"]] = item["value"]
            continue
        if item_type != "cookie":
            continue
        cookie: Dict[str, Any] = {
            "name": item["name"],
            "value": item["value"],
            "url": target_url,
        }
        if "domain" in item:
            cookie["domain"] = item["domain"]
        cookies_to_add.append(cookie)

    if extra_headers:
        ctx_opts["extra_http_headers"] = extra_headers
    return ctx_opts, cookies_to_add


async def _navigate_with_fallback(page: Any, target_url: str) -> None:
    logger.info("Navigating to {} ...", target_url)
    try:
        await page.goto(target_url, wait_until="networkidle", timeout=30000)
    except Exception:
        logger.warning("networkidle timeout, falling back to domcontentloaded")
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.error("Failed to navigate to {}: {}", target_url, e)
            raise


async def _trigger_scroll(page: Any, scroll: bool) -> None:
    if not scroll:
        return
    logger.info("Scrolling page to trigger lazy-loaded APIs...")
    try:
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(800)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(500)
    except Exception as e:
        logger.debug("Scroll error (non-fatal): {}", e)


def _append_captured_response(captured: List[_CapturedRequest], response: Any) -> None:
    req = response.request
    try:
        captured.append(
            _CapturedRequest(
                url=req.url,
                method=req.method,
                resource_type=req.resource_type,
                headers=dict(req.headers) if req.headers else {},
                post_data=req.post_data,
                status=response.status,
            )
        )
    except Exception as e:
        logger.debug("Failed to capture response: {}", e)


async def _launch_browser(p):
    """Launch Chromium with a user-friendly error on failure."""
    try:
        return await p.chromium.launch(headless=True)
    except Exception as e:
        err_msg = str(e).lower()
        if "executable doesn't exist" in err_msg:
            raise RuntimeError(
                "Chromium browser is not installed. "
                "Please run: playwright install --with-deps chromium"
            ) from e
        raise RuntimeError(
            "Failed to launch Chromium browser. "
            "Please ensure Playwright browsers are installed: "
            "playwright install --with-deps chromium"
        ) from e


async def _analyze_page(
    target_url: str,
    *,
    wait_seconds: int = 5,
    scroll: bool = True,
    browser_context: Optional[List[Dict[str, Any]]] = None,
) -> List[_CapturedRequest]:
    """Load the target page in a headless browser and capture XHR/Fetch requests."""
    async_playwright = _load_playwright()
    captured: List[_CapturedRequest] = []
    ctx_opts, cookies_to_add = _build_context_options(target_url, browser_context)

    async with async_playwright() as p:
        browser = await _launch_browser(p)
        context = await browser.new_context(**ctx_opts)
        if cookies_to_add:
            await context.add_cookies(cookies_to_add)

        page = await context.new_page()

        def on_response(response):
            _append_captured_response(captured, response)

        page.on("response", on_response)

        await _navigate_with_fallback(page, target_url)
        await _trigger_scroll(page, scroll)

        logger.info("Waiting {}s for async API calls...", wait_seconds)
        await page.wait_for_timeout(wait_seconds * 1000)
        await browser.close()

    logger.info("Captured {} total network requests", len(captured))
    return captured


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Filtering
# ─────────────────────────────────────────────────────────────────────────────


def _is_static(req: _CapturedRequest) -> bool:
    if req.resource_type in (
        "stylesheet",
        "image",
        "media",
        "font",
        "texttrack",
        "manifest",
        "other",
    ):
        return True
    parsed = urlparse(req.url)
    path = parsed.path.lower()
    return any(path.endswith(ext) for ext in _STATIC_EXTENSIONS)


def _is_tracking(req: _CapturedRequest) -> bool:
    domain = urlparse(req.url).hostname or ""
    return any(domain == td or domain.endswith("." + td) for td in _TRACKING_DOMAINS)


def _is_probe(req: _CapturedRequest) -> bool:
    path = urlparse(req.url).path
    return any(pat.search(path) for pat in _PROBE_PATTERNS)


def _filter_requests(requests: List[_CapturedRequest]) -> List[_CapturedRequest]:
    """Keep only XHR/Fetch data-exchange requests; deduplicate."""
    filtered: List[_CapturedRequest] = []
    seen: Set[str] = set()

    for req in requests:
        if req.resource_type not in ("xhr", "fetch"):
            continue
        if _is_static(req) or _is_tracking(req) or _is_probe(req):
            continue
        parsed = urlparse(req.url)
        dedup_key = f"{req.method}:{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        filtered.append(req)

    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Build discovered API items and loadtest configs
# ─────────────────────────────────────────────────────────────────────────────


def _guess_api_name(url: str, method: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    segments = [s for s in path.split("/") if s and not s.startswith("v")]
    if not segments:
        return f"{method} {parsed.netloc}"
    name_parts = segments[-2:] if len(segments) >= 2 else segments
    return f"{method} /{'/'.join(name_parts)}"


def _extract_forward_headers(headers: Dict[str, str]) -> List[Dict[str, str]]:
    return [
        {"key": k, "value": v}
        for k, v in headers.items()
        if k.lower() in _FORWARD_HEADER_KEYS
    ]


def _build_discovered_apis(
    filtered: List[_CapturedRequest],
) -> List[DiscoveredApiItem]:
    apis: List[DiscoveredApiItem] = []
    for req in filtered:
        apis.append(
            DiscoveredApiItem(
                name=_guess_api_name(req.url, req.method)[:100],
                target_url=req.url,
                method=req.method,
                headers=_extract_forward_headers(req.headers),
                request_body=req.post_data,
                http_status=req.status,
                source="playwright_xhr_fetch",
                confidence="high",
            )
        )
    return apis


def _api_dedup_key(item: DiscoveredApiItem) -> str:
    parsed = urlparse(item.target_url)
    normalized_path = (parsed.path or "/").rstrip("/") or "/"
    return f"{item.method.upper()}:{parsed.scheme}://{parsed.netloc}{normalized_path}"


def _is_url_likely_business_api(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    candidate = _CapturedRequest(
        url=url,
        method="GET",
        resource_type="fetch",
        headers={},
        post_data=None,
        status=None,
    )
    if _is_static(candidate) or _is_tracking(candidate) or _is_probe(candidate):
        return False
    path = (parsed.path or "").lower()
    if "/api/" in path or re.search(r"/v\d+/", path):
        return True
    return False


def _extract_method_hint(js_text: str, start_idx: int, end_idx: int) -> str:
    window_before = js_text[max(0, start_idx - 120) : start_idx].lower()
    window_after = js_text[end_idx : min(len(js_text), end_idx + 120)].lower()
    nearby = f"{window_before} {window_after}"
    if "axios.post" in nearby or "method:'post'" in nearby or 'method:"post"' in nearby:
        return "POST"
    if "axios.put" in nearby or "method:'put'" in nearby or 'method:"put"' in nearby:
        return "PUT"
    if (
        "axios.patch" in nearby
        or "method:'patch'" in nearby
        or 'method:"patch"' in nearby
    ):
        return "PATCH"
    if (
        "axios.delete" in nearby
        or "method:'delete'" in nearby
        or 'method:"delete"' in nearby
    ):
        return "DELETE"
    return "GET"


def _extract_candidate_apis_from_js_text(
    js_text: str, base_page_url: str
) -> List[DiscoveredApiItem]:
    candidates: List[DiscoveredApiItem] = []
    for match in _JS_API_LITERAL_RE.finditer(js_text):
        raw_url = match.group("url")
        full_url = (
            raw_url if raw_url.startswith("http") else urljoin(base_page_url, raw_url)
        )
        if not _is_url_likely_business_api(full_url):
            continue
        method = _extract_method_hint(js_text, match.start(), match.end())
        candidates.append(
            DiscoveredApiItem(
                name=_guess_api_name(full_url, method)[:100],
                target_url=full_url,
                method=method,
                headers=[],
                request_body=None,
                http_status=None,
                source="js_static_scan",
                confidence="medium",
            )
        )
    return candidates


async def _collect_script_urls_from_html(target_url: str) -> List[str]:
    script_urls: List[str] = []
    try:
        timeout = httpx.Timeout(_JS_SCAN_TIMEOUT_SECONDS)
        # verify=False: Target URLs provided by users for load testing may use
        # self-signed certificates in staging/internal environments.
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(target_url)
            resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.debug("Failed to fetch html for js static scan {}: {}", target_url, e)
        return script_urls

    for m in re.finditer(
        r"""<script[^>]+src=(['"])(?P<src>[^'"]+)\1""",
        html,
        flags=re.IGNORECASE,
    ):
        src = m.group("src").strip()
        if not src:
            continue
        script_urls.append(urljoin(target_url, src))
    return script_urls


def _collect_script_urls_from_captured(
    raw_requests: List[_CapturedRequest],
) -> List[str]:
    script_urls: List[str] = []
    for req in raw_requests:
        parsed = urlparse(req.url)
        path = parsed.path.lower()
        if req.resource_type == "script" or path.endswith(".js"):
            script_urls.append(req.url)
    return script_urls


async def _discover_apis_via_js_static_scan(
    target_url: str, raw_requests: List[_CapturedRequest]
) -> List[DiscoveredApiItem]:
    script_url_candidates = _collect_script_urls_from_captured(raw_requests)
    script_url_candidates.extend(await _collect_script_urls_from_html(target_url))

    seen_script_urls: Set[str] = set()
    script_urls: List[str] = []
    for url in script_url_candidates:
        if not url or url in seen_script_urls:
            continue
        seen_script_urls.add(url)
        script_urls.append(url)
        if len(script_urls) >= _MAX_JS_FILES_TO_SCAN:
            break

    if not script_urls:
        return []

    discovered: List[DiscoveredApiItem] = []
    timeout = httpx.Timeout(_JS_SCAN_TIMEOUT_SECONDS)
    # verify=False: Target URLs provided by users for load testing may use
    # self-signed certificates in staging/internal environments.
    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        for script_url in script_urls:
            try:
                resp = await client.get(script_url)
                resp.raise_for_status()
                content = resp.text
                if len(content.encode("utf-8", errors="ignore")) > _MAX_JS_SIZE_BYTES:
                    logger.debug("Skip large JS file for static scan: {}", script_url)
                    continue
                discovered.extend(
                    _extract_candidate_apis_from_js_text(
                        content, base_page_url=target_url
                    )
                )
            except Exception as e:
                logger.debug("Skip js static scan file {}: {}", script_url, e)
                continue

    merged: Dict[str, DiscoveredApiItem] = {}
    for item in discovered:
        merged[_api_dedup_key(item)] = item
    return list(merged.values())


def _merge_discovered_apis(
    runtime_apis: List[DiscoveredApiItem],
    js_apis: List[DiscoveredApiItem],
) -> List[DiscoveredApiItem]:
    merged: Dict[str, DiscoveredApiItem] = {}
    for api in js_apis:
        merged[_api_dedup_key(api)] = api
    for api in runtime_apis:
        # Runtime interception is stronger evidence; overwrite JS candidate.
        merged[_api_dedup_key(api)] = api
    return list(merged.values())


def _build_default_configs(
    apis: List[DiscoveredApiItem],
    concurrent_users: int = 10,
    duration: int = 300,
    spawn_rate: int = 1000,
) -> List[LoadtestConfigItem]:
    """Build loadtest configs with fixed defaults (no LLM)."""
    configs: List[LoadtestConfigItem] = []
    for api in apis:
        tid = f"skills_{uuid.uuid4().hex[:8]}"
        configs.append(
            LoadtestConfigItem(
                temp_task_id=tid,
                name=api.name,
                method=api.method,
                target_url=api.target_url,
                headers=api.headers,
                cookies=[],
                request_body=api.request_body or "",
                concurrent_users=concurrent_users,
                duration=duration,
                spawn_rate=spawn_rate,
                load_mode="fixed",
            )
        )
    return configs


# ─────────────────────────────────────────────────────────────────────────────
# Step 3b — LLM-powered config generation
# ─────────────────────────────────────────────────────────────────────────────

_LLM_CONFIG_PROMPT = """你是一个 Web API 性能测试专家。

下面是从目标网页 {target_url} 中自动抓取到的核心业务 API 列表（JSON 格式）：

```json
{apis_json}
```

请根据每个 API 的 HTTP 方法、URL 路径语义和请求体，为它们分别推荐一个合理的压测配置。

规则：
- GET 请求通常并发量可以更高（100-200），持续时间 300 秒
- POST/PUT 等写操作并发量应适当降低（10-100），持续时间 300 秒
- 登录、注册等认证类 API 并发量应更低（10-50），持续时间 300 秒
- spawn_rate 建议为 concurrent_users 的 100%
- 所有 API 使用 fixed 模式

请严格返回如下 JSON 数组格式（不要包含其他文字）：
```json
[
  {{
    "target_url": "原始 API URL",
    "concurrent_users": 10,
    "duration": 300,
    "spawn_rate": 10
  }}
]
```
"""


async def _generate_configs_via_llm(
    request: Request,
    apis: List[DiscoveredApiItem],
    target_url: str,
) -> Optional[List[Dict[str, Any]]]:
    """Call the system-configured AI service to generate smart loadtest configs."""
    try:
        from service.system_service import get_ai_service_config_internal_svc

        ai_config = await get_ai_service_config_internal_svc(request)
    except Exception:
        logger.info("No AI service configured, skipping LLM config generation")
        return None

    apis_payload = [
        {
            "name": a.name,
            "target_url": a.target_url,
            "method": a.method,
            "request_body": (a.request_body or "")[:500],
            "http_status": a.http_status,
        }
        for a in apis
    ]

    prompt = _LLM_CONFIG_PROMPT.format(
        target_url=target_url,
        apis_json=json.dumps(apis_payload, ensure_ascii=False, indent=2),
    )

    url = f"{ai_config.host}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ai_config.api_key}",
    }
    data = {
        "model": ai_config.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    try:
        timeout = httpx.Timeout(60.0)
        async with httpx.AsyncClient(
            timeout=timeout, verify=ai_config.ssl_verify
        ) as client:
            resp = await client.post(url, headers=headers, json=data)
            resp.raise_for_status()

        content = ""
        choices = resp.json().get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        # Strip thinking tags
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # Extract JSON array from content (handle markdown code fences).
        # Use non-greedy .*? so we don't accidentally swallow text beyond
        # the real closing bracket.  Iterate over all candidate matches and
        # return the first one that parses as a valid JSON array.
        for json_match in re.finditer(r"\[.*?\]", content, re.DOTALL):
            try:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                continue

        logger.warning(
            "LLM response did not contain valid JSON array: {}", content[:300]
        )
        return None

    except Exception as e:
        logger.warning("LLM config generation failed, falling back to defaults: {}", e)
        return None


def _merge_llm_configs(
    apis: List[DiscoveredApiItem],
    llm_configs: List[Dict[str, Any]],
    fallback_concurrent: int = 10,
    fallback_duration: int = 300,
    fallback_spawn_rate: int = 1000,
) -> List[LoadtestConfigItem]:
    """Merge LLM-generated configs with discovered APIs, with fallback defaults."""
    # Index LLM configs by target_url
    llm_map: Dict[str, Dict[str, Any]] = {}
    for cfg in llm_configs:
        url = cfg.get("target_url", "")
        if url:
            llm_map[url] = cfg

    configs: List[LoadtestConfigItem] = []
    for api in apis:
        tid = f"skills_{uuid.uuid4().hex[:8]}"
        llm_cfg = llm_map.get(api.target_url, {})
        concurrent_users = _coerce_int_range(
            llm_cfg.get("concurrent_users", fallback_concurrent),
            fallback_concurrent,
            _MIN_CONCURRENT_USERS,
            _MAX_CONCURRENT_USERS,
        )
        duration = _coerce_int_range(
            llm_cfg.get("duration", fallback_duration),
            fallback_duration,
            _MIN_DURATION_SECONDS,
            _MAX_DURATION_SECONDS,
        )
        spawn_rate = _coerce_int_range(
            llm_cfg.get("spawn_rate", fallback_spawn_rate),
            fallback_spawn_rate,
            _MIN_SPAWN_RATE,
            _MAX_SPAWN_RATE,
        )

        configs.append(
            LoadtestConfigItem(
                temp_task_id=tid,
                name=api.name,
                method=api.method,
                target_url=api.target_url,
                headers=api.headers,
                cookies=[],
                request_body=api.request_body or "",
                concurrent_users=concurrent_users,
                duration=duration,
                spawn_rate=spawn_rate,
                load_mode="fixed",
            )
        )
    return configs


# ─────────────────────────────────────────────────────────────────────────────
# Public API — Service entry point
# ─────────────────────────────────────────────────────────────────────────────


async def analyze_url_svc(
    request: Request, body: AnalyzeUrlRequest
) -> AnalyzeUrlResponse:
    """
    Full pipeline: analyze page → filter → build configs.

    If the system has an LLM configured (AI Service in system config),
    uses LLM to generate smart per-API loadtest configs.
    Otherwise, assigns fixed defaults.
    """
    target_url = body.target_url

    # Build browser context from cookies/headers
    browser_context: Optional[List[Dict[str, Any]]] = None
    ctx_items: List[Dict[str, Any]] = []
    if body.cookies:
        for c in body.cookies:
            ctx_items.append({"type": "cookie", "name": c["name"], "value": c["value"]})
    if body.headers:
        for h in body.headers:
            ctx_items.append({"type": "header", "name": h["name"], "value": h["value"]})
    if ctx_items:
        browser_context = ctx_items

    # ── Step 1: Capture ──
    try:
        raw_requests = await _analyze_page(
            target_url,
            wait_seconds=body.wait_seconds,
            scroll=body.scroll,
            browser_context=browser_context,
        )
    except RuntimeError as e:
        return AnalyzeUrlResponse(
            status="error",
            message=str(e),
            target_url=target_url,
        )
    except Exception as e:
        logger.error("Page analysis failed for {}: {}", target_url, e, exc_info=True)
        return AnalyzeUrlResponse(
            status="error",
            message=f"Failed to analyze page: {str(e)}",
            target_url=target_url,
        )

    # ── Step 2: Filter runtime captured API calls ──
    filtered = _filter_requests(raw_requests)
    logger.info("Filtered: {} → {} core API requests", len(raw_requests), len(filtered))

    # ── Step 3: Build discovered APIs (runtime + JS static scan) ──
    discovered_runtime = _build_discovered_apis(filtered)
    discovered_js = await _discover_apis_via_js_static_scan(target_url, raw_requests)
    discovered = _merge_discovered_apis(discovered_runtime, discovered_js)
    logger.info(
        "Discovered APIs merged: runtime={} js_static={} final={}",
        len(discovered_runtime),
        len(discovered_js),
        len(discovered),
    )

    if not discovered:
        return AnalyzeUrlResponse(
            status="error",
            message=(
                f"No core business API requests found in {target_url}"
                f"(intercepted {len(raw_requests)} requests, no valid JS static candidates)"
            ),
            target_url=target_url,
        )

    # Build analysis summary
    methods_count: Dict[str, int] = {}
    for api in discovered:
        methods_count[api.method] = methods_count.get(api.method, 0) + 1
    method_summary = ", ".join(f"{m}×{c}" for m, c in methods_count.items())
    parsed = urlparse(target_url)
    summary = (
        f"From {parsed.netloc} detected {len(discovered)} core business APIs "
        f"({method_summary}), filtered out static resources and third-party tracking"
    )

    # ── Step 3b: Generate loadtest configs (LLM or defaults) ──
    llm_used = False
    llm_configs = await _generate_configs_via_llm(request, discovered, target_url)

    if llm_configs:
        configs = _merge_llm_configs(
            discovered,
            llm_configs,
            fallback_concurrent=body.concurrent_users,
            fallback_duration=body.duration,
            fallback_spawn_rate=body.spawn_rate,
        )
        llm_used = True
        logger.info("LLM generated configs for {} APIs", len(configs))
    else:
        configs = _build_default_configs(
            discovered,
            concurrent_users=body.concurrent_users,
            duration=body.duration,
            spawn_rate=body.spawn_rate,
        )
        logger.info(
            "Using default configs (concurrent={}, duration={}s) for {} APIs",
            body.concurrent_users,
            body.duration,
            len(configs),
        )

    return AnalyzeUrlResponse(
        status="success",
        message=f"Successfully analyzed {target_url}",
        target_url=target_url,
        analysis_summary=summary,
        discovered_apis=discovered,
        loadtest_configs=configs,
        llm_used=llm_used,
    )
