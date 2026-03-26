#!/usr/bin/env python3
"""
run-web-loadtest skill — thin client for LMeterX backend.

Workflow:
  1. POST /api/skills/analyze-url  → discover APIs + generate loadtest configs
  2. POST /api/http-tasks/test   → connectivity pre-check
  3. POST /api/http-tasks        → create loadtest tasks

All crawling, filtering and config-generation logic lives on the backend;
this script only calls APIs, prints progress, and persists a batch manifest.
"""

import argparse
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

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
    print_failure_summary,
)

TIMEOUT = 120.0  # analysis can take a while (Playwright on backend)
MAX_WORKERS = 10  # max concurrent pre-check / create threads


# ── helpers ─────────────────────────────────────────────────────────────────


def _print_json(label: str, data: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _persist_batch(
    batch_id: str,
    source_url: str,
    configs_count: int,
    passed_count: int,
    tasks: list,
) -> Path:
    """Save a batch manifest JSON for later use by fetch-loadtest-results."""
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_ROOT / f"{batch_id}.json"
    path.write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "source_url": source_url,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "discovered_api_count": configs_count,
                "precheck_passed_count": passed_count,
                "tasks": tasks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


# ── concurrent helpers ──────────────────────────────────────────────────────


def _precheck_one(client: httpx.Client, cfg: Dict) -> Tuple[Dict, bool, str, str, str]:
    """Pre-check connectivity for a single API config.

    Returns (cfg, passed, message, category_key, detail).
    ``category_key`` and ``detail`` are non-empty only when *passed* is False.
    """
    name = cfg.get("name", cfg.get("target_url", ""))
    try:
        test_resp = client.post(
            f"{BASE_URL}/api/http-tasks/test",
            headers=headers(),
            json={
                "method": cfg["method"],
                "target_url": cfg["target_url"],
                "headers": cfg.get("headers", []),
                "cookies": cfg.get("cookies", []),
                "request_body": cfg.get("request_body", ""),
            },
        )
        test_resp.raise_for_status()
        test_data = test_resp.json()

        if test_data.get("status") == "success":
            http_code = test_data.get("http_status")
            # 2xx/3xx → passed; 4xx/5xx → failed with classified reason
            if isinstance(http_code, int) and http_code >= 400:
                cat_key, label, _ = classify_precheck_failure(http_status=http_code)
                return (
                    cfg,
                    False,
                    f"❌ {name} → HTTP {http_code} ({label})",
                    cat_key,
                    f"HTTP {http_code}",
                )
            return (cfg, True, f"✅ {name} → HTTP {http_code or '?'}", "", "")
        else:
            error = test_data.get("error", "Failed")
            cat_key, label, _ = classify_precheck_failure(error_msg=error)
            return (cfg, False, f"❌ {name} → {error}", cat_key, error)
    except Exception as e:
        cat_key, label, _ = classify_precheck_failure(error_msg=str(e))
        return (cfg, False, f"❌ {name} → {e}", cat_key, str(e))


def _create_one(
    client: httpx.Client, cfg: Dict, args: argparse.Namespace
) -> Tuple[str, bool, str, Dict]:
    """Create a single loadtest task.

    Returns (name, success, message, task_info_dict).
    """
    name = cfg.get("name", "")
    try:
        create_resp = client.post(
            f"{BASE_URL}/api/http-tasks",
            headers=headers(),
            json={
                "temp_task_id": cfg["temp_task_id"],
                "name": cfg["name"],
                "method": cfg["method"],
                "target_url": cfg["target_url"],
                "headers": cfg.get("headers", []),
                "cookies": cfg.get("cookies", []),
                "request_body": cfg.get("request_body", ""),
                "concurrent_users": bounded_int(
                    cfg.get("concurrent_users", 50), 50, 1, 5000
                ),
                "duration": bounded_int(cfg.get("duration", 300), 300, 1, 172800),
                "spawn_rate": bounded_int(cfg.get("spawn_rate", 30), 30, 1, 10000),
                "load_mode": cfg.get("load_mode", "fixed"),
            },
        )
        create_resp.raise_for_status()
        result = create_resp.json()
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
                "duration": cfg.get("duration", args.duration),
            },
        )
    except Exception as e:
        return (name, False, f"❌ {name} → {e}", {})


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="LMeterX: Run API Load Test")
    parser.add_argument("--url", required=True, help="Target webpage URL to analyze")
    parser.add_argument(
        "--concurrent-users", type=int, default=50, help="Concurrent users (default 50)"
    )
    parser.add_argument(
        "--duration", type=int, default=300, help="Duration in seconds (default 300)"
    )
    parser.add_argument(
        "--spawn-rate", type=int, default=30, help="Spawn rate (default 30)"
    )
    args = parser.parse_args()

    # ── Step 0: Preflight check ──────────────────────────────────────────
    print("\n🔑 Step 0: 检查后端连通性与认证状态 ...")
    preflight_check()
    print("   ✅ 后端连通，认证正常\n")

    batch_id = f"batch_{uuid.uuid4().hex[:10]}"

    with httpx.Client(timeout=TIMEOUT, verify=False) as client:
        # ── Step 1: Analyze URL ─────────────────────────────────────────────
        print(f"🔍 Step 1/3: 分析页面 {args.url} ...")
        analyze_resp = client.post(
            f"{BASE_URL}/api/skills/analyze-url",
            headers=headers(),
            json={
                "target_url": args.url,
                "concurrent_users": args.concurrent_users,
                "duration": args.duration,
                "spawn_rate": args.spawn_rate,
            },
        )
        analyze_resp.raise_for_status()
        analyze_data = analyze_resp.json()
        _print_json("分析结果", analyze_data)

        if analyze_data.get("status") != "success":
            print(f"\n❌ 分析失败: {analyze_data.get('message')}")
            sys.exit(1)

        configs: List[Dict] = analyze_data.get("loadtest_configs", [])
        if not configs:
            print("\n⚠️ 未发现可测试的 API。")
            sys.exit(0)

        print(f"\n✅ 发现 {len(configs)} 个候选 API")
        if analyze_data.get("llm_used"):
            print("   (已使用 LLM 智能生成压测配置)")

        # ── Step 2: Pre-check (concurrent) ──────────────────────────────────
        n_workers = min(MAX_WORKERS, len(configs))
        print(
            f"\n🔗 Step 2/3: 并发预检 {len(configs)} 个 API 的连通性 (workers={n_workers}) ..."
        )
        passing: List[Dict] = []
        failures: List[Tuple[str, str, str]] = []  # (name, cat_key, detail)
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(_precheck_one, client, cfg): cfg for cfg in configs}
            for future in as_completed(futures):
                cfg, ok, msg, cat_key, detail = future.result()
                print(f"   {msg}")
                if ok:
                    passing.append(cfg)
                else:
                    api_name = cfg.get("name", cfg.get("target_url", "?"))
                    failures.append((api_name, cat_key, detail))

        print(f"\n📊 预检通过: {len(passing)}/{len(configs)}")

        if failures:
            print_failure_summary(failures)

        if not passing:
            print("\n❌ 所有 API 预检失败，流程终止。")
            sys.exit(1)

        # ── Step 3: Create tasks (concurrent) ──────────────────────────────
        n_workers = min(MAX_WORKERS, len(passing))
        print(
            f"\n🚀 Step 3/3: 并发创建 {len(passing)} 个压测任务 (workers={n_workers}) ..."
        )
        created_tasks: List[Dict] = []
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            create_futures = {
                pool.submit(_create_one, client, cfg, args): cfg for cfg in passing
            }
            for cf in as_completed(create_futures):
                name, ok, msg, task_info = cf.result()
                print(f"   {msg}")
                if ok:
                    created_tasks.append(task_info)

        # ── Summary ─────────────────────────────────────────────────────────
        manifest_path = None
        if created_tasks:
            manifest_path = _persist_batch(
                batch_id, args.url, len(configs), len(passing), created_tasks
            )

        task_ids = [t["task_id"] for t in created_tasks]
        print(f"\n{'=' * 60}")
        print("  SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Batch ID:      {batch_id}")
        print(f"  Target URL:    {args.url}")
        print(f"  APIs Found:    {len(configs)}")
        print(f"  Pre-check OK:  {len(passing)}")
        print(f"  Tasks Created: {len(task_ids)}")
        if task_ids:
            print(f"  Task IDs:      {', '.join(task_ids)}")
        if manifest_path:
            print(f"  Batch File:    {manifest_path}")

        if task_ids:
            print(f"\n💡 使用 fetch-loadtest-results 拉取报告:")
            print(f"   python scripts/fetch.py --batch-id {batch_id} --watch")
        else:
            print("\n⚠️ 未创建任何任务。")

        print()


if __name__ == "__main__":
    main()
