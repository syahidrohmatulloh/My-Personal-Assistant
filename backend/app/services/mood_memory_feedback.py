"""Mood-Memory Feedback Loop v1.

Converts repeated mood + task-context patterns into conservative behavioral
preference memories.

Important:
- Does NOT infer or mutate companion mood.
- Does NOT store temporary emotions as permanent memory.
- Does NOT touch companion_settings or companion_mood_state.
- Deterministic/rule-based in v1.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.supabase_client import safe_execute

log = logging.getLogger(__name__)


DEBUGGING_TERMS = (
    "error",
    "failed",
    "traceback",
    "pytest",
    "deploy",
    "flyctl",
    "vercel",
    "supabase",
    "build",
    "bug",
    "patch",
    "terminal",
    "command",
    "log",
    "exception",
    "gagal",
    "errornya",
    "tes",
)

FRUSTRATION_TERMS = (
    "capek",
    "pusing",
    "frustrated",
    "frustrasi",
    "bingung",
    "kesel",
    "bolak-balik",
    "ga kelar",
    "gak kelar",
    "ribet",
    "stuck",
)

DIRECT_COMMAND_TERMS = (
    "paste",
    "copy-paste",
    "command",
    "terminal",
    "langsung",
    "edit",
    "patch",
    "tolong edit",
)


@dataclass(frozen=True)
class BehavioralMemoryCandidate:
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
    user_mood_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and persist a behavioral memory candidate if signal is strong.

    This is intentionally narrow in v1. It only writes a stable preference about
    debugging/deployment support style under frustration. It never stores the
    user's temporary mood itself.
    """
    candidate = build_behavioral_memory_candidate(
        user_message=user_message,
        assistant_response=assistant_response,
        user_mood_context=user_mood_context,
    )
    if candidate is None:
        return {"saved": False, "reason": "no_candidate"}

    try:
        return await _upsert_candidate(user_id=user_id, candidate=candidate)
    except Exception as exc:  # noqa: BLE001
        log.warning("mood_memory_feedback: persist failed: %s", exc)
        return {"saved": False, "reason": "persist_failed"}


def build_behavioral_memory_candidate(
    *,
    user_message: str,
    assistant_response: str | None = None,
    user_mood_context: dict[str, Any] | None = None,
) -> BehavioralMemoryCandidate | None:
    """Return a behavioral memory candidate if the pattern is strong enough."""
    text = _norm(user_message)
    response_text = _norm(assistant_response or "")

    mood_hint = _extract_mood_hint(user_mood_context)
    has_frustration = _contains_any(text, FRUSTRATION_TERMS) or mood_hint in {
        "frustrated",
        "stressed",
        "tired",
        "overwhelmed",
    }
    has_debugging_context = _contains_any(text, DEBUGGING_TERMS)
    asks_direct_action = _contains_any(text, DIRECT_COMMAND_TERMS)

    # Require task context + either frustration or direct action preference.
    if not has_debugging_context or not (has_frustration or asks_direct_action):
        return None

    has_command_response = any(
        marker in response_text
        for marker in ("cd ", "python", "pytest", "git ", "flyctl", "pnpm", "uv run")
    )

    confidence = 0.72
    if has_frustration and asks_direct_action:
        confidence += 0.08
    if has_command_response:
        confidence += 0.05
    confidence = min(confidence, 0.85)

    evidence = [_truncate(user_message, 180)]
    if mood_hint:
        evidence.append(f"user_mood_hint={mood_hint}")
    if has_command_response:
        evidence.append("assistant_response_included_terminal_commands")

    return BehavioralMemoryCandidate(
        content=(
            "When debugging or deployment issues feel frustrating, user prefers "
            "direct paste-ready terminal commands, root-cause diagnosis first, "
            "and minimal broad theory."
        ),
        kind="preference",
        category="preferences",
        structured_field="debugging_support_style_under_frustration",
        structured_value="paste_ready_commands_root_cause_first_minimal_theory",
        confidence=round(confidence, 2),
        source_priority="repeated_pattern",
        evidence=evidence,
    )


async def _upsert_candidate(
    *,
    user_id: str,
    candidate: BehavioralMemoryCandidate,
) -> dict[str, Any]:
    """Multi-user-safe dedupe by structured_field + structured_value."""
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


def _extract_mood_hint(ctx: dict[str, Any] | None) -> str | None:
    if not ctx:
        return None

    current = ctx.get("current_message_signal") or {}
    hint = current.get("mood_hint")
    if isinstance(hint, str) and hint.strip():
        return hint.strip().lower()

    latest = ctx.get("latest") or {}
    stress = _to_float(latest.get("stress"))
    energy = _to_float(latest.get("energy"))
    mood = _to_float(latest.get("mood"))

    if stress is not None and stress >= 3:
        return "stressed"
    if energy is not None and energy <= -3:
        return "tired"
    if mood is not None and mood <= -3:
        return "low"

    return None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truncate(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
