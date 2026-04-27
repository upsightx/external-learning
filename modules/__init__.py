"""External Learning modules.

New architecture only:
- gather candidates programmatically
- MiniMax reads broadly
- GPT54 makes the final decision
- deepread consumes only final-selected items
"""

from .gather import gather, merge_all_candidates
from .deepread import load_candidates, filter_for_deep_read, deep_read_batch, save_notes
from .minimax_screener import screen_candidates
from .minimax_reader import generate_reading_cards
from .quality import score_note_quality, check_secondary_verification, enforce_secondary_verification

__all__ = [
    "gather",
    "merge_all_candidates",
    "load_candidates",
    "filter_for_deep_read",
    "deep_read_batch",
    "save_notes",
    "screen_candidates",
    "generate_reading_cards",
    "score_note_quality",
    "check_secondary_verification",
    "enforce_secondary_verification",
]
