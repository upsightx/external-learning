"""Canonical gather entry for external-learning.

New architecture only:
- gather sources programmatically
- write candidate markdown
- expose merged candidates for MiniMax reading and GPT54 judgment
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

WORKSPACE_ROOT = Path("/root/.openclaw/workspace")
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

    # Older candidate markdown files are display-only. Keep a minimal reader so
    # existing same-day files remain usable, but new writes use JSONL above.
    for filepath in LEARNING_DIR.glob(f"candidates-*-{date_str}.md"):
        lines = filepath.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) < 4:
            continue
        for line in lines[2:]:
            if line.startswith("|") and not line.startswith("| #"):
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 6:
                    try:
                        all_candidates.append({
                            "title": parts[1],
                            "url": parts[2],
                            "score": float(parts[3]),
                            "reason": parts[4],
                            "published": parts[5],
                        })
                    except Exception:
                        continue

    seen = set()
    deduped = []
    for candidate in all_candidates:
        url = candidate.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(candidate)

    deduped.sort(key=lambda x: x.get("score", 0), reverse=True)
    return deduped


def generate_evolution_proposals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    proposals = []
    for item in items:
        score = item.get("score", 0)
        if score >= 8.5:
            priority = "P0" if score >= 9.5 else "P1"
            proposals.append({
                "id": f"prop_{datetime.now().strftime('%Y%m%d')}_{hash(item.get('url', '')) % (10**6):06d}",
                "source_url": item.get("url"),
                "type": "RESEARCH_PAPER" if "arxiv" in item.get("url", "") else "ENGINEERING_INSIGHT",
                "priority": priority,
                "summary": item.get("reason", "")[:200],
                "target_module": "external-learning",
                "change_description": item.get("reason", "")[:200],
                "created_at": datetime.now().isoformat(),
                "status": "pending_review",
            })
    return proposals


def push_to_evolution(proposals: list[dict[str, Any]]):
    if not proposals:
        print("ℹ️ 本次扫描未发现新的高价值进化提案。")
        return

    try:
        from proposal_bridge import process_learning_items
        result = process_learning_items(proposals)
        print(
            f"🚀 proposal_bridge 处理完成: evidence={result.get('evidence_recorded', 0)}, "
            f"proposals={result.get('proposals_created', 0)}, "
            f"attached={result.get('evidence_attached', 0)}, "
            f"orchestrator={'triggered' if result.get('orchestrator_triggered') else 'no'}"
        )
    except Exception as exc:
        print(f"⚠️ proposal_bridge 失败: {exc}")


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
    print("🧠 启动 external-learning 统一扫描流程...")
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
        print(f"📡 采集完成：共获取 {len(all_items)} 条技术情报。")
    proposals = generate_evolution_proposals(all_items)
    push_to_evolution(proposals)
    return results


def run_pipeline(force_all: bool = False, only_new: bool = True):
    return gather(force_all=force_all, only_new=only_new)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="External Learning Gather Module")
    parser.add_argument("--force", action="store_true", help="Force fetch all sources")
    parser.add_argument("--list", action="store_true", help="List pending sources")
    parser.add_argument("--all", action="store_true", help="Process already-seen URLs too")
    args = parser.parse_args()

    if args.list:
        for source in get_pending_sources(force_all=args.force):
            print(f"- {source['id']} ({source.get('type', 'unknown')})")
    else:
        run_pipeline(force_all=args.force, only_new=not args.all)
