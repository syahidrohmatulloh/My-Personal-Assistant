"""Aliyya interaction preference prompt integration v1.

This service reads stable relationship/interaction memories and renders them
as a compact prompt block.

Important boundaries:
- This is NOT companion mood.
- This is NOT user mood.
- This does not write memories.
- This does not mutate companion_mood_state.
- This only guides tone, pacing, carefulness, and interaction style.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.supabase_client import safe_execute


INTERACTION_STRUCTURED_FIELDS = (
    "aliyya_coding_support_style",
    "aliyya_relationship_style",
    "ui_design_taste",
    "debugging_support_style_under_frustration",
)

MAX_PREFERENCES = 5
MAX_CONTENT_CHARS = 220


async def get_interaction_preferences_block(*, user_id: str) -> str | None:
    rows = await fetch_interaction_preferences(user_id=user_id)
    return render_interaction_preferences_block(rows)


async def fetch_interaction_preferences(*, user_id: str) -> list[dict[str, Any]]:
    """Fetch active relationship/interaction preferences.

    We intentionally fetch by structured_field so these preferences are not
    dependent on semantic similarity wording in the current user message.
    """
    def _query():
        return safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id, content, category, kind, structured_field, structured_value, "
                "confidence, source_priority, last_confirmed_at, created_at"
            )
            .eq("user_id", user_id)
            .eq("superseded", False)
            .in_("structured_field", list(INTERACTION_STRUCTURED_FIELDS))
            .limit(20)
            .execute()
        )

    result = await asyncio.to_thread(_query)
    rows = result.data or []
    return _rank_interaction_preferences(rows)[:MAX_PREFERENCES]


def render_interaction_preferences_block(rows: list[dict[str, Any]]) -> str | None:
    ranked = _rank_interaction_preferences(rows)
    if not ranked:
        return None

    lines = [
        "## ALIYYA INTERACTION PREFERENCES",
        "- Purpose: guide how Aliyya responds to the user. These are stable interaction preferences, not user mood and not companion mood.",
        "- Use these to adjust carefulness, pacing, brevity, warmth, and UI/coding support style.",
        "- Do not recite these preferences unless the user asks about them.",
    ]

    for row in ranked[:MAX_PREFERENCES]:
        content = _truncate(str(row.get("content") or "").strip(), MAX_CONTENT_CHARS)
        field = str(row.get("structured_field") or "").strip()
        if not content:
            continue

        if field:
            lines.append(f"- {field}: {content}")
        else:
            lines.append(f"- {content}")

    return "\n".join(lines) if len(lines) > 4 else None


def _rank_interaction_preferences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [
        row
        for row in rows
        if row
        and not row.get("superseded")
        and str(row.get("structured_field") or "") in INTERACTION_STRUCTURED_FIELDS
        and str(row.get("content") or "").strip()
    ]

    return sorted(
        active,
        key=lambda row: (
            _field_priority(str(row.get("structured_field") or "")),
            _safe_float(row.get("confidence")),
            str(row.get("last_confirmed_at") or row.get("created_at") or ""),
        ),
        reverse=True,
    )


def _field_priority(field: str) -> float:
    return {
        "aliyya_coding_support_style": 4.0,
        "debugging_support_style_under_frustration": 3.5,
        "aliyya_relationship_style": 3.0,
        "ui_design_taste": 2.0,
    }.get(field, 0.0)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _truncate(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
