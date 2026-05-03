"""Classify podcast episodes by type based on title and transcript content."""
import re
from typing import Any

EPISODE_TYPES = (
    "crash_course",
    "rare_review",
    "draft_log",
    "archetype_analysis",
    "format_retrospective",
)

_TITLE_RULES: list[tuple[str, list[str]]] = [
    ("crash_course", [
        r"first impression", r"crash course", r"initial take", r"preview show",
        r"set preview", r"early look",
    ]),
    ("rare_review", [
        r"rare review", r"set review", r"card rating", r"reviewing the",
        r"rating the",
    ]),
    ("format_retrospective", [
        r"retrospective", r"looking back", r"format wrap", r"format review",
        r"post[- ]format", r"season finale",
    ]),
    ("archetype_analysis", [
        r"archetype", r"\b[WUBRG]{2}\b.{0,20}(?:aggro|control|tempo|midrange)",
        r"color pair",
    ]),
]

_TRANSCRIPT_RULES: list[tuple[str, list[str]]] = [
    ("draft_log", [
        r"pack\s+\d+\s+pick\s+\d+",
        r"p\d+p\d+",
        r"i'm going to take",
        r"i'll take",
        r"picking up",
    ]),
    ("archetype_analysis", [
        r"\b(?:RW|UB|BG|RG|WU|WB|UG|RB|WG|UR)\b.{0,30}(?:archetype|synergy|deck)",
    ]),
]


def classify_episode(episode_metadata: dict[str, Any], transcript: dict[str, Any]) -> str:
    """Classify an episode by type. Returns one of EPISODE_TYPES or 'unknown'."""
    title = episode_metadata.get("title", "") or ""
    description = episode_metadata.get("description", "") or ""
    full_text = transcript.get("full_text", "") or ""

    title_lower = title.lower()
    desc_lower = description.lower()
    text_lower = full_text.lower()

    # Title + description matching takes priority
    for episode_type, patterns in _TITLE_RULES:
        for pattern in patterns:
            if re.search(pattern, title_lower) or re.search(pattern, desc_lower):
                _log_match(episode_type, "title/description", pattern)
                return episode_type

    # Transcript matching as fallback
    for episode_type, patterns in _TRANSCRIPT_RULES:
        for pattern in patterns:
            if re.search(pattern, text_lower):
                _log_match(episode_type, "transcript", pattern)
                return episode_type

    print(f"  [classifier] no match for: {title!r} — returning 'unknown'")
    return "unknown"


def _log_match(episode_type: str, source: str, pattern: str) -> None:
    print(f"  [classifier] {episode_type!r} matched via {source}: /{pattern}/")
