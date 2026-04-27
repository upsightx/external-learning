"""Quality checks for external-learning deep-read notes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

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

_SECONDARY_VERIFIER: Callable[[dict[str, Any]], dict[str, str]] | None = None


def set_secondary_verifier(verifier: Callable[[dict[str, Any]], dict[str, str]] | None) -> None:
    global _SECONDARY_VERIFIER
    _SECONDARY_VERIFIER = verifier


def check_secondary_verification(note: dict[str, Any]) -> bool:
    verification = note.get("二次验证", "")
    if not verification or verification.strip() == "" or verification.strip() == "未做":
        return False
    return len(verification.strip()) >= 5


def check_source_level(note: dict[str, Any]) -> str:
    level = note.get("来源等级", "")
    valid_levels = ["摘要级", "原文级", "多源验证级"]
    if level not in valid_levels:
        return "摘要级"
    return level


def auto_verify_candidate(candidate: dict[str, Any]) -> dict[str, str]:
    if _SECONDARY_VERIFIER is None:
        return {
            "status": "unverified",
            "method": "二次验证",
            "details": "未配置二次验证执行器",
        }
    return _SECONDARY_VERIFIER(candidate)


def score_note_quality(note: dict[str, Any]) -> float:
    score = 1.0

    core_content = note.get("核心内容", "")
    if core_content and len(core_content.strip()) > 20:
        bullet_count = core_content.count("- ") + core_content.count("•")
        if bullet_count >= 3:
            score += 3.0
        elif bullet_count >= 1:
            score += 2.0
        else:
            score += 1.0

    insights = note.get("对我们的启发", "")
    if insights and len(insights.strip()) > 10:
        empty_phrases = ["值得关注", "意义重大", "很有前景", "需要关注"]
        score += 0.5 if any(phrase in insights for phrase in empty_phrases) else 2.0

    key_data = note.get("关键数据", "")
    if key_data and len(key_data.strip()) > 5:
        score += 2.0 if any(c.isdigit() for c in key_data) else 1.0

    source_level = check_source_level(note)
    if source_level == "多源验证级":
        score += 2.0
    elif source_level == "原文级":
        score += 1.5

    if check_secondary_verification(note):
        score += 1.0

    return min(score, 10.0)


def should_discard_note(note: dict[str, Any]) -> bool:
    return score_note_quality(note) < 6.0


def enforce_secondary_verification(note: dict[str, Any]) -> dict[str, Any]:
    score = note.get("分数", 0)
    if score < 8 or check_secondary_verification(note):
        return note

    candidate = {
        "title": note.get("标题", ""),
        "url": note.get("URL", ""),
        "source": note.get("来源", ""),
    }
    verification = auto_verify_candidate(candidate)

    if verification["status"] == "verified":
        note["二次验证"] = f"{verification['method']}: {verification['details']}"
        return note

    note["二次验证"] = f"未完成验证: {verification['details']}，落地优先级降为P2"
    landing = note.get("落地评估")
    if isinstance(landing, dict) and landing.get("落地优先级") in ["P0", "P1"]:
        landing["落地优先级"] = "P2"
    return note
