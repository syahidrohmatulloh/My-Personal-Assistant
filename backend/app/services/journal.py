"""Journal service — daily check-in entry point.

A journal entry is a single mood reading plus optional free-text reflection.
We do two things with it:

  1. Always write to `emotional_state` with source='self_report' (the
     authoritative input — supersedes any inferred mood from the same window).

  2. If the free text mentions something that looks like a real life event,
     ask Claude to extract it and write to `life_events`. Conservative —
     better to miss than fabricate.

The extraction is a background task; the user sees their save confirmation
immediately.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.services import life_model
from app.services.claude import get_claude
from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Save a journal entry
# ---------------------------------------------------------------------------

async def save_entry(
    *,
    user_id: str,
    mood: int | None,
    energy: int | None,
    stress: int | None,
    note: str | None,
) -> dict:
    """Write a journal entry. Returns the saved emotional_state row."""
    row = await life_model.record_mood(
        user_id=user_id,
        mood=mood,
        energy=energy,
        stress=stress,
        note=note,
        source="self_report",
        confidence=1.0,
    )
    return row


# ---------------------------------------------------------------------------
# Has the user journaled today?
# ---------------------------------------------------------------------------

async def todays_entry(user_id: str) -> dict | None:
    """Return today's most recent self-reported journal entry, or None."""
    supabase = get_supabase()
    start_of_day = datetime.combine(date.today(), datetime.min.time()).isoformat()
    result = (
        supabase.table("emotional_state")
        .select("id, mood, energy, stress, note, observed_at")
        .eq("user_id", user_id)
        .eq("source", "self_report")
        .eq("superseded", False)
        .gte("observed_at", start_of_day)
        .order("observed_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ---------------------------------------------------------------------------
# Background event extraction
# ---------------------------------------------------------------------------

class ExtractedEvent(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    category: Literal[
        "milestone", "transition", "loss", "achievement", "reflection", "health", "other"
    ]
    significance: int = Field(ge=1, le=10)


EXTRACTION_PROMPT = """You read a daily journal entry and identify SIGNIFICANT life events worth \
recording — not everyday moments, only things the user might want to remember years later.

Output a JSON array. Each item:
  - title: short phrase, third person about "the user" (e.g. "Started new fitness routine")
  - category: one of: milestone, transition, loss, achievement, reflection, health, other
  - significance: 1-10. Be conservative — most days don't have a 7+. Reserve high \
significance for genuinely notable life events.

Examples to extract:
  - "Got the promotion!" → {"title": "Promoted at work", "category": "achievement", "significance": 8}
  - "Mom called, dad's in hospital" → {"title": "Father hospitalized", "category": "health", "significance": 8}
  - "Realized I want to leave consulting" → {"title": "Decided to leave consulting", "category": "reflection", "significance": 7}

Examples NOT to extract (return empty):
  - "Tough meeting today, feeling drained" — that's mood, not an event
  - "Went to the gym" — routine, not significant
  - General feelings without specific events

If nothing significant, return [].

Output ONLY the JSON array. No prose, no markdown, no commentary."""


async def extract_events_from_entry(
    *,
    user_id: str,
    entry_text: str,
    entry_date: date,
) -> int:
    """Look for noteworthy life events in a journal entry. Returns count saved.

    Runs as a background task — the user already saw their save confirmation.
    Failures are logged but don't surface anywhere.
    """
    if not entry_text or len(entry_text.strip()) < 20:
        return 0

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=512,
            system=EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": entry_text}],
        )
        text_block = next((b for b in response.content if b.type == "text"), None)
        if not text_block:
            return 0
        raw = text_block.text.strip()
    except Exception as exc:
        log.warning("journal event extraction: Claude failed: %s", exc)
        return 0

    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("journal event extraction: bad JSON: %r", raw[:200])
        return 0

    if not isinstance(parsed, list) or not parsed:
        return 0

    saved = 0
    for item in parsed[:3]:  # hard cap — max 3 events per entry
        try:
            event = ExtractedEvent.model_validate(item)
        except Exception:
            continue
        try:
            await life_model.record_life_event(
                user_id=user_id,
                title=event.title,
                happened_on=entry_date,
                category=event.category,
                significance=event.significance,
                source="inferred",
                created_by="assistant",
            )
            saved += 1
        except Exception as exc:
            log.warning("journal event save failed: %s", exc)

    log.info("journal event extraction: saved %d events for user=%s", saved, user_id[:8])
    return saved


# ---------------------------------------------------------------------------
# History — for the journal page to show recent entries
# ---------------------------------------------------------------------------

async def recent_entries(user_id: str, days: int = 30) -> list[dict]:
    """Return self-reported entries from the last N days, newest first."""
    supabase = get_supabase()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = (
        supabase.table("emotional_state")
        .select("id, mood, energy, stress, note, observed_at")
        .eq("user_id", user_id)
        .eq("source", "self_report")
        .eq("superseded", False)
        .gte("observed_at", since)
        .order("observed_at", desc=True)
        .execute()
    )
    return result.data or []
