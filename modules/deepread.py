"""
Deep Read module — 深读引擎。

读取候选清单，逐条深读原文，产出结构化知识笔记。
由主 Agent 调用，不是子 Agent。
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import sys
    from pathlib import Path as _Path
    _parent = _Path(__file__).resolve().parent.parent.parent.parent.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))
    from runtime_config import WORKSPACE as WORKSPACE_ROOT
except ImportError:
    WORKSPACE_ROOT = _Path("/root/.openclaw/workspace")
LEARNING_DIR = WORKSPACE_ROOT / "memory" / "learning"
RAW_DIR = LEARNING_DIR / "raw"

MODEL_RELEVANT_KEYWORDS = {
    "model", "models", "foundation model", "llm", "language model", "multimodal",
    "agent", "agents", "memory", "world model", "reasoning", "inference",
    "training", "post-training", "alignment", "benchmark", "eval", "evaluation",
    "dataset", "rag", "retrieval", "embedding", "safety", "guardrail",
    "机器人", "具身智能", "大模型", "模型", "智能体", "记忆", "推理", "对齐",
    "评测", "基准", "数据集", "训练", "检索", "多模态"
}

MODEL_IRRELEVANT_KEYWORDS = {
    "railway", "rail", "battery", "ev", "satellite", "launch", "climate",
    "grid", "energy", "pharma", "gene", "biotech", "semiconductor manufacturing",
    "房地产", "餐饮", "旅游", "物流", "地产", "电池", "卫星", "火箭", "能源"
}


def classify_model_relevance(candidate: dict[str, Any]) -> dict[str, str]:
    """Classify whether an item is relevant to model/agent evolution."""
    text_parts = [
        candidate.get("title", ""),
        candidate.get("reason", ""),
        candidate.get("description", ""),
        candidate.get("url", ""),
    ]
    text = " ".join(text_parts).lower()

    positive_hits = [kw for kw in MODEL_RELEVANT_KEYWORDS if kw.lower() in text]
    negative_hits = [kw for kw in MODEL_IRRELEVANT_KEYWORDS if kw.lower() in text]

    if positive_hits:
        return {
            "模型相关性": "高",
            "相关性理由": f"与模型/Agent 主线直接相关: {', '.join(positive_hits[:3])}",
            "建议优先级": "P1",
        }

    if negative_hits:
        return {
            "模型相关性": "低",
            "相关性理由": f"偏离模型主线: {', '.join(negative_hits[:3])}",
            "建议优先级": "skip",
        }

    return {
        "模型相关性": "中",
        "相关性理由": "与主线关系不够明确，需结合初读卡片人工判断是否可迁移",
        "建议优先级": "P2",
    }


def load_candidates(date_str: str = None) -> list[dict[str, Any]]:
    """Load and merge all candidate files for a given date.
    
    Args:
        date_str: Date string (YYYY-MM-DD). Defaults to today.
    
    Returns:
        Merged list of candidates sorted by score descending.
    """
    try:
        from .gather import merge_all_candidates
    except ImportError:
        from gather import merge_all_candidates
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    return merge_all_candidates(date_str)


def filter_for_deep_read(candidates: list[dict[str, Any]], min_score: float = 7.0, max_count: int = 15) -> list[dict[str, Any]]:
    """Run the full final selection pipeline for deep reading."""
    try:
        from .decider import select_for_deep_read
    except ImportError:
        from decider import select_for_deep_read

    coarse = [c for c in candidates if c.get("score", 0) >= max(5.0, min_score - 2.0)]
    return select_for_deep_read(coarse, threshold=min_score, max_count=max_count)


def deep_read_single(candidate: dict[str, Any]) -> dict[str, Any]:
    """Deep read a single candidate and produce a structured note.
    
    This function should be called by the main agent with web_fetch.
    Returns a template note that the agent should fill in.
    
    For arXiv papers, the agent should first web_fetch the abs page to get
    the real title, then fetch the PDF for full content.
    
    Args:
        candidate: Candidate dict with title, URL, score, source.
    
    Returns:
        Note template dict with placeholders for agent to fill.
    """
    url = candidate.get("url", "")
    title = candidate.get("title", "")
    score = candidate.get("score", 0)
    source = candidate.get("source", "")
    
    relevance = classify_model_relevance(candidate)

    note = {
        "标题": title,
        "URL": url,
        "分数": score,
        "日期": datetime.now().strftime("%Y-%m-%d"),
        "来源": source,
        "候选理由": candidate.get("reason", ""),
        "模型相关性": relevance["模型相关性"],
        "来源等级": "摘要级",  # Agent should update this after reading
        "二次验证": "",  # Agent should fill this in
        "核心内容": "",  # Agent should fill with 3-5 bullet points
        "对我们的启发": "",  # Agent should fill with actionable insights
        "关键数据": "",  # Agent should fill with specific numbers
        "落地评估": {
            "相关模块": "",
            "相关性理由": relevance["相关性理由"],
            "改动规模": "",
            "前置条件": "",
            "落地优先级": relevance["建议优先级"],
        },
        "原文存档": "",
    }
    
    return note


def deep_read_batch(candidates: list[dict[str, Any]], date_str: str = None) -> list[dict[str, Any]]:
    """Deep read a batch of candidates.
    
    This is the main entry point. The agent should:
    1. Call this to get the list of candidates to deep read
    2. For each candidate, call web_fetch to read the original content
    3. Fill in the note template
    4. Call save_notes to save the results
    
    Args:
        candidates: List of candidate dicts (already filtered).
        date_str: Date string (YYYY-MM-DD). Defaults to today.
    
    Returns:
        List of note templates for the agent to fill in.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    notes = []
    for candidate in candidates:
        note = deep_read_single(candidate)
        notes.append(note)
    
    return notes


def save_notes(notes: list[dict[str, Any]], date_str: str = None, skip_low_quality: bool = True):
    """Save deep reading notes to markdown file.
    
    Args:
        notes: List of completed note dicts.
        date_str: Date string (YYYY-MM-DD). Defaults to today.
        skip_low_quality: If True, skip notes with quality score < 6.
    """
    try:
        from .quality import score_note_quality, should_discard_note, enforce_secondary_verification
    except ImportError:
        from quality import score_note_quality, should_discard_note, enforce_secondary_verification
    
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    filepath = LEARNING_DIR / f"{date_str}.md"
    
    # Filter low quality notes if enabled
    if skip_low_quality:
        filtered_notes = []
        discarded_count = 0
        for note in notes:
            if should_discard_note(note):
                discarded_count += 1
                print(f"[deepread] Discarded low-quality note: {note.get('标题', '')[:30]}")
            else:
                # Enforce secondary verification for high-score notes
                note = enforce_secondary_verification(note)
                filtered_notes.append(note)
        
        if discarded_count > 0:
            print(f"[deepread] Discarded {discarded_count} low-quality notes")
        
        notes = filtered_notes
    
    # Write the markdown file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# 外部学习笔记 {date_str}\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**深读条目数**: {len(notes)}\n\n")
        
        if not notes:
            f.write("本次无符合条件的高价值条目。\n\n")
        else:
            f.write("## 深度笔记\n\n")
            
            for i, note in enumerate(notes, 1):
                f.write(f"### {i}. [{note.get('标题', '')}]({note.get('URL', '')})\n\n")
                f.write(f"**来源**: {note.get('来源', '')} | **分数**: {note.get('分数', 0)} | **日期**: {note.get('日期', '')}\n")
                if note.get("候选理由"):
                    f.write(f"**候选理由**: {note.get('候选理由', '')}\n")
                f.write(f"**模型相关性**: {note.get('模型相关性', '中')}\n")
                f.write(f"**来源等级**: {note.get('来源等级', '摘要级')}\n")
                f.write(f"**二次验证**: {note.get('二次验证', '未做')}\n\n")
                
                core_content = note.get("核心内容", "")
                if core_content:
                    f.write(f"**核心内容**:\n{core_content}\n\n")
                
                insights = note.get("对我们的启发", "")
                if insights:
                    f.write(f"**对我们的启发**:\n{insights}\n\n")
                
                key_data = note.get("关键数据", "")
                if key_data:
                    f.write(f"**关键数据**:\n{key_data}\n\n")
                
                landing = note.get("落地评估", {})
                if landing and isinstance(landing, dict):
                    f.write(f"**落地评估**:\n")
                    f.write(f"- 相关模块: {landing.get('相关模块', '无')}\n")
                    f.write(f"- 相关性理由: {landing.get('相关性理由', '未说明')}\n")
                    f.write(f"- 改动规模: {landing.get('改动规模', '不确定')}\n")
                    f.write(f"- 前置条件: {landing.get('前置条件', '无')}\n")
                    f.write(f"- 落地优先级: {landing.get('落地优先级', 'skip')}\n\n")
                
                archive_path = note.get("原文存档", "")
                if archive_path:
                    f.write(f"**原文存档**: {archive_path}\n\n")
                
                f.write("---\n\n")
            
            # Summary table
            f.write("## 落地评估汇总\n\n")
            f.write("| 条目 | 相关模块 | 优先级 | 状态 |\n")
            f.write("|------|----------|--------|------|\n")
            
            for note in notes:
                title = note.get("标题", "")[:30]
                landing = note.get("落地评估", {})
                if isinstance(landing, dict):
                    module = landing.get("相关模块", "无")
                    priority = landing.get("落地优先级", "skip")
                    f.write(f"| {title} | {module} | {priority} | — |\n")
    
    print(f"[deepread] Saved {len(notes)} notes to {filepath}")


def archive_original_content(title: str, content: str, source: str, date_str: str = None) -> str:
    """Archive original content to raw directory.
    
    Args:
        title: Article title.
        content: Original content (from web_fetch).
        source: Source identifier.
        date_str: Date string (YYYY-MM-DD). Defaults to today.
    
    Returns:
        Path to the archived file.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # Sanitize title for filename
    safe_title = title[:50].replace("/", "-").replace("\\", "-").replace(":", "-")
    filename = f"{source}-{safe_title}.md"
    filepath = RAW_DIR / date_str / filename
    
    # Create date subdirectory
    (RAW_DIR / date_str).mkdir(parents=True, exist_ok=True)
    filepath = RAW_DIR / date_str / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"**来源**: {source}\n")
        f.write(f"**存档时间**: {datetime.now().isoformat()}\n")
        f.write(f"**原始URL**: (should be added by agent)\n\n")
        f.write("---\n\n")
        f.write(content)
    
    return str(filepath.relative_to(WORKSPACE_ROOT))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="External Learning Deep Read Module")
    parser.add_argument("--date", type=str, help="Date string (YYYY-MM-DD)")
    parser.add_argument("--min-score", type=float, default=7.0, help="Minimum score to deep read")
    parser.add_argument("--max-count", type=int, default=15, help="Maximum candidates to deep read")
    args = parser.parse_args()
    
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    # Load candidates
    candidates = load_candidates(date_str)
    print(f"Loaded {len(candidates)} candidates")
    
    # Filter for deep read
    filtered = filter_for_deep_read(candidates, args.min_score, args.max_count)
    print(f"Filtered to {len(filtered)} candidates for deep reading")
    
    # Generate note templates
    notes = deep_read_batch(filtered, date_str)
    print(f"Generated {len(notes)} note templates")
    print("\nNote: Agent should now:")
    print("1. web_fetch each URL to read original content")
    print("2. Fill in the note templates")
    print("3. Call save_notes() to save results")
