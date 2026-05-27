"""Generate a human-friendly narrative summary of the user's active memories.

This is intentionally read-only:
- It does not create, edit, archive, or delete memories.
- It summarizes active, non-superseded memories.
- The POST endpoint can use Claude to produce a warm narrative.
- The GET endpoint returns a deterministic fallback so the UI always has something safe.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.services.claude import get_claude
from app.services.memory_quality import assess_memory_quality
from app.services.supabase_client import safe_execute


_MEMORY_SELECT = (
    "id, content, kind, category, structured_field, structured_value, "
    "confidence, source_priority, evidence, last_confirmed_at, created_at, "
    "archived, superseded"
)

_CATEGORY_LABELS = {
    "identity": "Identity",
    "important_dates": "Important dates",
    "preferences": "Preferences",
    "relationships": "Relationships",
    "routines": "Routines",
    "goals": "Goals",
    "constraints": "Constraints",
    "other": "Other",
}


_RAW_MEMORY_MARKERS = [
    "due_date=",
    "start_at=",
    "end_at=",
    "goal_id=",
    "location=",
    "title=",
    "polished_theme",
    "aware_glass",
    "mobile_smooth",
    "consistent_personal",
    "companion_not_generic",
    " | ",
]

_INTERNAL_MEMORY_VALUES = {
    "aliyya",
    "beb",
    "wib",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _latest_memory_changed_at(user_id: str) -> str | None:
    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .select("created_at, updated_at")
                .eq("user_id", user_id)
                .eq("superseded", False)
                .or_("archived.is.false,archived.is.null")
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
        )
    except Exception:
        return None

    rows = list(result.data or [])
    if not rows:
        return None

    row = rows[0]
    return str(row.get("updated_at") or row.get("created_at") or "") or None


def _with_freshness(payload: dict[str, Any], latest_memory_changed_at: str | None) -> dict[str, Any]:
    generated_at = str(payload.get("generated_at") or "")
    is_stale = bool(latest_memory_changed_at and generated_at and latest_memory_changed_at > generated_at)

    return {
        **payload,
        "is_stale": is_stale,
        "latest_memory_changed_at": latest_memory_changed_at,
    }


async def _load_active_memories(user_id: str) -> list[dict[str, Any]]:
    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .select(_MEMORY_SELECT)
            .eq("user_id", user_id)
            .eq("superseded", False)
            .or_("archived.is.false,archived.is.null")
            .order("confidence", desc=True)
            .order("created_at", desc=True)
            .limit(220)
            .execute()
        )
    )

    return list(result.data or [])


def _category_label(value: Any) -> str:
    key = str(value or "other").strip().lower()
    return _CATEGORY_LABELS.get(key, key.replace("_", " ").title() or "Other")


def _memory_value(row: dict[str, Any]) -> str:
    structured_value = str(row.get("structured_value") or "").strip()
    content = str(row.get("content") or "").strip()
    return structured_value or content


def _is_raw_or_internal_text(value: str) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()

    if not text:
        return True

    if lowered in _INTERNAL_MEMORY_VALUES:
        return True

    if any(marker in lowered for marker in _RAW_MEMORY_MARKERS):
        return True

    # Snake-case UI config strings are not meaningful to users.
    if "_" in text and len(text.split()) <= 3:
        return True

    # Date metadata strings are usually raw scheduler/calendar rows.
    if "t00:00" in lowered or "+07:00" in lowered or "+00:00" in lowered:
        return True

    return False


def _safe_memory_text(row: dict[str, Any]) -> str | None:
    content = str(row.get("content") or "").strip()
    structured_value = str(row.get("structured_value") or "").strip()

    for candidate in [content, structured_value]:
        if candidate and not _is_raw_or_internal_text(candidate):
            return candidate

    return None


def _safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []

    for row in rows:
        if _safe_memory_text(row):
            safe.append(row)

    return safe


def _group_memories(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        label = _category_label(row.get("category"))
        grouped.setdefault(label, []).append(row)

    return grouped


def _top_values(rows: list[dict[str, Any]], limit: int = 5) -> list[str]:
    values: list[str] = []

    for row in rows[:limit]:
        value = _memory_value(row)
        if value and value not in values:
            values.append(value)

    return values


def _summary_looks_raw(summary: str) -> bool:
    lowered = str(summary or "").lower()

    if any(marker in lowered for marker in _RAW_MEMORY_MARKERS):
        return True

    raw_patterns = [
        "identity/profile details:",
        "preferences that may shape recommendations:",
        "goals or routines such as:",
        "relationship context involving:",
        "constraints or limits such as:",
    ]

    return any(pattern in lowered for pattern in raw_patterns)


def _category_counts(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    grouped = _group_memories(rows)
    counts = [(label, len(items)) for label, items in grouped.items() if items]
    counts.sort(key=lambda item: item[1], reverse=True)
    return counts


def _natural_theme_sentence(counts: list[tuple[str, int]]) -> str:
    if not counts:
        return "Aliyya is still building her understanding of you."

    labels = [label for label, _count in counts if label != "Other"][:5]
    if not labels and counts:
        labels = [counts[0][0]]

    if len(labels) == 1:
        return f"The clearest area of memory is {labels[0].lower()}."
    if len(labels) == 2:
        return f"The clearest areas of memory are {labels[0].lower()} and {labels[1].lower()}."

    return (
        "The clearest areas of memory are "
        + ", ".join(label.lower() for label in labels[:-1])
        + f", and {labels[-1].lower()}."
    )


def _deterministic_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Safe editorial fallback.

    This does NOT list raw memories. It describes the shape of Aliyya's
    understanding in natural language.
    """
    safe_rows = _safe_rows(rows)
    memory_count = len(rows)
    safe_count = len(safe_rows)
    quality = assess_memory_quality(rows)
    counts = _category_counts(safe_rows)
    themes = [label for label, _count in counts if label != "Other"][:8]
    needs_review = int(quality.get("summary", {}).get("needs_review") or 0)

    if memory_count <= 0:
        summary = (
            "Aliyya is still building her understanding of you. She does not yet have enough active, reliable memories to summarize who you are or how she should support you.\n\n"
            "As your chats continue and you approve useful memories, this section will become a warmer summary of your work, preferences, routines, relationships, and constraints."
        )
    elif safe_count <= 3:
        summary = (
            f"Aliyya has started building a memory base about you, but the current understanding is still early. She has {memory_count} active memories, although only a small portion is clean enough to summarize confidently.\n\n"
            "At this stage, treat the summary as a rough orientation rather than a complete profile. Reviewing noisy or outdated memories will help Aliyya become more accurate."
        )
    else:
        theme_sentence = _natural_theme_sentence(counts)

        summary = (
            f"Aliyya currently has {memory_count} active memories about you. {theme_sentence} These memories help her keep continuity across conversations, so she can respond with more context instead of starting from zero each time.\n\n"
            "From the available memory base, Aliyya is trying to understand your identity and working context, the preferences that should shape her suggestions, the goals or routines you return to, important people or relationships, and constraints she should respect.\n\n"
            "This is not meant to be a permanent biography. It is a living understanding that should be corrected whenever something is outdated, duplicated, too vague, or no longer useful."
        )

    if needs_review > 0:
        summary += (
            f"\n\nThere are currently {needs_review} memories that may need review. Cleaning them up will make this summary more accurate and make Aliyya less likely to rely on noisy details."
        )

    return {
        "summary": summary,
        "themes": themes,
        "confidence_notes": [
            f"This summary is based on {memory_count} active memories.",
            "Raw scheduler fields, internal UI settings, and unclear technical fragments are intentionally excluded from the narrative.",
        ],
        "needs_review_notes": [
            f"{needs_review} memory item{'s' if needs_review != 1 else ''} may need review."
            if needs_review > 0
            else "No urgent memory cleanup is currently detected."
        ],
        "memory_count": memory_count,
        "generated_at": _now_iso(),
        "source": "deterministic",
    }


def _memory_brief_for_prompt(rows: list[dict[str, Any]]) -> str:
    grouped = _group_memories(_safe_rows(rows))
    lines: list[str] = []

    for label, items in grouped.items():
        if not items:
            continue

        lines.append(f"## {label}")
        for row in items[:14]:
            confidence = row.get("confidence")
            source = row.get("source_priority") or row.get("source") or "unknown"
            value = _safe_memory_text(row)
            if not value:
                continue
            lines.append(f"- {value} | confidence={confidence} | source={source}")

    return "\n".join(lines)


_SYSTEM_PROMPT = """You are summarizing what a personal AI assistant currently understands about its user.

Input: active memories extracted from past chats.
Output STRICT JSON:
{
  "summary": "4-7 short, warm paragraphs in second person or natural assistant voice. Do not invent facts. Mention uncertainty when needed.",
  "themes": ["short theme", "..."],
  "confidence_notes": ["what seems well-supported", "..."],
  "needs_review_notes": ["what may need review or may be outdated", "..."]
}

Rules:
- Use ONLY the provided memories.
- Do not expose raw database language.
- Do not say the user has an attribute unless the memory directly supports it.
- Keep it concise, warm, and useful.
- If memories are thin, say that clearly.
- NEVER copy raw structured strings such as due_date=, start_at=, end_at=, goal_id=, location=, title=, or pipe-separated internal fields.
- NEVER mention internal UI/style settings such as polished_theme, aware_glass, mobile_smooth, or similar technical tokens.
- If a memory looks like internal metadata, ignore it.
- Write a polished narrative, not a database summary.
- The summary should sound like an assistant's thoughtful understanding, not a list of extracted fields.
- No markdown fences. JSON only.
"""


def _coerce_summary_payload(parsed: Any, fallback: dict[str, Any], memory_count: int) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return fallback

    summary = str(parsed.get("summary") or "").strip()
    if not summary or _summary_looks_raw(summary):
        return fallback

    def list_of_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:8]

    return {
        "summary": summary,
        "themes": list_of_strings(parsed.get("themes")),
        "confidence_notes": list_of_strings(parsed.get("confidence_notes")),
        "needs_review_notes": list_of_strings(parsed.get("needs_review_notes")),
        "memory_count": memory_count,
        "generated_at": _now_iso(),
        "source": "llm",
    }


async def _load_latest_persisted_summary(user_id: str) -> dict[str, Any] | None:
    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memory_narrative_summaries")
                .select(
                    "summary, themes, confidence_notes, needs_review_notes, "
                    "memory_count, source, generated_at"
                )
                .eq("user_id", user_id)
                .order("generated_at", desc=True)
                .limit(1)
                .execute()
            )
        )
    except Exception:
        return None

    rows = list(result.data or [])
    if not rows:
        return None

    row = rows[0]
    summary = str(row.get("summary") or "").strip()
    if not summary:
        return None

    if _summary_looks_raw(summary):
        return None

    def list_value(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    return {
        "summary": summary,
        "themes": list_value(row.get("themes")),
        "confidence_notes": list_value(row.get("confidence_notes")),
        "needs_review_notes": list_value(row.get("needs_review_notes")),
        "memory_count": int(row.get("memory_count") or 0),
        "generated_at": str(row.get("generated_at") or _now_iso()),
        "source": str(row.get("source") or "persisted"),
    }


async def _persist_summary(user_id: str, payload: dict[str, Any]) -> None:
    try:
        await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memory_narrative_summaries")
                .insert(
                    {
                        "user_id": user_id,
                        "summary": payload.get("summary") or "",
                        "themes": payload.get("themes") or [],
                        "confidence_notes": payload.get("confidence_notes") or [],
                        "needs_review_notes": payload.get("needs_review_notes") or [],
                        "memory_count": int(payload.get("memory_count") or 0),
                        "source": payload.get("source") or "deterministic",
                        "generated_at": payload.get("generated_at") or _now_iso(),
                    }
                )
                .execute()
            )
        )
    except Exception:
        # Persistence must never break the user-facing summary endpoint.
        return


async def get_memory_narrative_summary(
    *,
    user_id: str,
    use_llm: bool = False,
) -> dict[str, Any]:
    latest_changed_at = await _latest_memory_changed_at(user_id)

    if not use_llm:
        persisted = await _load_latest_persisted_summary(user_id)
        if persisted:
            return _with_freshness(persisted, latest_changed_at)

    rows = await _load_active_memories(user_id)
    fallback = _deterministic_summary(rows)

    if not use_llm or not rows:
        if not use_llm:
            await _persist_summary(user_id, fallback)
        return _with_freshness(fallback, latest_changed_at)

    brief = _memory_brief_for_prompt(rows)

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1200,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Create the user's current memory narrative summary from these active memories:\n\n"
                        + brief[:12000]
                    ),
                }
            ],
        )

        text_block = next((block for block in response.content if block.type == "text"), None)
        if not text_block:
            return fallback

        raw = text_block.text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()

        parsed = json.loads(raw)
        payload = _coerce_summary_payload(parsed, fallback, len(rows))
        await _persist_summary(user_id, payload)
        return _with_freshness(payload, latest_changed_at)
    except Exception:
        await _persist_summary(user_id, fallback)
        return _with_freshness(fallback, latest_changed_at)
