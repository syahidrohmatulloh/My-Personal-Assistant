"""Self-reflection engine.

Periodically reads a user's recent journal entries, emotional state log,
and goal check-ins, then asks Haiku to identify 1-3 patterns that would
help the assistant calibrate behavior — NOT patterns to lecture the user
about.

These are PRIVATE notes. The prompt_builder already wraps self_reflections
with "do NOT recite these back to the user", so reflections influence
reasoning without becoming therapy talk.

Categories (per schema):
  - what_works:       e.g. "User responds well to direct, concise answers"
  - what_doesnt:      e.g. "User finds nudges intrusive after 9pm"
  - pattern_noticed:  e.g. "User journals more on Sundays"
  - open_question:    e.g. "Is the user venting or asking for help when stressed?"

Idempotency: we don't dedupe. The prompt builder limits to 5 most recent,
so if Haiku writes a similar reflection twice in a row, the older one ages
out naturally. Decay function (already present in schema_phase3_decay.sql)
will also drop confidence on inferred rows over time.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.claude import get_claude
from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)


REFLECTION_KINDS = ("what_works", "what_doesnt", "pattern_noticed", "open_question")


class ExtractedReflection(BaseModel):
    content: str = Field(min_length=10, max_length=300)
    kind: Literal["what_works", "what_doesnt", "pattern_noticed", "open_question"]


REFLECTION_PROMPT = """You are reviewing 1-2 weeks of activity logs for a user of \
a personal AI assistant. Your job: identify 1-3 patterns that would help the \
assistant (not the user) calibrate its behavior.

# Output

JSON array of objects: {{ "content": "...", "kind": "..." }}.

`kind` must be one of:
  - "what_works"      — behaviors of the assistant the user has responded well to
  - "what_doesnt"     — behaviors that haven't landed, or contexts where the \
user prefers different treatment
  - "pattern_noticed" — temporal, emotional, or behavioral patterns of the user
  - "open_question"   — uncertainty about the user's intent or preference \
that the assistant should hold lightly

# Rules

- Be conservative. Only output patterns you can point to evidence for.
- 1-3 items maximum. Quality > quantity.
- Write in third person about "the user" or "the assistant".
- These are PRIVATE notes for the assistant's internal calibration. They will \
NEVER be shown to the user verbatim.
- Avoid therapy talk, diagnoses, or sweeping personality claims.
- If there is genuinely nothing useful to note, return [].

# What NOT to do

- Don't infer mental health conditions.
- Don't speculate about the user's relationships or history beyond the data.
- Don't write reflections about a single event — patterns need 2+ data points.
- Don't write platitudes ("the user values growth") — be specific.

Output ONLY the JSON array. No prose, no markdown fences."""


async def generate_weekly_reflection(*, user_id: str, lookback_days: int = 14) -> int:
    """Generate reflections for one user. Returns number of reflections written.

    Reads:
      - Journal entries (emotional_state self_report rows) with notes
      - Goal check-ins with notes
      - Recent life_events

    Skips silently if there's not enough data (< 3 total signals in window).
    """
    supabase = get_supabase()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    # Pull signals in parallel-friendly order. We do them sequentially because
    # all three are small queries against indexed columns — no real win
    # from parallelism, and easier to reason about.
    journals = (
        supabase.table("emotional_state")
        .select("mood, energy, stress, note, observed_at")
        .eq("user_id", user_id)
        .eq("source", "self_report")
        .eq("superseded", False)
        .gte("observed_at", cutoff)
        .order("observed_at", desc=False)
        .execute()
    )
    checkins = (
        supabase.table("goal_check_ins")
        .select("goal_id, momentum, note, created_at")
        .eq("user_id", user_id)
        .gte("created_at", cutoff)
        .order("created_at", desc=False)
        .execute()
    )
    events = (
        supabase.table("life_events")
        .select("title, category, happened_on, significance")
        .eq("user_id", user_id)
        .gte("happened_on", (date.today() - timedelta(days=lookback_days)).isoformat())
        .order("happened_on", desc=False)
        .execute()
    )

    journal_rows = journals.data or []
    checkin_rows = checkins.data or []
    event_rows = events.data or []

    total_signals = len(journal_rows) + len(checkin_rows) + len(event_rows)
    if total_signals < 3:
        log.info(
            "reflection: user=%s skipped (only %d signals in %dd window)",
            user_id[:8],
            total_signals,
            lookback_days,
        )
        return 0

    # Compose the digest for Haiku.
    blocks: list[str] = []

    if journal_rows:
        lines = ["## Journal entries (self-reported emotional state)"]
        for j in journal_rows:
            date_str = (j.get("observed_at") or "")[:10]
            nums = []
            if j.get("mood") is not None:
                nums.append(f"mood {j['mood']:+d}")
            if j.get("energy") is not None:
                nums.append(f"energy {j['energy']:+d}")
            if j.get("stress") is not None:
                nums.append(f"stress {j['stress']:+d}")
            num_str = ", ".join(nums) if nums else ""
            note = j.get("note") or ""
            lines.append(f"- {date_str}: {num_str} — {note}".rstrip(" —"))
        blocks.append("\n".join(lines))

    if checkin_rows:
        lines = ["## Goal check-ins"]
        for c in checkin_rows:
            date_str = (c.get("created_at") or "")[:10]
            momentum = c.get("momentum")
            mom_str = f" (momentum {momentum:+d})" if momentum is not None else ""
            lines.append(f"- {date_str}{mom_str}: {c.get('note') or ''}".rstrip(": "))
        blocks.append("\n".join(lines))

    if event_rows:
        lines = ["## Life events"]
        for e in event_rows:
            lines.append(
                f"- {e.get('happened_on')}: [{e.get('category')}] {e.get('title')}"
            )
        blocks.append("\n".join(lines))

    digest = "\n\n".join(blocks)

    # Call Haiku.
    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=600,
            system=REFLECTION_PROMPT,
            messages=[{"role": "user", "content": digest}],
        )
    except Exception as exc:
        log.warning("reflection: Haiku failed for user=%s: %s", user_id[:8], exc)
        return 0

    text_block = next((b for b in response.content if b.type == "text"), None)
    if not text_block:
        return 0
    raw = text_block.text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("reflection: bad JSON from Haiku: %r", raw[:200])
        return 0

    if not isinstance(parsed, list):
        return 0

    # Validate + cap.
    valid: list[ExtractedReflection] = []
    for item in parsed[:3]:
        try:
            valid.append(ExtractedReflection.model_validate(item))
        except ValidationError:
            continue

    if not valid:
        return 0

    period_start = (date.today() - timedelta(days=lookback_days)).isoformat()
    period_end = date.today().isoformat()

    rows = [
        {
            "user_id": user_id,
            "content": r.content,
            "kind": r.kind,
            "covers_period_start": period_start,
            "covers_period_end": period_end,
        }
        for r in valid
    ]

    supabase.table("self_reflections").insert(rows).execute()

    log.info(
        "reflection: user=%s wrote %d reflections covering %s..%s",
        user_id[:8],
        len(rows),
        period_start,
        period_end,
    )
    return len(rows)
