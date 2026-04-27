"""External learning gather entry — 纯程序化采集，无 LLM。

流程：抓取 → 评分(规则) → 写 JSONL → orchestrator 心跳桥接

不调用 MiniMax/GPT54。深读和 judge 由主 Agent 直接做。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .gather_programmatic import fetch_deepxiv, fetch_rss, fetch_web, write_candidates_markdown
except ImportError:
    from gather_programmatic import fetch_deepxiv, fetch_rss, fetch_web, write_candidates_markdown

try:
    from runtime_config import WORKSPACE as WORKSPACE_ROOT
except ImportError:
    WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent

SKILL_ROOT = Path(__file__).parent.parent
CONFIG_PATH = SKILL_ROOT / "modules" / "sources" / "source_config.json"
LEARNING_DIR = WORKSPACE_ROOT / "memory" / "learning"
HEARTBEAT_STATE = WORKSPACE_ROOT / "memory" / "heartbeat-state.json"
SEEN_URLS_PATH = WORKSPACE_ROOT / "memory" / "learning" / "seen-urls.json"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_heartbeat_state() -> dict:
    if HEARTBEAT_STATE.exists():
        with open(HEARTBEAT_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"lastChecks": {}}


def load_seen_urls() -> set[str]:
    if not SEEN_URLS_PATH.exists():
        return set()
    try:
        data = json.loads(SEEN_URLS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(data, list):
        return {str(url) for url in data if url}
    if isinstance(data, dict):
        return {str(url) for url in data.get("urls", []) if url}
    return set()


def save_seen_urls(urls: set[str]) -> None:
    SEEN_URLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"urls": sorted(urls), "count": len(urls), "updated_at": datetime.now().isoformat()}
    SEEN_URLS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def filter_new_items(items: list[dict[str, Any]], seen_urls: set[str]) -> list[dict[str, Any]]:
    fresh = []
    for item in items:
        url = str(item.get("url", "")).strip().rstrip("/")
        if not url or url in seen_urls:
            continue
        fresh.append(item)
    return fresh


def mark_seen(items: list[dict[str, Any]], seen_urls: set[str]) -> set[str]:
    for item in items:
        url = str(item.get("url", "")).strip().rstrip("/")
        if url:
            seen_urls.add(url)
    save_seen_urls(seen_urls)
    return seen_urls


def should_update_source(source_id: str, interval_hours: int) -> bool:
    state = load_heartbeat_state()
    last_check_str = state.get("lastChecks", {}).get(source_id)
    if not last_check_str:
        return True
    try:
        last_check = datetime.fromisoformat(last_check_str)
        return datetime.now() - last_check > timedelta(hours=interval_hours)
    except Exception:
        return True


def get_pending_sources(force_all: bool = False) -> list[dict[str, Any]]:
    config = load_config()
    pending = []
    for source in config.get("sources", []):
        if force_all or should_update_source(source["id"], source.get("interval_hours", 24)):
            pending.append(source)
    return pending


def merge_all_candidates(date_str: str | None = None) -> list[dict[str, Any]]:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    all_candidates = []
    for filepath in LEARNING_DIR.glob(f"candidates-*-{date_str}.jsonl"):
        for line in filepath.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                all_candidates.append(item)

    seen = set()
    deduped = []
    for candidate in all_candidates:
        url = candidate.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(candidate)

    deduped.sort(key=lambda x: x.get("score", 0), reverse=True)
    return deduped


def _fetch_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    source_type = source.get("type")
    if source_type == "rss":
        return fetch_rss(source)
    if source_type == "deepxiv":
        return fetch_deepxiv(source)
    if source_type == "fetch":
        return fetch_web(source)
    return []


def gather(force_all: bool = False, only_new: bool = True) -> dict[str, list[dict[str, Any]]]:
    print("🧠 启动 external-learning 程序化采集...")
    date_str = datetime.now().strftime("%Y-%m-%d")
    results: dict[str, list[dict[str, Any]]] = {}
    all_items: list[dict[str, Any]] = []
    fetched_count = 0
    seen_urls = load_seen_urls()

    for source in get_pending_sources(force_all=force_all):
        print(f"[gather] Fetching: {source['name']} ({source['type']})")
        items = _fetch_source(source)
        fetched_count += len(items)
        if only_new:
            items = filter_new_items(items, seen_urls)
        if not items:
            continue
        results[source["id"]] = items
        all_items.extend(items)
        write_candidates_markdown(source["id"], source["name"], items, date_str)
        seen_urls = mark_seen(items, seen_urls)

    if only_new:
        print(f"📡 采集完成：抓取 {fetched_count} 条，新增 {len(all_items)} 条。")
    else:
        print(f"📡 采集完成：共获取 {len(all_items)} 条。")

    # 高评分候选摘要（供主 Agent 深读挑选）
    high_score = [c for c in all_items if c.get("score", 0) >= 8.0]
    if high_score:
        high_score.sort(key=lambda x: x.get("score", 0), reverse=True)
        print(f"\n🎯 高评分候选（≥8 分）共 {len(high_score)} 条：")
        for i, c in enumerate(high_score[:10], 1):
            print(f"  {i}. [{c.get('score', 0):.1f}] {c.get('title', '?')[:80]}")
            print(f"     {c.get('url', '')}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="External Learning — 纯程序化采集")
    parser.add_argument("--force", action="store_true", help="忽略间隔限制，全量抓取")
    parser.add_argument("--list", action="store_true", help="列出待采集信息源")
    parser.add_argument("--all", action="store_true", help="包含已见过的 URL")
    args = parser.parse_args()

    if args.list:
        for source in get_pending_sources(force_all=args.force):
            print(f"- {source['id']} ({source.get('type', 'unknown')})")
    else:
        gather(force_all=args.force, only_new=not args.all)
