"""Generate a human-friendly narrative summary of the user's active memories.

This is intentionally read-only:
- It does not create, edit, archive, or delete memories.
- It summarizes active, non-superseded memories.
- The POST endpoint can use Claude to produce a warm narrative.
- The GET endpoint returns a deterministic fallback so the UI always has something safe.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.services import memory_epistemic_governance
from app.services.claude import get_claude
from app.services.memory_quality import assess_memory_quality
from app.services.supabase_client import safe_execute


_MEMORY_SELECT = (
    "id, content, kind, category, structured_field, structured_value, "
    "confidence, source, source_priority, evidence, last_confirmed_at, "
    "last_user_confirmed_at, last_user_confirmation_source, "
    "created_at, updated_at, archived, superseded"
)

NARRATIVE_GOVERNANCE_VERSION = "m35c3-v1"

_DIRECT_USER_PRIORITIES = frozenset(
    {
        "explicit_user_statement",
        "user_answer_in_context",
        "user_correction",
    }
)

# Compact token persisted in the existing `source` column so we can
# invalidate pre-M35C3 summaries without another schema migration.
_PERSISTED_GOVERNANCE_TOKEN = "g1"

_PERSISTED_SOURCE_CODES = {
    "deterministic": "d",
    "llm": "l",
}

_PERSISTED_SOURCE_NAMES = {
    value: key
    for key, value in _PERSISTED_SOURCE_CODES.items()
}

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


def _is_authoritative_memory(
    row: dict[str, Any],
) -> bool:
    """Return whether a row may support reliable user biography."""

    source_priority = str(
        row.get("source_priority") or ""
    ).strip().lower()

    if source_priority in _DIRECT_USER_PRIORITIES:
        return True

    # Canonical confirmation can upgrade otherwise weak provenance.
    # Legacy last_confirmed_at is intentionally ignored here.
    return (
        memory_epistemic_governance
        .has_confirmation(row)
    )


def _authoritative_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if _is_authoritative_memory(row)
    ]


def _authoritative_source_hash(
    rows: list[dict[str, Any]],
) -> str:
    """Stable fingerprint of authoritative narrative evidence."""

    canonical: list[dict[str, Any]] = []

    for row in _authoritative_rows(rows):
        canonical.append(
            {
                "id": str(
                    row.get("id") or ""
                ),
                "content": str(
                    row.get("content") or ""
                ),
                "kind": str(
                    row.get("kind") or ""
                ),
                "category": str(
                    row.get("category") or ""
                ),
                "structured_field": str(
                    row.get("structured_field")
                    or ""
                ),
                "structured_value": str(
                    row.get("structured_value")
                    or ""
                ),
                "source_priority": str(
                    row.get("source_priority")
                    or ""
                ),
                "last_user_confirmed_at": str(
                    row.get(
                        "last_user_confirmed_at"
                    )
                    or ""
                ),
                "updated_at": str(
                    row.get("updated_at")
                    or row.get("created_at")
                    or ""
                ),
            }
        )

    canonical.sort(
        key=lambda item: (
            item["id"],
            item["structured_field"],
            item["structured_value"],
            item["content"],
        )
    )

    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    # 64 bits is ample for personal-scale cache invalidation while keeping
    # the existing source-column token compact.
    return hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()[:16]


def _latest_authoritative_changed_at(
    rows: list[dict[str, Any]],
) -> str | None:
    values: list[str] = []

    for row in _authoritative_rows(rows):
        for key in (
            "updated_at",
            "last_user_confirmed_at",
            "created_at",
        ):
            value = str(
                row.get(key) or ""
            ).strip()
            if value:
                values.append(value)

    return max(values) if values else None


def _encode_persisted_source(
    source: str,
    source_hash: str,
) -> str:
    source_name = str(
        source or "deterministic"
    ).strip().lower()

    code = _PERSISTED_SOURCE_CODES.get(
        source_name,
        "d",
    )

    fingerprint = str(
        source_hash or ""
    ).strip()[:16]

    if not fingerprint:
        raise ValueError(
            "source_hash is required for governed "
            "narrative persistence"
        )

    return (
        f"{code}|"
        f"{_PERSISTED_GOVERNANCE_TOKEN}|"
        f"{fingerprint}"
    )


def _decode_persisted_source(
    value: Any,
) -> dict[str, str] | None:
    parts = str(
        value or ""
    ).strip().split("|")

    if len(parts) != 3:
        # Plain old values such as `deterministic` or `llm` are pre-M35C3
        # and must never be reused as authoritative biography.
        return None

    source_code, governance_token, source_hash = parts

    if (
        governance_token
        != _PERSISTED_GOVERNANCE_TOKEN
    ):
        return None

    source_name = _PERSISTED_SOURCE_NAMES.get(
        source_code
    )

    if source_name is None:
        return None

    source_hash = source_hash.strip()

    if len(source_hash) != 16:
        return None

    return {
        "source": source_name,
        "governance_version": (
            NARRATIVE_GOVERNANCE_VERSION
        ),
        "source_hash": source_hash,
    }


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


def _deterministic_summary(
    rows: list[dict[str, Any]],
    *,
    source_hash: str | None = None,
) -> dict[str, Any]:
    """Safe editorial fallback over authoritative biography only."""

    authoritative_rows = _authoritative_rows(
        rows
    )
    safe_rows = _safe_rows(
        authoritative_rows
    )
    memory_count = len(
        authoritative_rows
    )
    safe_count = len(safe_rows)
    quality = assess_memory_quality(
        authoritative_rows
    )

    if source_hash is None:
        source_hash = (
            _authoritative_source_hash(
                authoritative_rows
            )
        )
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
            f"Aliyya has started building a memory base about you, but the current understanding is still early. She has {memory_count} reliable memories, although only a small portion is clean enough to summarize confidently.\n\n"
            "At this stage, treat the summary as a rough orientation rather than a complete profile. Reviewing noisy or outdated memories will help Aliyya become more accurate."
        )
    else:
        theme_sentence = _natural_theme_sentence(counts)

        summary = (
            f"Aliyya currently has {memory_count} reliable memories about you. {theme_sentence} These memories help her keep continuity across conversations, so she can respond with more context instead of starting from zero each time.\n\n"
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
            f"This summary is based on {memory_count} authoritative memories.",
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
        "governance_version": (
            NARRATIVE_GOVERNANCE_VERSION
        ),
        "source_hash": source_hash,
    }


def _memory_brief_for_prompt(
    rows: list[dict[str, Any]],
) -> str:
    authoritative_rows = (
        _authoritative_rows(rows)
    )
    grouped = _group_memories(
        _safe_rows(authoritative_rows)
    )
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

Input: authoritative memories grounded in direct user evidence or explicit user confirmation.
Output STRICT JSON:
{
  "summary": "4-7 short, warm paragraphs in second person or natural assistant voice. Do not invent facts. Mention uncertainty when needed.",
  "themes": ["short theme", "..."],
  "confidence_notes": ["what seems well-supported", "..."],
  "needs_review_notes": ["what may need review or may be outdated", "..."]
}

Rules:
- Use ONLY the provided authoritative memories.
- Never promote unverified inference into user biography.
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


def _coerce_summary_payload(
    parsed: Any,
    fallback: dict[str, Any],
    memory_count: int,
    source_hash: str,
) -> dict[str, Any]:
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
        "governance_version": (
            NARRATIVE_GOVERNANCE_VERSION
        ),
        "source_hash": source_hash,
    }


async def _load_latest_persisted_summary(
    user_id: str,
    *,
    expected_source_hash: str,
) -> dict[str, Any] | None:
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

    source_meta = _decode_persisted_source(
        row.get("source")
    )

    if source_meta is None:
        return None

    if (
        source_meta["source_hash"]
        != expected_source_hash
    ):
        # Memory authority/content changed since this summary was created.
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
        "memory_count": int(
            row.get("memory_count") or 0
        ),
        "generated_at": str(
            row.get("generated_at")
            or _now_iso()
        ),
        "source": source_meta["source"],
        "governance_version": (
            source_meta[
                "governance_version"
            ]
        ),
        "source_hash": (
            source_meta["source_hash"]
        ),
    }


async def _persist_summary(
    user_id: str,
    payload: dict[str, Any],
) -> None:
    source_hash = str(
        payload.get("source_hash") or ""
    ).strip()

    if not source_hash:
        # Never create a persisted summary that cannot later prove which
        # authoritative evidence set produced it.
        return

    governed_source = (
        _encode_persisted_source(
            str(
                payload.get("source")
                or "deterministic"
            ),
            source_hash,
        )
    )

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
                        "source": governed_source,
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
    # Load current memory state BEFORE considering persisted narrative reuse.
    # The persisted summary is valid only if its governed source hash matches
    # the current authoritative evidence set.
    rows = await _load_active_memories(
        user_id
    )
    authoritative_rows = (
        _authoritative_rows(rows)
    )

    source_hash = (
        _authoritative_source_hash(
            authoritative_rows
        )
    )
    latest_changed_at = (
        _latest_authoritative_changed_at(
            authoritative_rows
        )
    )

    if not use_llm:
        persisted = (
            await _load_latest_persisted_summary(
                user_id,
                expected_source_hash=(
                    source_hash
                ),
            )
        )
        if persisted:
            return _with_freshness(
                persisted,
                latest_changed_at,
            )

    fallback = _deterministic_summary(
        authoritative_rows,
        source_hash=source_hash,
    )

    if (
        not use_llm
        or not authoritative_rows
    ):
        if not use_llm:
            await _persist_summary(
                user_id,
                fallback,
            )
        return _with_freshness(
            fallback,
            latest_changed_at,
        )

    brief = _memory_brief_for_prompt(
        authoritative_rows
    )

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
                        "Create the user's current memory narrative summary "
                        "from these authoritative memories:\n\n"
                        + brief[:12000]
                    ),
                }
            ],
        )

        text_block = next(
            (
                block
                for block in response.content
                if block.type == "text"
            ),
            None,
        )

        if not text_block:
            return _with_freshness(
                fallback,
                latest_changed_at,
            )

        raw = text_block.text.strip()

        if raw.startswith("```"):
            raw = (
                raw.strip("`")
                .lstrip("json")
                .strip()
            )

        parsed = json.loads(raw)

        payload = _coerce_summary_payload(
            parsed,
            fallback,
            len(authoritative_rows),
            source_hash,
        )

        await _persist_summary(
            user_id,
            payload,
        )

        return _with_freshness(
            payload,
            latest_changed_at,
        )
    except Exception:
        await _persist_summary(
            user_id,
            fallback,
        )
        return _with_freshness(
            fallback,
            latest_changed_at,
        )
