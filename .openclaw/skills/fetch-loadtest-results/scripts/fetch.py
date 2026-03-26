#!/usr/bin/env python3
"""
fetch-loadtest-results skill — output LMeterX report URLs.

Supports: --task-id / --task-ids / --batch-id / --batch-file
Generates report URLs based on task type:
  - common (HTTP API):  {BASE_URL}/http-results/{task_id}
  - llm    (LLM API):   {BASE_URL}/results/{task_id}
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── shared lib ──────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _lib.client import ARTIFACT_ROOT, BASE_URL  # noqa: E402

# ── task resolution ─────────────────────────────────────────────────────────


def _load_batch(
    batch_id: Optional[str], batch_file: Optional[str]
) -> Tuple[str, List[Dict], str]:
    """Load batch manifest and return (label, task_metas, task_type)."""
    if batch_file:
        path = Path(batch_file).expanduser().resolve()
    elif batch_id:
        path = ARTIFACT_ROOT / f"{batch_id}.json"
    else:
        return "", [], "http"

    if not path.exists():
        raise FileNotFoundError(f"Batch file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = [
        {
            "task_id": t["task_id"],
            "name": t.get("name", ""),
            "target_url": t.get("target_url", ""),
        }
        for t in data.get("tasks", [])
        if t.get("task_id")
    ]
    task_type = data.get("task_type", "http")
    return data.get("batch_id", batch_id or ""), tasks, task_type


def _collect_tasks(args) -> Tuple[str, List[Dict], str]:
    """Resolve task identifiers and task_type from CLI arguments.

    Returns (label, task_metas, task_type).
    """
    task_type = getattr(args, "task_type", "http") or "http"

    if args.task_ids:
        ids = [x.strip() for x in args.task_ids.split(",") if x.strip()]
        return "custom-task-ids", [{"task_id": tid} for tid in ids], task_type
    if args.task_id:
        return args.task_id, [{"task_id": args.task_id}], task_type

    label, metas, batch_task_type = _load_batch(args.batch_id, args.batch_file)
    # CLI --task-type overrides batch manifest; otherwise use batch value
    if task_type == "http" and batch_task_type:
        task_type = batch_task_type
    return label, metas, task_type


# ── URL generation ─────────────────────────────────────────────────────────


def _report_url(task_id: str, task_type: str) -> str:
    """Build the report page URL for a given task."""
    base = BASE_URL.rstrip("/")
    if task_type == "llm":
        return f"{base}/results/{task_id}"
    return f"{base}/http-results/{task_id}"


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="LMeterX: 获取压测报告地址")
    parser.add_argument("--task-id", help="Single task ID")
    parser.add_argument("--task-ids", help="Comma-separated task IDs")
    parser.add_argument("--batch-id", help="Batch ID from run-web-loadtest")
    parser.add_argument("--batch-file", help="Batch manifest JSON path")
    parser.add_argument(
        "--task-type",
        choices=["http", "llm"],
        default="http",
        help="Task type: 'http' for HTTP API, 'llm' for LLM API (default: http; auto-detected from batch file)",
    )
    args = parser.parse_args()

    provided = sum(
        [
            bool(args.task_id),
            bool(args.task_ids),
            bool(args.batch_id),
            bool(args.batch_file),
        ]
    )
    if provided != 1:
        print(
            "❌ 必须且只能提供一个: --task-id / --task-ids / --batch-id / --batch-file"
        )
        sys.exit(1)

    try:
        label, metas, task_type = _collect_tasks(args)
    except Exception as e:
        print(f"❌ 解析输入失败: {e}")
        sys.exit(1)

    if not metas:
        print("❌ 未找到任何任务")
        sys.exit(1)

    # ── Output report URLs ─────────────────────────────────────────────────
    task_type_label = "LLM API" if task_type == "llm" else "HTTP API"

    print(f"\n{'=' * 60}")
    print(f"  LMeterX 压测报告")
    print(f"{'=' * 60}")
    print(f"  任务类型: {task_type_label}")
    if label and label != "custom-task-ids":
        print(f"  批次 ID:  {label}")
    print(f"  任务数量: {len(metas)}")
    print(f"{'=' * 60}\n")

    for meta in metas:
        tid = meta["task_id"]
        name = meta.get("name", "")
        url = _report_url(tid, task_type)
        if name:
            print(f"  📊 {name}")
            print(f"     Task ID: {tid}")
            print(f"     报告地址: {url}\n")
        else:
            print(f"  📊 Task ID: {tid}")
            print(f"     报告地址: {url}\n")

    print(f"{'=' * 60}")
    print()


if __name__ == "__main__":
    main()
