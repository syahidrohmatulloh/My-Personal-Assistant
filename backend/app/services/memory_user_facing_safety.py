"""User-facing memory safety helpers.

These helpers detect memories that are technically useful internally but should
not be presented as a natural user profile fact.

They are deterministic and intentionally conservative.
"""

from __future__ import annotations

import re
from typing import Any


RAW_MEMORY_MARKERS = (
    "due_date=",
    "start_at=",
    "end_at=",
    "goal_id=",
    "location=",
    "title=",
    "calendar_event_",
    "structured_field",
    "structured_value",
    "source_priority",
    "polished_theme",
    "aware_glass",
    "mobile_smooth",
    "good_contrast",
    "consistent_personal",
    "companion_not_generic",
    "not_incremental_guessing",
    "root_cause_implementation",
    " | ",
)

INTERNAL_STYLE_FIELDS = {
    "ui_design_taste",
    "consolidated_ui_design_preference",
    "consolidated_interaction_pattern",
    "consolidated_aliyya_relationship_preference",
    "aliyya_coding_support_style",
    "aliyya_relationship_style",
    "monthly_focus",
}

LOW_INFORMATION_VALUES = {
    "",
    "none",
    "null",
    "n/a",
    "unknown",
    "aliyya",
    "assistant",
    "ai",
}


def compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def looks_like_raw_or_internal_text(value: Any) -> bool:
    text = compact(value)
    lowered = text.lower()

    if not text:
        return True

    if lowered in LOW_INFORMATION_VALUES:
        return True

    if any(marker in lowered for marker in RAW_MEMORY_MARKERS):
        return True

    # Most short snake_case values are implementation labels, not user-facing facts.
    if "_" in text and len(text.split()) <= 5:
        return True

    # ISO datetime metadata should not be shown as profile memory text.
    if re.search(r"\b20\d{2}-\d{2}-\d{2}t\d{2}:\d{2}", lowered):
        return True

    return False


def memory_low_quality_reasons(
    *,
    content: Any,
    structured_field: Any,
    structured_value: Any,
) -> list[str]:
    reasons: list[str] = []
    field = compact(structured_field).lower()
    value = compact(structured_value)

    if field in INTERNAL_STYLE_FIELDS and looks_like_raw_or_internal_text(value):
        reasons.append("Looks like an internal assistant preference key")

    if looks_like_raw_or_internal_text(value):
        reasons.append("Memory value looks technical or raw")

    if looks_like_raw_or_internal_text(content) and not value:
        reasons.append("Memory content looks technical or raw")

    return reasons


def human_calendar_structured_value(
    *,
    title: str,
    event_date: str,
    start_at: str | None = None,
    end_at: str | None = None,
    location: str | None = None,
) -> str:
    parts = [f"Calendar event: {compact(title) or 'Scheduled event'}", f"date {event_date}"]

    if start_at:
        parts.append(f"starts {start_at}")
    if end_at:
        parts.append(f"ends {end_at}")
    if location:
        parts.append(f"location {compact(location)}")

    return "; ".join(parts)
