"""MiniMax first-pass reader for external-learning.

Role in the new architecture:
- Read many candidate articles/papers cheaply
- Produce normalized reading cards
- Preserve breadth; do not make final decisions
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

try:
    from .llm_decider import run_screen_judgment
except ImportError:
    from llm_decider import run_screen_judgment


def build_first_pass_prompt(items: List[Dict[str, Any]], max_keep: int = 20) -> str:
    compact_items = []
    for idx, item in enumerate(items, 1):
        compact_items.append({
            "id": idx,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "content_source": item.get("content_source", ""),
            "content_chars": item.get("content_chars", 0),
            "content_cache_path": item.get("content_cache_path", ""),
            "content_text": item.get("content_text", ""),
            "score": item.get("score", 0),
            "reason": item.get("reason", ""),
            "source": item.get("source", ""),
        })

    payload = json.dumps(compact_items, ensure_ascii=False, indent=2)
    return f"""
你是外部学习系统里的低成本初读员。你的任务不是最终拍板，而是尽量便宜地读很多候选，并提炼成初读卡片，供更强模型复判。

要求：
1. 尽量保留有潜力的内容，宁可多收一点，不要过早错杀
2. 每条保留项输出一张初读卡片
3. 候选里包含 content_text，这是从 PDF、README 或网页正文提取的轻量全文包；必须基于 content_text 写概要，不要复述 description 摘要
4. summary 必须体现你从正文里读到的具体信息，如方法、实验规模、数据集、核心结论、限制或工程细节
5. 初读卡片只做：主题判断、价值判断、与模型/Agent主线关系、是否建议进一步深读
6. 不要写长文，不要做最终结论

输出 JSON：
- items: [
  {{
    "id": 1,
    "decision": "keep" | "drop",
    "reader_score": 0-10,
    "topic": "一句话主题",
    "summary": "2-4句基于content_text的正文概要，包含具体事实",
    "model_relevance": "high" | "medium" | "low",
    "next_action": "deepread" | "observe" | "drop",
    "rationale": "一句话原因"
  }}
]

硬约束：
- 最多 keep {max_keep} 条
- 输出必须是合法 JSON，不能带 markdown

候选列表：
{payload}
""".strip()


def generate_reading_cards(items: List[Dict[str, Any]], max_keep: int = 20) -> List[Dict[str, Any]]:
    if not items:
        return []

    prompt = build_first_pass_prompt(items, max_keep=max_keep)
    judgment = run_screen_judgment(prompt)
    decisions = judgment.get("items", [])
    item_map = {idx: dict(item) for idx, item in enumerate(items, 1)}

    cards = []
    for decision in decisions:
        idx = decision.get("id")
        if idx not in item_map:
            continue
        base = item_map[idx]
        card = dict(base)
        card["reader_score"] = float(decision.get("reader_score", card.get("score", 0)))
        card["reader_decision"] = decision.get("decision", "drop")
        card["reader_topic"] = decision.get("topic", "")
        card["reader_summary"] = decision.get("summary", "")
        card["reader_model_relevance"] = decision.get("model_relevance", "medium")
        card["reader_next_action"] = decision.get("next_action", "observe")
        card["reader_rationale"] = decision.get("rationale", "")
        card["reader_content_source"] = card.get("content_source", "")
        card["reader_content_chars"] = card.get("content_chars", 0)
        card["reader_content_cache_path"] = card.get("content_cache_path", "")
        cards.append(card)

    cards = [c for c in cards if c.get("reader_decision") == "keep"]
    cards.sort(key=lambda x: (x.get("reader_score", 0), x.get("score", 0)), reverse=True)
    return cards[:max_keep]
