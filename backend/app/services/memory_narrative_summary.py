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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _deterministic_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped = _group_memories(rows)
    memory_count = len(rows)
    quality = assess_memory_quality(rows)

    identity = _top_values(grouped.get("Identity", []), 4)
    preferences = _top_values(grouped.get("Preferences", []), 4)
    goals = _top_values(grouped.get("Goals", []) + grouped.get("Routines", []), 4)
    relationships = _top_values(grouped.get("Relationships", []), 4)
    constraints = _top_values(grouped.get("Constraints", []), 4)

    sentences: list[str] = []

    if identity:
        sentences.append(
            "From current memories, Aliyya understands several identity/profile details: "
            + "; ".join(identity)
            + "."
        )

    if preferences:
        sentences.append(
            "Aliyya also tracks preferences that may shape recommendations: "
            + "; ".join(preferences)
            + "."
        )

    if goals:
        sentences.append(
            "For planning and follow-through, Aliyya remembers goals or routines such as: "
            + "; ".join(goals)
            + "."
        )

    if relationships:
        sentences.append(
            "Aliyya has relationship context involving: "
            + "; ".join(relationships)
            + "."
        )

    if constraints:
        sentences.append(
            "Aliyya should also respect constraints or limits such as: "
            + "; ".join(constraints)
            + "."
        )

    if not sentences:
        sentences.append(
            "Aliyya does not yet have enough active memories to form a detailed understanding. "
            "As you chat and approve memories, this summary will become more useful."
        )

    needs_review = int(quality.get("summary", {}).get("needs_review") or 0)
    if needs_review > 0:
        needs_review_notes = [
            f"{needs_review} memor{'y' if needs_review == 1 else 'ies'} may need review before this understanding is fully reliable."
        ]
    else:
        needs_review_notes = ["No urgent memory cleanup is currently detected."]

    themes = [
        label
        for label, items in grouped.items()
        if items
    ][:8]

    return {
        "summary": "\n\n".join(sentences),
        "themes": themes,
        "confidence_notes": [
            f"This summary is based on {memory_count} active memor{'y' if memory_count == 1 else 'ies'}.",
            "Higher-confidence and structured memories are prioritized.",
        ],
        "needs_review_notes": needs_review_notes,
        "memory_count": memory_count,
        "generated_at": _now_iso(),
        "source": "deterministic",
    }


def _memory_brief_for_prompt(rows: list[dict[str, Any]]) -> str:
    grouped = _group_memories(rows)
    lines: list[str] = []

    for label, items in grouped.items():
        lines.append(f"## {label}")
        for row in items[:20]:
            confidence = row.get("confidence")
            source = row.get("source_priority") or row.get("source") or "unknown"
            value = str(row.get("content") or "").strip()
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
- No markdown fences. JSON only.
"""


def _coerce_summary_payload(parsed: Any, fallback: dict[str, Any], memory_count: int) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return fallback

    summary = str(parsed.get("summary") or "").strip()
    if not summary:
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
    if not use_llm:
        persisted = await _load_latest_persisted_summary(user_id)
        if persisted:
            return persisted

    rows = await _load_active_memories(user_id)
    fallback = _deterministic_summary(rows)

    if not use_llm or not rows:
        if not use_llm:
            await _persist_summary(user_id, fallback)
        return fallback

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
        return payload
    except Exception:
        await _persist_summary(user_id, fallback)
        return fallback
