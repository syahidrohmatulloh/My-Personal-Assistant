"""Daily briefing service.

Generates a short, personal morning greeting that references the user's
actual context: active goals, important people (birthdays nearby), recent
mood pattern, journal entries, recent life events.

Design principles (CLAUDE.md doctrine):
  - Restrained, not performative. No "Good morning! ✨" — just useful.
  - Reference observed facts only — never invent context.
  - One specific, actionable observation > three vague ones.
  - Tone matches user's communication preferences from identity.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]

from app.services import life_model
from app.services.claude import get_claude
from app.services.prompt_builder import render_context
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)


BRIEFING_PROMPT = """You are a personal AI assistant writing a SHORT morning briefing \
for one specific person. You have their life context below.

# What to write

A briefing in 3-5 short sentences. Greet them by name once (use it naturally, \
not "Hello [name]!"). Then surface AT MOST 2-3 specific things that matter \
today, drawn from the context:

- A goal that hasn't been touched in a while
- A relationship event coming up (birthday in next 14 days, a friend mentioned recently)
- A mood pattern worth noting (e.g. several stressed days in a row)
- A life event anniversary
- A follow-up they said they'd do

# How to write

- Match the user's language (Indonesian, English, or mix — whatever their identity narrative uses).
- Match their preferred communication tone if specified.
- Calm. Operational. NOT performatively warm. NOT "I noticed you've been feeling…"
- Specific. Reference actual goals/people/events by name where appropriate.
- End with a soft prompt that gives them an opening to engage — but doesn't pressure.

# What NOT to do

- No emojis. No "✨" or "🌟" or anything else.
- No "Good morning [Name]! Here's your briefing:" formula.
- No vague platitudes ("Hope you're well today").
- No therapy talk. No "It's okay if today feels hard."
- No restating the context wholesale. You have it for grounding, not recital.
- If there's genuinely nothing specific to surface, write something short and \
honest — don't pad.

Output ONLY the briefing text. No preamble, no markdown headers, no quotes."""



def _select_existing_briefing(*, user_id: str, local_date: str) -> dict[str, Any] | None:
    """Return an existing daily briefing row, if present."""
    existing = safe_execute(
        lambda sb: sb.table("daily_briefings")
        .select("id, content, generated_at, conversation_id, opened_at")
        .eq("user_id", user_id)
        .eq("briefing_date", local_date)
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        return existing.data
    return None


def _is_daily_briefing_duplicate_error(exc: Exception) -> bool:
    """Detect the user_id + briefing_date unique constraint race."""
    text = str(exc).lower()
    return (
        "23505" in text
        or "daily_briefings_user_id_briefing_date_key" in text
        or "duplicate key value violates unique constraint" in text
    )


async def get_or_generate_briefing(
    *,
    user_id: str,
    local_date: str,  # 'YYYY-MM-DD' in user's local timezone
) -> dict[str, Any]:
    """Return today's briefing for the user, generating it if missing.

    Returns: {id, content, generated_at, conversation_id, opened_at}
    """
    # Check if briefing exists for this user+date.
    existing = _select_existing_briefing(user_id=user_id, local_date=local_date)
    if existing:
        return existing

    # Generate fresh.
    content = await _generate_briefing_content(user_id)
    if not content:
        # Empty briefing — don't persist. Caller treats as "no briefing today".
        return {}

    try:
        inserted = safe_execute(
            lambda sb: sb.table("daily_briefings")
            .insert(
                {
                    "user_id": user_id,
                    "briefing_date": local_date,
                    "content": content,
                }
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        if _is_daily_briefing_duplicate_error(exc):
            existing_after_race = _select_existing_briefing(
                user_id=user_id,
                local_date=local_date,
            )
            if existing_after_race:
                log.info(
                    "briefing: recovered duplicate insert race for user=%s date=%s",
                    user_id[:8],
                    local_date,
                )
                return existing_after_race
        raise

    row = (inserted.data or [{}])[0]
    log.info(
        "briefing: generated for user=%s date=%s len=%d",
        user_id[:8],
        local_date,
        len(content),
    )
    return row


async def _generate_briefing_content(user_id: str) -> str | None:
    """Call Haiku to write the briefing, given user's life context."""
    try:
        context = await life_model.get_context(user_id, mood_days=14)
    except Exception as exc:  # noqa: BLE001
        log.warning("briefing: failed to load context: %s", exc)
        return None

    rendered = render_context(context)
    if not rendered:
        # Brand new user, no context — no briefing worth generating.
        return None

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=400,
            system=BRIEFING_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Write today's briefing. Here is the user's context:\n\n"
                        + rendered
                    ),
                }
            ],
        )
        block = next((b for b in response.content if b.type == "text"), None)
        if not block:
            return None
        text = block.text.strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        log.warning("briefing: Haiku call failed: %s", exc)
        return None


async def mark_briefing_opened(
    *,
    user_id: str,
    briefing_id: str,
    conversation_id: str,
) -> None:
    """Link the briefing to a conversation once the user taps it."""
    try:
        safe_execute(
            lambda sb: sb.table("daily_briefings")
            .update(
                {
                    "conversation_id": conversation_id,
                    "opened_at": "now()",
                }
            )
            .eq("id", briefing_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("briefing: mark-opened failed: %s", exc)
