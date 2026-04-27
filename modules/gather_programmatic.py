"""Programmatic gather implementation for external-learning.

New architecture only:
- fetch RSS / DeepXiv / simple web pages
- score with structural signals only
- write normalized candidate markdown
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import requests

# Use runtime_config for workspace path resolution
try:
    import sys
    from pathlib import Path
    _parent = Path(__file__).resolve().parent.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))
    from runtime_config import WORKSPACE as _WORKSPACE
    WORKSPACE_ROOT = _WORKSPACE
except ImportError:
    WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_ROOT = Path(__file__).parent.parent
CONFIG_PATH = SKILL_ROOT / "modules" / "sources" / "source_config.json"
LEARNING_DIR = WORKSPACE_ROOT / "memory" / "learning"
HEARTBEAT_STATE = WORKSPACE_ROOT / "memory" / "heartbeat-state.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"}

_DEEPXIV_TOKEN = None


def _get_deepxiv_token():
    global _DEEPXIV_TOKEN
    if _DEEPXIV_TOKEN:
        return _DEEPXIV_TOKEN
    env_file = Path.home() / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DEEPXIV_TOKEN="):
                _DEEPXIV_TOKEN = line.split("=", 1)[1].strip()
                return _DEEPXIV_TOKEN
    return None


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_heartbeat_state() -> dict:
    if HEARTBEAT_STATE.exists():
        with open(HEARTBEAT_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"lastChecks": {}}


def update_heartbeat_state(source_id: str):
    state = load_heartbeat_state()
    state.setdefault("lastChecks", {})[source_id] = datetime.now().isoformat()
    HEARTBEAT_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(HEARTBEAT_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def score_item(title: str, summary: str, url: str, source: dict[str, Any]) -> tuple[float, list[str]]:
    title_text = (title or "").strip()
    summary_text = (summary or "").strip()
    lower_title = title_text.lower()
    lower_summary = summary_text.lower()
    lower_url = (url or "").lower()

    score = 3.5
    reasons = []

    source_type = source.get("type", "")
    priority = source.get("priority", 2)
    score += max(0.0, 1.2 - 0.2 * max(priority - 1, 0))
    reasons.append(f"源优先级 P{priority}")

    if source_type == "deepxiv":
        score += 2.2
        reasons.append("论文源")
    elif source_type == "fetch":
        score += 1.4
        reasons.append("网页直抓")
    elif source_type == "rss":
        score += 1.0
        reasons.append("RSS源")

    if 60 <= len(summary_text) <= 400:
        score += 1.1
        reasons.append("摘要信息充足")
    elif len(summary_text) >= 25:
        score += 0.5
        reasons.append("摘要可用")

    if len(title_text) >= 18:
        score += 0.4
        reasons.append("标题信息量较高")

    if "arxiv.org/abs/" in lower_url:
        score += 1.6
        reasons.append("论文详情页")
    elif "github.com/" in lower_url:
        score += 1.2
        reasons.append("代码仓库")
    elif any(host in lower_url for host in ["huggingface.co", "paperswithcode.com"]):
        score += 1.0
        reasons.append("模型/论文生态源")

    if any(token in lower_title for token in ["benchmark", "evaluation", "framework", "system", "agent", "memory", "reasoning", "guardrail"]):
        score += 0.9
        reasons.append("标题像方法/评测/系统工作")

    if any(token in lower_summary for token in ["abstract", "we present", "we propose", "benchmark", "evaluate", "results"]):
        score += 0.8
        reasons.append("摘要像研究型内容")

    if any(token in lower_title for token in ["weekly", "podcast", "newsletter", "digest"]):
        score -= 1.0
        reasons.append("偏资讯汇总")

    return round(min(max(score, 0.0), 10.0), 1), reasons[:4]


def build_reason(title: str, summary: str, url: str, source: dict[str, Any], score: float) -> str:
    _, reasons = score_item(title, summary, url, source)
    if reasons:
        return f"{'; '.join(reasons)}; 综合分 {score:.1f}"
    return f"结构信号通过; 综合分 {score:.1f}"


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidates:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        canonical = url.rstrip("/")
        existing = deduped.get(canonical)
        if existing is None or item.get("score", 0) > existing.get("score", 0):
            deduped[canonical] = item
    return sorted(deduped.values(), key=lambda x: x.get("score", 0), reverse=True)


def fetch_rss(source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        feed = feedparser.parse(source["url"])
        candidates = []
        for entry in feed.entries[:15]:
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            score, _ = score_item(title, summary, link, source)
            if score < 5:
                continue
            candidates.append({
                "title": title[:80],
                "url": link,
                "description": summary[:150],
                "score": score,
                "reason": build_reason(title, summary, link, source, score),
                "source": source["id"],
                "published": entry.get("published", ""),
            })
        return dedupe_candidates(candidates)
    except Exception as exc:
        print(f"[fetch_rss] Error for {source['name']}: {exc}")
        return []


def fetch_github_trending(source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        res = requests.get(source["url"], headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return []
        pattern = re.compile(r'<article[^>]*>.*?<h2[^>]*>.*?<a[^>]*href="(/[^"]+)"[^>]*>.*?</a>.*?</h2>.*?<p[^>]*>([^<]*)</p>', re.DOTALL)
        candidates = []
        for match in pattern.finditer(res.text):
            path = match.group(1)
            desc = match.group(2).strip()
            title = path.split('/')[-1]
            url = f"https://github.com{path}"
            score, _ = score_item(title, desc, url, source)
            if score < 5:
                continue
            candidates.append({
                "title": path[1:],
                "url": url,
                "description": desc[:100],
                "score": score,
                "reason": build_reason(title, desc, url, source, score),
                "source": source["id"],
                "published": datetime.now().isoformat(),
            })
        return dedupe_candidates(candidates)[:10]
    except Exception as exc:
        print(f"[fetch_github] Error: {exc}")
        return []


def fetch_deepxiv(source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from deepxiv_sdk import Reader
    except ImportError:
        print("[fetch_deepxiv] deepxiv-sdk not installed, skip")
        return []

    token = _get_deepxiv_token()
    if not token:
        print("[fetch_deepxiv] No DEEPXIV_TOKEN found in ~/.env, skip")
        return []

    queries = source.get("queries", ["AI agent"])
    size_per_query = source.get("size_per_query", 10)
    date_from_str = (datetime.now() - timedelta(days=source.get("date_from_days", 7))).strftime("%Y-%m-%d")
    reader = Reader(token=token)
    seen_ids = set()
    candidates = []

    for query in queries:
        try:
            results = reader.search(query, size=size_per_query, date_from=date_from_str)
            for paper in results.get("results", []):
                arxiv_id = paper.get("arxiv_id", "")
                if not arxiv_id or arxiv_id in seen_ids:
                    continue
                seen_ids.add(arxiv_id)
                title = paper.get("title", "")
                abstract = paper.get("abstract", "")
                url = f"https://arxiv.org/abs/{arxiv_id}"
                score, _ = score_item(title, abstract, url, source)
                if score < 5:
                    continue
                brief = {}
                try:
                    brief = reader.brief(arxiv_id) or {}
                except Exception:
                    pass
                description = (brief.get("tldr") or abstract)[:200]
                candidates.append({
                    "title": title[:80],
                    "url": url,
                    "description": description,
                    "score": score,
                    "reason": build_reason(title, description, url, source, score),
                    "source": source["id"],
                    "published": paper.get("publish_at", "")[:10],
                    "arxiv_id": arxiv_id,
                    "github_url": brief.get("github_url", ""),
                })
        except Exception as exc:
            print(f"[fetch_deepxiv] Error for query '{query}': {exc}")

    return dedupe_candidates(candidates)


def fetch_web(source: dict[str, Any]) -> list[dict[str, Any]]:
    if "github" in source["id"].lower():
        return fetch_github_trending(source)
    return []


def write_candidates_markdown(source_id: str, name: str, candidates: list[dict[str, Any]], date_str: str):
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    markdown_path = LEARNING_DIR / f"candidates-{source_id}-{date_str}.md"
    jsonl_path = LEARNING_DIR / f"candidates-{source_id}-{date_str}.jsonl"

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for candidate in candidates:
            f.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write(f"# {name} 候选清单 {date_str}\n\n")
        f.write(f"结构化数据: `{jsonl_path.name}`\n\n")
        f.write("| # | 标题 | URL | 分数 | 理由 | 发布时间 |\n")
        f.write("|---|------|-----|------|------|----------|\n")
        for i, c in enumerate(candidates, 1):
            published = str(c.get("published", ""))[:10]
            reason = str(c.get("reason", ""))[:80].replace("|", "/")
            title = str(c.get("title", "")).replace("|", "/")
            url = str(c.get("url", "")).replace("|", "%7C")
            f.write(f"| {i} | {title} | {url} | {c.get('score', 0)} | {reason} | {published} |\n")
    update_heartbeat_state(source_id)
    print(f"[gather] Written {len(candidates)} candidates to {markdown_path} and {jsonl_path}")


def gather(force_all: bool = False) -> dict[str, list[dict[str, Any]]]:
    config = load_config()
    sources = config.get("sources", [])
    date_str = datetime.now().strftime("%Y-%m-%d")
    results = {}

    for source in sources:
        sid = source["id"]
        interval = source.get("interval_hours", 24)
        if not force_all:
            last_time = load_heartbeat_state().get("lastChecks", {}).get(sid)
            if last_time:
                try:
                    last_dt = datetime.fromisoformat(last_time)
                    if (datetime.now() - last_dt).total_seconds() < interval * 3600:
                        continue
                except Exception:
                    pass
        print(f"[gather] Fetching: {source['name']} ({source['type']})")
        candidates = []
        if source["type"] == "rss":
            candidates = fetch_rss(source)
        elif source["type"] == "deepxiv":
            candidates = fetch_deepxiv(source)
        elif source["type"] == "fetch":
            candidates = fetch_web(source)
        if candidates:
            results[sid] = candidates
            write_candidates_markdown(sid, source["name"], candidates, date_str)
    return results


if __name__ == "__main__":
    import sys
    results = gather(force_all="--force" in sys.argv)
    total = sum(len(v) for v in results.values())
    print(f"\nTotal: {total} candidates from {len(results)} sources")
