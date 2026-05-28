"""Reflection / Memory Consolidation v1.

Creates a small number of high-level, stable memories from existing memories.

Design:
- Manual-trigger first, no cron.
- Deterministic/rule-based in v1.
- Does not mutate companion mood.
- Does not store temporary user mood.
- Does not delete existing memories.
- Upserts by structured_field + structured_value to avoid duplicates.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.embeddings import embed_document
from app.services.supabase_client import safe_execute

log = logging.getLogger(__name__)


MAX_SOURCE_MEMORIES = 200
MAX_CANDIDATES = 4
MAX_EVIDENCE = 5


DEVELOPMENT_TERMS = (
    "aliyya",
    "assistant",
    "personal assistant",
    "memory",
    "memories",
    "mood",
    "relationship",
    "voice",
    "ui",
    "frontend",
    "backend",
    "deploy",
    "sidebar",
    "mobile",
)

UI_TERMS = (
    "ui",
    "vibes",
    "glass",
    "theme-aware",
    "theme",
    "dark",
    "light",
    "mobile",
    "smooth",
    "contrast",
    "sidebar",
    "back to chat",
)

CAREFUL_SUPPORT_TERMS = (
    "careful",
    "comprehensive",
    "hati-hati",
    "menyeluruh",
    "incremental",
    "patch",
    "debugging",
    "deploy",
    "terminal",
    "root-cause",
    "root cause",
)

RELATIONSHIP_TERMS = (
    "companion",
    "personal",
    "generic assistant",
    "relationship",
    "aliyya_relationship_style",
    "aliyya_coding_support_style",
)


@dataclass(frozen=True)
class ConsolidatedMemoryCandidate:
    content: str
    kind: str
    category: str
    structured_field: str
    structured_value: str
    confidence: float
    evidence: list[str]

    def as_payload(self, *, user_id: str, embedding: list[float] | None) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "user_id": user_id,
            "content": self.content,
            "kind": self.kind,
            "category": self.category,
            "structured_field": self.structured_field,
            "structured_value": self.structured_value,
            "confidence": self.confidence,
            "source_priority": "repeated_pattern",
            "evidence": self.evidence[:MAX_EVIDENCE],
            "superseded": False,
            "last_confirmed_at": now,
        }
        if embedding is not None:
            payload["embedding"] = embedding
        return payload


async def consolidate_and_persist(
    *,
    user_id: str,
    days: int = 30,
) -> dict[str, Any]:
    """Fetch recent active memories, consolidate stable patterns, and persist."""
    rows = await fetch_recent_active_memories(user_id=user_id, days=days)
    candidates = build_consolidation_candidates(rows, days=days)

    if not candidates:
        return {
            "ok": True,
            "saved": 0,
            "confirmed": 0,
            "candidates": 0,
            "source_memories": len(rows),
            "reason": "no_stable_pattern",
        }

    saved = 0
    confirmed = 0
    failed = 0
    actions: list[dict[str, Any]] = []

    for candidate in candidates[:MAX_CANDIDATES]:
        try:
            result = await _upsert_candidate(user_id=user_id, candidate=candidate)
            actions.append(result)
            if result.get("action") == "inserted":
                saved += 1
            elif result.get("action") == "confirmed_existing":
                confirmed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.warning("memory_consolidation: failed to persist candidate: %s", exc)

    return {
        "ok": failed == 0,
        "saved": saved,
        "confirmed": confirmed,
        "failed": failed,
        "candidates": len(candidates),
        "source_memories": len(rows),
        "actions": actions,
    }


async def fetch_recent_active_memories(*, user_id: str, days: int = 30) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    def _query():
        return safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id, content, kind, category, structured_field, structured_value, "
                "confidence, source_priority, evidence, superseded, "
                "last_confirmed_at, created_at"
            )
            .eq("user_id", user_id)
            .eq("superseded", False)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(MAX_SOURCE_MEMORIES)
            .execute()
        )

    result = await asyncio.to_thread(_query)
    return result.data or []


def build_consolidation_candidates(
    rows: list[dict[str, Any]],
    *,
    days: int = 30,
) -> list[ConsolidatedMemoryCandidate]:
    """Build high-level stable memories from existing memory rows."""
    active = [
        row
        for row in rows
        if row
        and not row.get("superseded")
        and str(row.get("content") or "").strip()
    ]

    if len(active) < 3:
        return []

    candidates: list[ConsolidatedMemoryCandidate] = []

    dev_rows = _matching_rows(active, DEVELOPMENT_TERMS)
    if len(dev_rows) >= 3:
        candidates.append(
            ConsolidatedMemoryCandidate(
                content=(
                    f"Over the last {days} days, user has been actively developing "
                    "Aliyya/My Personal Assistant with emphasis on memory reliability, "
                    "mood context, relationship continuity, UI polish, and mobile usability."
                ),
                kind="context",
                category="goals",
                structured_field="monthly_focus",
                structured_value="Aliyya development: memory reliability, mood context, relationship continuity, UI polish, and mobile usability",
                confidence=_confidence_from_count(len(dev_rows), base=0.74),
                evidence=_evidence(dev_rows),
            )
        )

    support_rows = _matching_rows(active, CAREFUL_SUPPORT_TERMS)
    if len(support_rows) >= 2:
        candidates.append(
            ConsolidatedMemoryCandidate(
                content=(
                    "A repeated interaction pattern is that user prefers careful, "
                    "complete, root-cause-oriented implementation help over incremental "
                    "or speculative fixes, especially during debugging and deployment."
                ),
                kind="preference",
                category="relationships",
                structured_field="consolidated_interaction_pattern",
                structured_value="Careful, complete, root-cause implementation support",
                confidence=_confidence_from_count(len(support_rows), base=0.78),
                evidence=_evidence(support_rows),
            )
        )

    ui_rows = _matching_rows(active, UI_TERMS)
    if len(ui_rows) >= 2:
        candidates.append(
            ConsolidatedMemoryCandidate(
                content=(
                    "A stable design preference is that user appreciates polished, "
                    "theme-aware UI with glass-like surfaces, good contrast, smooth "
                    "mobile behavior, and consistent page/sidebar interactions."
                ),
                kind="preference",
                category="preferences",
                structured_field="consolidated_ui_design_preference",
                structured_value="Polished, theme-aware UI with glass-like surfaces, good contrast, and smooth mobile behavior",
                confidence=_confidence_from_count(len(ui_rows), base=0.78),
                evidence=_evidence(ui_rows),
            )
        )

    relationship_rows = _matching_rows(active, RELATIONSHIP_TERMS)
    if len(relationship_rows) >= 2:
        candidates.append(
            ConsolidatedMemoryCandidate(
                content=(
                    "User wants Aliyya to maintain relationship continuity and feel like "
                    "a consistent personal assistant/companion, not a generic assistant."
                ),
                kind="preference",
                category="relationships",
                structured_field="consolidated_aliyya_relationship_preference",
                structured_value="Consistent personal assistant and companion, not a generic assistant",
                confidence=_confidence_from_count(len(relationship_rows), base=0.76),
                evidence=_evidence(relationship_rows),
            )
        )

    return _dedupe_candidates(candidates)


async def _upsert_candidate(
    *,
    user_id: str,
    candidate: ConsolidatedMemoryCandidate,
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

    existing = await asyncio.to_thread(_select_existing)
    rows = existing.data or []

    if rows:
        row = rows[0]
        memory_id = row.get("id")
        current_confidence = _safe_float(row.get("confidence"))
        next_confidence = max(current_confidence, candidate.confidence)

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
            "action": "confirmed_existing",
            "memory_id": memory_id,
            "structured_field": candidate.structured_field,
        }

    embedding = None
    try:
        embedding = await embed_document(candidate.content)
    except Exception as exc:  # noqa: BLE001
        log.warning("memory_consolidation: embedding failed, inserting without embedding: %s", exc)

    payload = candidate.as_payload(user_id=user_id, embedding=embedding)

    def _insert_new():
        return safe_execute(lambda sb: sb.table("memories").insert(payload).execute())

    inserted = await asyncio.to_thread(_insert_new)
    inserted_rows = inserted.data or []

    return {
        "action": "inserted",
        "memory_id": inserted_rows[0].get("id") if inserted_rows else None,
        "structured_field": candidate.structured_field,
    }


def _matching_rows(rows: list[dict[str, Any]], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        haystack = " ".join(
            str(part or "")
            for part in (
                row.get("content"),
                row.get("category"),
                row.get("structured_field"),
                row.get("structured_value"),
            )
        ).lower()
        if any(term.lower() in haystack for term in terms):
            out.append(row)
    return out


def _evidence(rows: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    seen: set[str] = set()

    for row in rows[:MAX_EVIDENCE]:
        text = _truncate(str(row.get("content") or "").strip(), 180)
        if not text or text in seen:
            continue
        seen.add(text)
        evidence.append(text)

    return evidence


def _confidence_from_count(count: int, *, base: float) -> float:
    return round(min(0.92, base + min(count, 6) * 0.025), 2)


def _dedupe_candidates(
    candidates: list[ConsolidatedMemoryCandidate],
) -> list[ConsolidatedMemoryCandidate]:
    seen: set[tuple[str, str]] = set()
    out: list[ConsolidatedMemoryCandidate] = []

    for candidate in candidates:
        key = (candidate.structured_field, candidate.structured_value)
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)

    return out


def _truncate(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
