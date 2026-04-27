"""MiniMax metadata screener for external-learning candidates."""

from __future__ import annotations

import json
from typing import Any

try:
    from .llm_decider import run_screen_judgment
except ImportError:
    from llm_decider import run_screen_judgment


def build_screen_prompt(items: list[dict[str, Any]], max_keep: int = 25) -> str:
    compact_items = []
    for idx, item in enumerate(items, 1):
        compact_items.append({
            "id": idx,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "score": item.get("score", 0),
            "reason": item.get("reason", ""),
            "source": item.get("source", ""),
            "published": item.get("published", ""),
        })

    payload = json.dumps(compact_items, ensure_ascii=False, indent=2)
    return f"""
你是 external-learning 的第一道低成本粗筛员。你只看链接元数据，不读全文。

目标：过滤水内容、泛新闻、营销稿、低相关内容，只保留值得抓全文的候选。

判断标准：
1. 优先保留：AI Agent、LLM记忆、推理、评测、coding agent、工具链、系统工程、模型训练/推理优化
2. 可以保留：对当前系统有明确迁移价值的工程实践或产品形态
3. 过滤：泛科技新闻、融资新闻、纯产品发布、硬件/能源/医疗等和模型/Agent主线弱相关内容
4. 不要因为标题里有 AI 就保留，必须有具体方法、系统、评测、论文或工程启发

输出 JSON：
- items: [
  {{
    "id": 1,
    "screen_decision": "keep" | "drop",
    "screen_score": 0-10,
    "screen_reason": "一句话中文理由"
  }}
]

硬约束：
- 最多 keep {max_keep} 条
- 输出必须是合法 JSON，不能带 markdown

候选元数据：
{payload}
""".strip()


def apply_screen_judgment(items: list[dict[str, Any]], judgment: dict[str, Any], max_keep: int = 25) -> list[dict[str, Any]]:
    item_map = {idx: dict(item) for idx, item in enumerate(items, 1)}
    screened = []
    for decision in judgment.get("items", []):
        idx = decision.get("id")
        if idx not in item_map:
            continue
        item = item_map[idx]
        item["screen_decision"] = decision.get("screen_decision", "drop")
        item["screen_score"] = float(decision.get("screen_score", item.get("score", 0)))
        item["screen_reason"] = decision.get("screen_reason", "")
        if item["screen_decision"] == "keep":
            screened.append(item)

    screened.sort(key=lambda x: (x.get("screen_score", 0), x.get("score", 0)), reverse=True)
    return screened[:max_keep]


def screen_candidates(items: list[dict[str, Any]], max_keep: int = 25) -> list[dict[str, Any]]:
    if not items:
        return []
    candidates = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
    prompt = build_screen_prompt(candidates, max_keep=max_keep)
    judgment = run_screen_judgment(prompt)
    return apply_screen_judgment(candidates, judgment, max_keep=max_keep)
