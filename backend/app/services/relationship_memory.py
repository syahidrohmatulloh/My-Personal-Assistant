"""Relationship Memory Model v1.

Learns stable interaction preferences between the user and Aliyya.

Important:
- Does NOT mutate companion mood.
- Does NOT store temporary user mood.
- Does NOT infer romantic/dramatic relationship facts.
- Only stores durable interaction-style and relationship-continuity preferences.
- Deterministic/rule-based in v1.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.supabase_client import safe_execute

log = logging.getLogger(__name__)


CAREFUL_PATCH_TERMS = (
    "lebih teliti",
    "jangan incremental",
    "jangan bolak-balik",
    "jangan nebak",
    "perbaiki secara hati-hati",
    "menyeluruh",
    "jangan asal",
    "patch final",
    "full patch",
    "lebih hati-hati",
)

DIRECT_EDIT_TERMS = (
    "tolong edit",
    "kamu yang edit",
    "please proceed edit",
    "lanjut edit",
    "buatkan kodenya",
    "patch",
    "copy-paste",
    "langsung command",
)

UI_TASTE_TERMS = (
    "ui yang enak dilihat",
    "vibes",
    "glass",
    "theme",
    "dark",
    "terang",
    "mobile",
    "smooth",
    "kontras",
    "sidebar",
    "highlight",
    "back to chat",
    "serupa",
)

COMPANION_TERMS = (
    "aliyya",
    "personal companion",
    "bukan generic assistant",
    "companion",
    "relationship",
    "relasi",
    "personal assistant",
)


@dataclass(frozen=True)
class RelationshipMemoryCandidate:
    content: str
    kind: str
    category: str
    structured_field: str
    structured_value: str
    confidence: float
    source_priority: str
    evidence: list[str]

    def as_memory_payload(self, user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "content": self.content,
            "kind": self.kind,
            "category": self.category,
            "structured_field": self.structured_field,
            "structured_value": self.structured_value,
            "confidence": self.confidence,
            "source_priority": self.source_priority,
            "evidence": self.evidence,
            "superseded": False,
            "last_confirmed_at": datetime.now(timezone.utc).isoformat(),
        }


async def extract_and_persist(
    *,
    user_id: str,
    user_message: str,
    assistant_response: str | None = None,
) -> dict[str, Any]:
    """Extract and persist stable relationship/interaction preferences."""
    candidates = build_relationship_memory_candidates(
        user_message=user_message,
        assistant_response=assistant_response,
    )
    if not candidates:
        return {"saved": 0, "reason": "no_candidate"}

    saved = 0
    confirmed = 0
    failed = 0

    for candidate in candidates:
        try:
            result = await _upsert_candidate(user_id=user_id, candidate=candidate)
            if result.get("action") == "inserted":
                saved += 1
            elif result.get("action") == "confirmed_existing":
                confirmed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.warning("relationship_memory: persist failed: %s", exc)

    return {"saved": saved, "confirmed": confirmed, "failed": failed}


def build_relationship_memory_candidates(
    *,
    user_message: str,
    assistant_response: str | None = None,
) -> list[RelationshipMemoryCandidate]:
    """Return durable interaction preference candidates.

    v1 focuses on high-signal explicit user feedback only.
    """
    text = _norm(user_message)
    response_text = _norm(assistant_response or "")
    candidates: list[RelationshipMemoryCandidate] = []

    if _contains_any(text, CAREFUL_PATCH_TERMS) and (
        _contains_any(text, DIRECT_EDIT_TERMS) or "error" in text or "build" in text
    ):
        candidates.append(
            RelationshipMemoryCandidate(
                content=(
                    "User prefers Aliyya to make careful, comprehensive fixes "
                    "instead of incremental or speculative patches, especially "
                    "during coding/debugging work."
                ),
                kind="preference",
                category="relationships",
                structured_field="aliyya_coding_support_style",
                structured_value="careful_comprehensive_fixes_not_incremental_guessing",
                confidence=0.86,
                source_priority="explicit_user_statement",
                evidence=_evidence(user_message, response_text),
            )
        )

    if _contains_any(text, UI_TASTE_TERMS) and _contains_any(
        text,
        ("ui", "ux", "vibes", "mobile", "sidebar", "theme", "contrast", "kontras"),
    ):
        candidates.append(
            RelationshipMemoryCandidate(
                content=(
                    "User appreciates polished, calm, glassy, theme-aware UI "
                    "with good contrast, smooth mobile behavior, and consistent "
                    "visual language across pages."
                ),
                kind="preference",
                category="preferences",
                structured_field="ui_design_taste",
                structured_value="polished_glassy_theme_aware_mobile_smooth_consistent",
                confidence=0.82,
                source_priority="explicit_user_statement",
                evidence=_evidence(user_message, response_text),
            )
        )

    if _contains_any(text, COMPANION_TERMS) and (
        "generic" in text or "personal" in text or "companion" in text
    ):
        candidates.append(
            RelationshipMemoryCandidate(
                content=(
                    "User wants Aliyya to feel like a consistent personal "
                    "assistant/companion rather than a generic assistant."
                ),
                kind="preference",
                category="relationships",
                structured_field="aliyya_relationship_style",
                structured_value="consistent_personal_companion_not_generic_assistant",
                confidence=0.80,
                source_priority="explicit_user_statement",
                evidence=_evidence(user_message, response_text),
            )
        )

    return candidates


async def _upsert_candidate(
    *,
    user_id: str,
    candidate: RelationshipMemoryCandidate,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    def _select_existing():
        return safe_execute(
            lambda sb: sb.table("memories")
            .select("id, confidence")
            .eq("user_id", user_id)
            .eq("structured_field", candidate.structured_field)
            .eq("structured_value", candidate.structured_value)
            .eq("superseded", False)
            .limit(1)
            .execute()
        )

    result = await asyncio.to_thread(_select_existing)
    rows = result.data or []

    if rows:
        existing = rows[0]
        memory_id = existing.get("id")
        existing_confidence = _to_float(existing.get("confidence")) or 0.0
        next_confidence = max(existing_confidence, candidate.confidence)

        def _update_existing():
            return safe_execute(
                lambda sb: sb.table("memories")
                .update(
                    {
                        "confidence": next_confidence,
                        "last_confirmed_at": now,
                    }
                )
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute()
            )

        await asyncio.to_thread(_update_existing)
        return {
            "saved": True,
            "action": "confirmed_existing",
            "memory_id": memory_id,
            "structured_field": candidate.structured_field,
        }

    payload = candidate.as_memory_payload(user_id)

    def _insert_new():
        return safe_execute(lambda sb: sb.table("memories").insert(payload).execute())

    inserted = await asyncio.to_thread(_insert_new)
    inserted_rows = inserted.data or []

    return {
        "saved": True,
        "action": "inserted",
        "memory_id": inserted_rows[0].get("id") if inserted_rows else None,
        "structured_field": candidate.structured_field,
    }


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    """Match terms safely.

    Short terms like "ui" and "ux" must match as whole words only.
    Otherwise words like "quiet" can accidentally match "ui".
    """
    for term in terms:
        normalized = str(term or "").lower().strip()
        if not normalized:
            continue

        if len(normalized) <= 3 and normalized.isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
                return True
            continue

        if normalized in text:
            return True

    return False


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _truncate(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _evidence(user_message: str, assistant_response: str) -> list[str]:
    evidence = [_truncate(user_message, 220)]
    if assistant_response:
        evidence.append("assistant_response_observed")
    return evidence


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
