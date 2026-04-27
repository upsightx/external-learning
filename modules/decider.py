"""Final decision stage for external-learning.

New architecture only:
- MiniMax reads broadly and outputs reading cards
- GPT54 performs the final keep/drop decision on those cards
The final decision always comes from GPT54 judgment.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

try:
    from .content_fetcher import enrich_candidates_with_content
    from .minimax_reader import generate_reading_cards
    from .minimax_screener import screen_candidates
except ImportError:
    from content_fetcher import enrich_candidates_with_content
    from minimax_reader import generate_reading_cards
    from minimax_screener import screen_candidates


def build_llm_judgment_prompt(items: List[Dict[str, Any]], threshold: float = 8.0, max_count: int = 15) -> str:
    compact_items = []
    for idx, item in enumerate(items, 1):
        compact_items.append({
            "id": idx,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "score": item.get("score", 0),
            "reader_score": item.get("reader_score", item.get("score", 0)),
            "reader_topic": item.get("reader_topic", ""),
            "reader_summary": item.get("reader_summary", ""),
            "reader_model_relevance": item.get("reader_model_relevance", "medium"),
            "reader_next_action": item.get("reader_next_action", "observe"),
            "reader_rationale": item.get("reader_rationale", ""),
            "source": item.get("source", ""),
        })

    payload = json.dumps(compact_items, ensure_ascii=False, indent=2)
    return f"""
你负责 external-learning 的最终决策。MiniMax 已经做完初读，你只看初读卡片做高质量拍板。

目标：从 reading cards 中选出最值得进入深读阶段的条目。

决策原则：
1. 优先：对 AI 模型、Agent、记忆、推理、评测、工具链、系统工程有直接启发
2. 优先：对当前系统或产品方向有强迁移价值
3. 降权：泛资讯、主题偏离主线、初读结论空泛、不可落地
4. 不要重复 MiniMax 的摘要，直接做最终判断

输出 JSON：
- items: [
  {{
    "id": 1,
    "final_score": 0-10,
    "decision": "keep" | "drop",
    "rationale": "一句话中文理由"
  }}
]

硬约束：
- 只保留 final_score >= {threshold} 的条目
- 最多保留 {max_count} 条
- 输出必须是合法 JSON，不能带 markdown

reading cards:
{payload}
""".strip()


def apply_llm_judgment(items: List[Dict[str, Any]], judgment: Dict[str, Any], threshold: float = 8.0, max_count: int = 15) -> List[Dict[str, Any]]:
    item_map = {idx: dict(item) for idx, item in enumerate(items, 1)}
    decisions = judgment.get("items", [])
    selected = []

    for decision in decisions:
        idx = decision.get("id")
        if idx not in item_map:
            continue
        item = item_map[idx]
        item["final_score"] = float(decision.get("final_score", item.get("reader_score", item.get("score", 0))))
        item["final_decision"] = decision.get("decision", "drop")
        item["final_rationale"] = decision.get("rationale", "")
        if item["final_decision"] == "keep" and item["final_score"] >= threshold:
            selected.append(item)

    selected.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return selected[:max_count]


def select_for_deep_read(summaries: List[Dict[str, Any]], threshold: float = 8.0, max_count: int = 15) -> List[Dict[str, Any]]:
    screen_keep = max(max_count * 5, 25)
    read_keep = max(max_count * 2, 15)

    screened = screen_candidates(summaries, max_keep=screen_keep)
    if not screened:
        return []

    enriched = enrich_candidates_with_content(screened)
    reading_cards = generate_reading_cards(enriched, max_keep=read_keep)
    if not reading_cards:
        return []

    try:
        from .llm_decider import run_final_judgment
    except ImportError:
        from llm_decider import run_final_judgment

    prompt = build_llm_judgment_prompt(reading_cards, threshold=threshold, max_count=max_count)
    judgment = run_final_judgment(prompt)
    return apply_llm_judgment(reading_cards, judgment, threshold=threshold, max_count=max_count)


def format_decision_brief(selected_items: List[Dict[str, Any]]) -> str:
    if not selected_items:
        return "今日扫描未发现高启发性条目。"

    brief = "### 🚀 今日前沿科技决策简报\n\n"
    for i, item in enumerate(selected_items, 1):
        score = item.get("final_score", item.get("reader_score", item.get("score", 0)))
        brief += f"**{i}. [{score}分] {item.get('title', '未知标题')}**\n"
        if item.get("final_rationale"):
            brief += f"> GPT54判断: {item.get('final_rationale')}\n"
        elif item.get("reader_rationale"):
            brief += f"> MiniMax初读: {item.get('reader_rationale')}\n"
        brief += f"> {item.get('reader_summary', item.get('description', '无摘要'))}\n"
        brief += f"[查看原文]({item.get('url', '#')})\n\n"
    return brief
