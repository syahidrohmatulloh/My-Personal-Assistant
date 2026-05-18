"""Memory intelligence — context-aware extraction with conflict resolution.

Different from the existing `memory.py`:
  * `memory.py` does generic durable-fact extraction over the last user/assistant
    pair. It still runs.
  * THIS service runs OVER THE LAST 6-12 MESSAGES and focuses on:
      - structured identity facts (birthday, timezone, nickname, assistant name)
      - categorized memories (identity / preferences / relationships / routines
        / goals / important_dates / constraints)
      - source-priority scoring (explicit > answer-in-context > correction > pattern > assistant)
      - confidence scoring + evidence snippets
      - conflict resolution via `superseded` chain

Both run as background tasks after a chat turn. They don't fight: this one writes
NEW rows with `source_priority` set, and only marks a row `superseded=true` when
a clear contradiction is detected.

Decisions baked in (see Zip 5 audit conversation for reasoning):
  - Single Haiku call per turn (no per-message LLM)
  - 8-message context window (4 user + 4 assistant exchanges)
  - confidence >= 0.85 + (explicit OR answer_in_context) → save
  - confidence >= 0.70 + correction → save (and supersede)
  - assistant_confirmation alone → NEVER save as high-confidence; downgrade.
  - Random date without question context → discard
  - Identity facts (birthday/timezone/nickname/assistant_name) ALSO write to
    user_identity.profile via single-field merge.

Always run as a background task — never blocks the chat reply.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.claude import get_claude
from app.services.embeddings import embed_document
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Window over recent conversation. 8 messages = roughly 4 turns of back-and-forth.
# Enough for "assistant question → user short answer" pattern. Going larger risks
# Haiku misreading older context as current.
CONTEXT_WINDOW_MESSAGES = 8

# Hard cap on candidates per extraction. Even if Haiku tries to extract 15
# things, we keep only the top 5 by confidence.
MAX_CANDIDATES_PER_EXTRACTION = 5

# Categories — match the SQL check constraint.
Category = Literal[
    "identity",
    "preferences",
    "relationships",
    "routines",
    "goals",
    "important_dates",
    "constraints",
    "other",
]

# Source priorities. Order matters for ranking/threshold decisions.
SourcePriority = Literal[
    "explicit_user_statement",
    "user_answer_in_context",
    "user_correction",
    "repeated_pattern",
    "assistant_confirmation",
]

# Save thresholds. Tuned conservatively — better to miss than store noise.
_SAVE_THRESHOLDS: dict[str, float] = {
    "explicit_user_statement": 0.80,
    "user_answer_in_context": 0.75,
    "user_correction": 0.70,    # lower because the correction itself is high signal
    "repeated_pattern": 0.80,
    "assistant_confirmation": 0.95,  # almost never save these — they're weak
}

# Cosine similarity at which we treat a new memory as a duplicate of an old one
# rather than creating a new row. Lower than the legacy memory.py threshold
# (0.92) because we also have explicit conflict markers via category match.
_DEDUP_SIMILARITY_THRESHOLD = 0.88

# Structured identity fields — when we extract one of these, also write it to
# user_identity.profile (in addition to a memories row).
_STRUCTURED_IDENTITY_FIELDS: set[str] = {
    "birthday",
    "timezone",
    "nickname",
    "assistant_name",
    "name",
    "location",
}


# ---------------------------------------------------------------------------
# Schemas (Pydantic)
# ---------------------------------------------------------------------------


class CandidateMemory(BaseModel):
    """One candidate extracted by Haiku."""

    content: str = Field(min_length=3, max_length=500)
    category: Category
    source_priority: SourcePriority
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list, max_length=3)
    # If this is a structured identity fact, what field does it set?
    # e.g. "birthday" -> "7 Januari". None for non-identity memories.
    structured_field: str | None = Field(default=None, max_length=40)
    structured_value: str | None = Field(default=None, max_length=200)
    # If user is explicitly correcting an older fact, the new content
    # supersedes it. The service finds and marks the old one.
    is_correction: bool = False


# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM_PROMPT = """You analyze the last few messages of a conversation between a user and an AI assistant. Identify durable facts about the USER worth remembering for future conversations.

Output STRICT JSON array. Each item:
{
  "content": "third-person statement about the user (e.g. 'User's birthday is 7 Januari')",
  "category": "identity | preferences | relationships | routines | goals | important_dates | constraints | other",
  "source_priority": "explicit_user_statement | user_answer_in_context | user_correction | repeated_pattern | assistant_confirmation",
  "confidence": 0.0-1.0,
  "evidence": ["short quote 1 from user", "..."],
  "structured_field": "birthday | timezone | nickname | assistant_name | name | location | null",
  "structured_value": "the actual value, e.g. '7 Januari' (only if structured_field is set)",
  "is_correction": true | false
}

# Source priority rules — CRITICAL

- explicit_user_statement: User directly stated the fact unprompted.
  Example: "my birthday is January 7th"
- user_answer_in_context: User answered a question the assistant asked.
  REQUIRES: assistant asked a clear question in the prior turn.
  Example: Assistant: "kapan ulang tahunmu?" → User: "7 Januari hehe" → THIS is user_answer_in_context.
- user_correction: User contradicted/corrected something from earlier in the conversation.
  Example: "actually it's January 7th not December 7th"
- repeated_pattern: Same fact appeared multiple times across messages (rare in single turn).
- assistant_confirmation: ONLY the assistant said the fact; user did not confirm beyond "ok" or "yes".
  USE SPARINGLY. Confidence MUST be <= 0.6 unless user explicitly affirmed.

# Confidence calibration

- 0.95+: User stated it explicitly, in own words, plain language.
- 0.85: User answered an explicit assistant question with the value.
- 0.75: User implied the fact while answering something related.
- 0.65: Soft signal — needs context to interpret.
- 0.50 or lower: weak — do NOT include unless source_priority is correction.

# CRITICAL rules

1. SHORT ANSWERS: If the user gives a short answer like "7 Januari hehe", look at
   what the assistant ASKED in the prior turn. If assistant asked about birthday/
   timezone/etc, link the short answer to that question. confidence 0.85.
2. DO NOT extract random dates as birthdays. A date is a birthday ONLY if
   the assistant explicitly asked about birthday OR the user said the word "birthday"/
   "ulang tahun"/"ultah".
3. assistant_confirmation alone (user said "ok" / "noted" / "ya") is NOT enough
   to save a fact as high confidence. Drop confidence to <= 0.55 in those cases.
4. Be CONSERVATIVE. Return [] if nothing is clear.
5. Output JSON array ONLY. No prose, no markdown fences, no commentary.
6. Hard cap: max 5 items.

# Example

Conversation:
ASSISTANT: hey kamu tau ga aku ngga inget ulang tahunmu kapan
USER: 7 Januari hehe

Output:
[
  {
    "content": "User's birthday is January 7",
    "category": "important_dates",
    "source_priority": "user_answer_in_context",
    "confidence": 0.88,
    "evidence": ["7 Januari hehe"],
    "structured_field": "birthday",
    "structured_value": "7 Januari",
    "is_correction": false
  }
]
"""


# ---------------------------------------------------------------------------
# Public entry point — run as background task after a chat turn
# ---------------------------------------------------------------------------


async def extract_and_persist(
    *,
    user_id: str,
    conversation_id: str,
    recent_messages: list[dict],
) -> dict:
    """Run extraction over recent messages, save high-confidence facts.

    `recent_messages` should already be ordered oldest -> newest. The function
    will trim to CONTEXT_WINDOW_MESSAGES and feed only that slice to Haiku.

    Returns an audit dict: {candidates: N, saved: N, skipped: N, superseded: N}.
    Safe to fail silently — errors are logged but don't propagate.
    """
    audit = {"candidates": 0, "saved": 0, "skipped": 0, "superseded": 0}

    if not recent_messages:
        return audit

    window = recent_messages[-CONTEXT_WINDOW_MESSAGES:]
    transcript = _format_transcript(window)

    # === Call Haiku ===
    try:
        candidates = await _ask_haiku(transcript)
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: Haiku call failed: %s", exc)
        return audit

    audit["candidates"] = len(candidates)
    if not candidates:
        log.info("memory_intelligence: no candidates from %d-msg window", len(window))
        return audit

    # === Sort + dedupe by content + apply thresholds ===
    candidates = _dedupe_candidates(candidates)
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    candidates = candidates[:MAX_CANDIDATES_PER_EXTRACTION]

    # === Persist each ===
    for cand in candidates:
        threshold = _SAVE_THRESHOLDS.get(cand.source_priority, 0.95)
        if cand.confidence < threshold:
            audit["skipped"] += 1
            log.info(
                "memory_intelligence: skip '%s' (conf %.2f < %.2f for source=%s)",
                cand.content[:60], cand.confidence, threshold, cand.source_priority,
            )
            continue

        # Guard: assistant_confirmation alone → never high-confidence regardless.
        if cand.source_priority == "assistant_confirmation":
            audit["skipped"] += 1
            log.info(
                "memory_intelligence: skip '%s' (assistant_confirmation alone insufficient)",
                cand.content[:60],
            )
            continue

        # Guard: random date saved as birthday without context → discard.
        # Specifically: if structured_field == 'birthday' but source_priority is not
        # explicit_user_statement and not user_answer_in_context, drop.
        if (
            cand.structured_field == "birthday"
            and cand.source_priority not in (
                "explicit_user_statement",
                "user_answer_in_context",
                "user_correction",
            )
        ):
            audit["skipped"] += 1
            log.info(
                "memory_intelligence: skip birthday without question context: '%s'",
                cand.content[:60],
            )
            continue

        try:
            result = await _persist_candidate(
                user_id=user_id,
                conversation_id=conversation_id,
                cand=cand,
            )
            if result.get("saved"):
                audit["saved"] += 1
            if result.get("superseded"):
                audit["superseded"] += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("memory_intelligence: persist failed: %s", exc)
            audit["skipped"] += 1

    log.info("memory_intelligence: audit=%s", audit)
    return audit


# ---------------------------------------------------------------------------
# Internal: Haiku extraction
# ---------------------------------------------------------------------------


def _format_transcript(messages: list[dict]) -> str:
    """Render messages with clear role markers for Haiku."""
    return "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)


async def _ask_haiku(transcript: str) -> list[CandidateMemory]:
    claude = get_claude()
    response = await claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        system=_EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript}],
    )
    block = next((b for b in response.content if b.type == "text"), None)
    if not block:
        return []
    raw = block.text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("memory_intelligence: bad JSON: %s; raw=%r", exc, raw[:200])
        return []

    if not isinstance(parsed, list):
        return []

    valid: list[CandidateMemory] = []
    for item in parsed[:MAX_CANDIDATES_PER_EXTRACTION * 2]:
        try:
            valid.append(CandidateMemory.model_validate(item))
        except ValidationError:
            continue
    return valid


def _dedupe_candidates(cands: list[CandidateMemory]) -> list[CandidateMemory]:
    """Drop candidates with identical content (case-insensitive)."""
    seen: set[str] = set()
    out: list[CandidateMemory] = []
    for c in cands:
        key = c.content.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Internal: persistence
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Internal: structured value normalization
# ---------------------------------------------------------------------------

_MONTHS: dict[str, int] = {
    "januari": 1, "jan": 1, "january": 1,
    "februari": 2, "feb": 2, "february": 2,
    "maret": 3, "mar": 3, "march": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "agustus": 8, "agu": 8, "aug": 8, "august": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12, "december": 12, "dec": 12,
}


def _normalize_structured_candidate(
    cand: CandidateMemory,
    *,
    existing_profile: dict | None = None,
) -> CandidateMemory:
    """Normalize structured values before profile write / supersede."""
    if cand.structured_field != "birthday" or not cand.structured_value:
        return cand

    existing_birthday = None
    if isinstance(existing_profile, dict):
        existing_birthday = existing_profile.get("birthday")

    normalized = _normalize_birthday_value(
        cand.structured_value,
        existing_birthday=existing_birthday,
    )
    if not normalized:
        return cand

    content = cand.content
    if normalized not in content:
        content = f"User's birthday is {normalized}"

    return cand.model_copy(
        update={
            "content": content,
            "structured_value": normalized,
        }
    )


def _normalize_birthday_value(
    value: str,
    *,
    existing_birthday: str | None = None,
) -> str | None:
    """Return ISO YYYY-MM-DD when birthday can be safely normalized."""
    raw = " ".join(str(value or "").strip().split())
    if not raw:
        return None

    iso = _parse_iso_date(raw)
    if iso:
        return iso

    existing_year = _extract_year_from_iso(existing_birthday)
    parsed = _parse_day_month_year(raw)
    if not parsed:
        return None

    day, month, year = parsed
    if year is None:
        year = existing_year
    if year is None:
        return None

    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _parse_iso_date(value: str) -> str | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _extract_year_from_iso(value: str | None) -> int | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d{4})-\d{2}-\d{2}", str(value).strip())
    if not m:
        return None
    return int(m.group(1))


def _parse_day_month_year(value: str) -> tuple[int, int, int | None] | None:
    text = value.lower()
    text = re.sub(r"[,]", " ", text)
    text = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    m = re.search(
        r"\b(?P<day>\d{1,2})\s+(?P<month>[a-zA-Z]+)\s*(?P<year>\d{4})?\b",
        text,
    )
    if m:
        month = _MONTHS.get(m.group("month").lower())
        if not month:
            return None
        year = int(m.group("year")) if m.group("year") else None
        return int(m.group("day")), month, year

    m = re.search(
        r"\b(?P<month>[a-zA-Z]+)\s+(?P<day>\d{1,2})\s*(?P<year>\d{4})?\b",
        text,
    )
    if m:
        month = _MONTHS.get(m.group("month").lower())
        if not month:
            return None
        year = int(m.group("year")) if m.group("year") else None
        return int(m.group("day")), month, year

    return None


def _get_existing_identity_profile(user_id: str) -> dict:
    """Best-effort read of user_identity.profile for normalization decisions."""
    supabase = get_supabase()
    try:
        existing = (
            supabase.table("user_identity")
            .select("profile")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: identity profile read failed: %s", exc)
        return {}

    return (existing.data or {}).get("profile") or {} if existing else {}


def _get_active_structured_value(
    *,
    user_id: str,
    memory_id: str,
) -> str | None:
    """Fetch structured_value for an active memory id."""
    supabase = get_supabase()
    try:
        result = (
            supabase.table("memories")
            .select("structured_value")
            .eq("user_id", user_id)
            .eq("id", memory_id)
            .eq("superseded", False)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows:
            value = rows[0].get("structured_value")
            return str(value) if value is not None else None
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: active structured value read failed: %s", exc)
        return None


async def _persist_candidate(
    *,
    user_id: str,
    conversation_id: str,
    cand: CandidateMemory,
) -> dict:
    """Save one candidate. Handles supersede + structured identity write."""

    existing_profile = {}
    if cand.structured_field in _STRUCTURED_IDENTITY_FIELDS:
        existing_profile = _get_existing_identity_profile(user_id)

    cand = _normalize_structured_candidate(cand, existing_profile=existing_profile)

    # 1. If structured identity field, write to user_identity.profile too.
    if (
        cand.structured_field
        and cand.structured_field in _STRUCTURED_IDENTITY_FIELDS
        and cand.structured_value
    ):
        await _upsert_identity_field(
            user_id=user_id,
            field=cand.structured_field,
            value=cand.structured_value,
        )

    # 2. Embed.
    try:
        embedding = await embed_document(cand.content)
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: embed failed: %s", exc)
        return {"saved": False}

    # 3. Conflict resolution: look up existing same-category memories and
    #    check for high cosine similarity or structured_field match.
    superseded_id = _find_superseded(
        user_id=user_id,
        embedding=embedding,
        category=cand.category,
        structured_field=cand.structured_field,
        is_correction=cand.is_correction,
    )

    # 4. If an active structured memory already has the same value, treat it as
    #    still true and only bump last_confirmed_at. If the value differs, insert
    #    a new row and supersede the old one below.
    if superseded_id and cand.structured_field:
        existing_value = _get_active_structured_value(
            user_id=user_id,
            memory_id=superseded_id,
        )
        if existing_value == cand.structured_value:
            await _bump_last_confirmed(superseded_id)
            log.info(
                "memory_intelligence: confirmed existing structured memory %s (no new row)",
                superseded_id,
            )
            return {"saved": False, "confirmed": True}

    # 4b. If existing very-similar memory found AND not a correction, treat as
    #     "still true" — bump last_confirmed_at on the existing row, don't insert
    #     duplicate.
    if superseded_id and not cand.is_correction and not cand.structured_field:
        await _bump_last_confirmed(superseded_id)
        log.info(
            "memory_intelligence: confirmed existing memory %s (no new row)",
            superseded_id,
        )
        return {"saved": False, "confirmed": True}

    # 5. Insert new row.
    row = {
        "user_id": user_id,
        "content": cand.content,
        # Map category to legacy kind for backwards compat.
        "kind": _category_to_legacy_kind(cand.category),
        "embedding": embedding,
        "source": "auto",
        "source_conversation_id": conversation_id,
        "confidence": cand.confidence,
        "source_priority": cand.source_priority,
        "evidence": cand.evidence,
        "category": cand.category,
        # Structured identity field — written here so supersede lookups can
        # be deterministic (eq on column instead of ILIKE guess).
        "structured_field": cand.structured_field,
        "structured_value": cand.structured_value,
    }
    try:
        result = safe_execute(
            lambda sb: sb.table("memories").insert(row).execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: insert failed: %s", exc)
        return {"saved": False}

    if not result or not result.data:
        return {"saved": False}

    new_id = result.data[0]["id"]
    log.info(
        "memory_intelligence: saved '%s' (category=%s, source=%s, conf=%.2f)",
        cand.content[:60], cand.category, cand.source_priority, cand.confidence,
    )

    # 6. If there's an old memory to supersede, mark it.
    superseded = False
    if superseded_id and (cand.is_correction or cand.structured_field):
        try:
            safe_execute(
                lambda sb: sb.table("memories")
                .update({
                    "superseded": True,
                    "superseded_by": new_id,
                    "superseded_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", superseded_id)
                .execute()
            )
            superseded = True
            log.info(
                "memory_intelligence: superseded %s by %s", superseded_id, new_id
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("memory_intelligence: supersede failed: %s", exc)

    return {"saved": True, "superseded": superseded, "id": new_id}


def _find_superseded(
    *,
    user_id: str,
    embedding: list[float],
    category: str,
    structured_field: str | None,
    is_correction: bool,
) -> str | None:
    """Find an existing memory that the new candidate likely replaces.

    Priority:
      1. If structured_field set: deterministic lookup on user_id +
         structured_field + superseded=false. Single source of truth — works
         regardless of which category the old row was filed under (which
         changes over time as we tune the prompt).
      2. Otherwise: cosine similarity within same category.
    """
    supabase = get_supabase()

    # 1. Structured field — deterministic lookup by exact field name.
    # No ILIKE fragility, no category coupling. The structured_field column
    # is indexed for active rows so this is a single index lookup.
    if structured_field:
        try:
            result = (
                supabase.table("memories")
                .select("id, content")
                .eq("user_id", user_id)
                .eq("superseded", False)
                .eq("structured_field", structured_field)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["id"]
        except Exception as exc:  # noqa: BLE001
            log.warning("memory_intelligence: structured supersede lookup failed: %s", exc)

    # 2. Generic: cosine similarity over same-category active memories.
    try:
        result = supabase.rpc(
            "match_memories",
            {
                "p_user_id": user_id,
                "p_query_embedding": embedding,
                "p_match_count": 3,
            },
        ).execute()
        rows = result.data or []
        for r in rows:
            if r.get("similarity", 0) >= _DEDUP_SIMILARITY_THRESHOLD:
                # Same category? Only supersede within category.
                if r.get("category") == category:
                    return r["id"]
                # If correction explicitly, broader match allowed.
                if is_correction:
                    return r["id"]
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: cosine supersede lookup failed: %s", exc)
        return None


async def _bump_last_confirmed(memory_id: str) -> None:
    try:
        safe_execute(
            lambda sb: sb.table("memories")
            .update({"last_confirmed_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", memory_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: bump last_confirmed failed: %s", exc)


def _category_to_legacy_kind(category: str) -> str:
    """Map new category to the existing memories.kind enum.

    Old enum: fact, preference, context, plan.
    """
    mapping = {
        "identity": "fact",
        "preferences": "preference",
        "relationships": "fact",
        "routines": "context",
        "goals": "plan",
        "important_dates": "fact",
        "constraints": "context",
        "other": "context",
    }
    return mapping.get(category, "fact")


# ---------------------------------------------------------------------------
# Structured identity write — single-field merge into user_identity.profile
# ---------------------------------------------------------------------------


async def _upsert_identity_field(
    *,
    user_id: str,
    field: str,
    value: str,
) -> None:
    """Merge one field into user_identity.profile without replacing the whole row.

    life_model.upsert_identity() replaces the whole profile, which is unsafe
    here — we'd nuke other identity fields. So we do read-then-merge-then-write.

    Idempotent: if the same value already exists, no-op.
    """
    supabase = get_supabase()
    try:
        existing = (
            supabase.table("user_identity")
            .select("profile, narrative")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: identity read failed: %s", exc)
        return

    current_profile: dict = (existing.data or {}).get("profile") or {} if existing else {}
    narrative = (existing.data or {}).get("narrative") if existing else None

    if current_profile.get(field) == value:
        return  # already set

    merged = {**current_profile, field: value}
    try:
        safe_execute(
            lambda sb: sb.table("user_identity")
            .upsert(
                {
                    "user_id": user_id,
                    "profile": merged,
                    "narrative": narrative,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="user_id",
            )
            .execute()
        )
        log.info(
            "memory_intelligence: identity %s set %s='%s' (prev=%r)",
            user_id[:8], field, value, current_profile.get(field),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_intelligence: identity write failed: %s", exc)
