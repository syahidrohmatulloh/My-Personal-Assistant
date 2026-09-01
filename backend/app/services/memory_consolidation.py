"""M33 — deterministic evidence consolidation for durable memory.

"Dream cycle" is an engineering metaphor for deferred, low-priority memory
maintenance. M33 does not generate dreams and does not invent new user facts.

Canonical boundaries:
- consolidate evidence, not semantics;
- never create a new memory claim during the automatic cycle;
- never raise confidence or set last_confirmed_at;
- never auto-archive/delete/supersede source memories;
- only use active, trusted user-authored source rows;
- exclude unverified repeated-pattern inference from consolidation;
- exclude identity / important-date synthesis and sensitive profiling;
- deterministic only: no LLM, embeddings, or external provider calls;
- return structured audit data; do not emit a second per-turn cognitive trace.

The existing public functions ``build_consolidation_candidates`` and
``consolidate_and_persist`` remain available for compatibility.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.memory_lifecycle_governance import assess_memory_lifecycle
from app.services.supabase_client import safe_execute


CONSOLIDATION_VERSION = "M33-v1"

MAX_SOURCE_MEMORIES = 240
MAX_CANDIDATES = 4
MAX_EVIDENCE = 5

STRUCTURED_MIN_CLUSTER_SIZE = 2
UNSTRUCTURED_MIN_CLUSTER_SIZE = 3
UNSTRUCTURED_SIMILARITY_THRESHOLD = 0.82

_ALLOWED_CATEGORIES = {
    "preferences",
    "relationships",
    "routines",
    "goals",
    "constraints",
    "other",
}

_EXCLUDED_CATEGORIES = {
    "identity",
    "important_dates",
}

_USER_AUTHORED_PRIORITIES = {
    "explicit_user_statement",
    "user_answer_in_context",
    "user_correction",
}

_USER_AUTHORED_SOURCES = {
    "manual",
    "user",
}

_SENSITIVE_TERMS = {
    "diagnosis",
    "diagnosed",
    "medication",
    "medicine",
    "prescription",
    "insulin",
    "therapy",
    "terapi",
    "obat",
    "religion",
    "religious",
    "muslim",
    "christian",
    "hindu",
    "buddhist",
    "islam",
    "church",
    "mosque",
    "masjid",
    "quran",
    "bible",
    "politics",
    "political",
    "party",
    "partai",
    "election",
    "pemilu",
    "vote",
    "sexual",
    "sex",
    "porn",
    "alcohol",
    "beer",
    "wine",
    "whisky",
    "whiskey",
    "rokok",
    "cigarette",
    "smoking",
    "vape",
    "marijuana",
    "thc",
}

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "for", "from", "has", "is",
    "it", "of", "on", "or", "that", "the", "to", "user", "with",
    "aku", "dan", "di", "dengan", "dari", "ini", "itu", "ke", "saya", "yang",
}


@dataclass(frozen=True)
class ConsolidatedMemoryCandidate:
    """Evidence-merge proposal targeting one existing canonical memory."""

    content: str
    kind: str
    category: str
    structured_field: str | None
    structured_value: str | None
    confidence: float
    evidence: list[str]
    target_memory_ref: str = ""
    source_memory_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _fold(value: Any) -> str:
    return _compact(value).casefold()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_hidden(row: dict[str, Any]) -> bool:
    status = _fold(row.get("status"))
    return bool(
        row.get("archived")
        or row.get("superseded")
        or row.get("deleted_at")
        or status in {"archived", "superseded", "deleted"}
    )


def _is_sensitive(text: str) -> bool:
    words = set(
        re.findall(
            r"[a-z0-9\u00c0-\u024f]+",
            text.casefold(),
        )
    )
    return bool(words & _SENSITIVE_TERMS)


def _eligible_source(row: dict[str, Any]) -> bool:
    if not row or not _compact(row.get("content")):
        return False

    if _is_hidden(row):
        return False

    assessment = assess_memory_lifecycle(row)
    if assessment.hidden or assessment.needs_confirmation:
        return False

    category = _fold(row.get("category")) or "other"
    if category in _EXCLUDED_CATEGORIES:
        return False
    if category not in _ALLOWED_CATEGORIES:
        return False

    source_priority = _fold(row.get("source_priority"))
    source = _fold(row.get("source"))

    user_authored = (
        source_priority in _USER_AUTHORED_PRIORITIES
        or source in _USER_AUTHORED_SOURCES
    )
    if not user_authored:
        return False

    haystack = " ".join(
        part
        for part in (
            _compact(row.get("content")),
            _compact(row.get("structured_value")),
        )
        if part
    )
    if _is_sensitive(haystack):
        return False

    structured_field = _fold(row.get("structured_field"))
    if structured_field.startswith("consolidated_pattern_"):
        return False

    return True


def _normalized_value(value: Any) -> str:
    text = _fold(value)
    text = re.sub(
        r"[^a-z0-9\u00c0-\u024f]+",
        " ",
        text,
    )
    return " ".join(text.split())


def _tokens(value: Any) -> frozenset[str]:
    text = _normalized_value(value)
    return frozenset(
        token
        for token in text.split()
        if token not in _STOPWORDS
        and len(token) >= 2
    )


def _similarity(left: Any, right: Any) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)

    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return 0.0

    union = len(left_tokens | right_tokens)
    if union == 0:
        return 0.0

    return len(left_tokens & right_tokens) / union


def _provenance_rank(row: dict[str, Any]) -> int:
    priority = _fold(row.get("source_priority"))

    if priority == "user_correction":
        return 5
    if priority == "explicit_user_statement":
        return 4
    if priority == "user_answer_in_context":
        return 3

    source = _fold(row.get("source"))
    if source in _USER_AUTHORED_SOURCES:
        return 2

    return 1


def _representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            _provenance_rank(row),
            _safe_float(row.get("confidence")),
            _compact(row.get("updated_at")),
            _compact(row.get("created_at")),
            _compact(row.get("id")),
        )

    return max(rows, key=key)


def _evidence(rows: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    for row in rows:
        text = _compact(row.get("content"))[:180]
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
        if len(values) >= MAX_EVIDENCE:
            break

    return values


def _candidate_from_cluster(
    rows: list[dict[str, Any]],
    *,
    reason_code: str,
) -> ConsolidatedMemoryCandidate | None:
    if not rows:
        return None

    representative = _representative(rows)
    target_ref = _compact(representative.get("id"))
    if not target_ref:
        return None

    source_refs = tuple(
        ref
        for ref in (
            _compact(row.get("id"))
            for row in rows
        )
        if ref
    )

    return ConsolidatedMemoryCandidate(
        content=_compact(representative.get("content")),
        kind=_compact(representative.get("kind")) or "context",
        category=_fold(representative.get("category")) or "other",
        structured_field=(
            _compact(representative.get("structured_field"))
            or None
        ),
        structured_value=(
            _compact(representative.get("structured_value"))
            or None
        ),
        confidence=_safe_float(
            representative.get("confidence"),
            0.0,
        ),
        evidence=_evidence(rows),
        target_memory_ref=target_ref,
        source_memory_refs=source_refs,
        reason_codes=(reason_code,),
    )


def _structured_clusters(
    rows: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    groups: dict[
        tuple[str, str, str],
        list[dict[str, Any]],
    ] = {}

    for row in rows:
        field = _normalized_value(
            row.get("structured_field")
        )
        value = _normalized_value(
            row.get("structured_value")
        )
        category = _fold(row.get("category")) or "other"

        if not field or not value:
            continue

        key = (category, field, value)
        groups.setdefault(key, []).append(row)

    return [
        group
        for group in groups.values()
        if len(group) >= STRUCTURED_MIN_CLUSTER_SIZE
    ]


def _unstructured_clusters(
    rows: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    candidates = [
        row
        for row in rows
        if not _compact(row.get("structured_field"))
        and not _compact(row.get("structured_value"))
    ]

    clusters: list[list[dict[str, Any]]] = []
    used: set[str] = set()

    ordered = sorted(
        candidates,
        key=lambda row: (
            _fold(row.get("category")),
            _compact(row.get("id")),
        ),
    )

    for row in ordered:
        row_ref = _compact(row.get("id"))
        if not row_ref or row_ref in used:
            continue

        category = _fold(row.get("category")) or "other"
        cluster = [row]

        for other in ordered:
            other_ref = _compact(other.get("id"))
            if (
                not other_ref
                or other_ref == row_ref
                or other_ref in used
                or _fold(other.get("category")) != category
            ):
                continue

            if (
                _similarity(
                    row.get("content"),
                    other.get("content"),
                )
                >= UNSTRUCTURED_SIMILARITY_THRESHOLD
            ):
                cluster.append(other)

        if len(cluster) < UNSTRUCTURED_MIN_CLUSTER_SIZE:
            continue

        for item in cluster:
            ref = _compact(item.get("id"))
            if ref:
                used.add(ref)

        clusters.append(cluster)

    return clusters


def build_consolidation_candidates(
    rows: list[dict[str, Any]],
    *,
    days: int = 30,
) -> list[ConsolidatedMemoryCandidate]:
    """Build deterministic evidence-merge candidates from trusted memory rows."""

    del days

    eligible = [
        row
        for row in rows
        if isinstance(row, dict)
        and _eligible_source(row)
    ]

    if len(eligible) < STRUCTURED_MIN_CLUSTER_SIZE:
        return []

    candidates: list[ConsolidatedMemoryCandidate] = []
    seen_targets: set[str] = set()

    for cluster in _structured_clusters(eligible):
        candidate = _candidate_from_cluster(
            cluster,
            reason_code=(
                "consolidation.cluster.structured_repeat"
            ),
        )
        if (
            candidate is not None
            and candidate.target_memory_ref
            not in seen_targets
        ):
            seen_targets.add(candidate.target_memory_ref)
            candidates.append(candidate)

    for cluster in _unstructured_clusters(eligible):
        candidate = _candidate_from_cluster(
            cluster,
            reason_code=(
                "consolidation.cluster.near_duplicate"
            ),
        )
        if (
            candidate is not None
            and candidate.target_memory_ref
            not in seen_targets
        ):
            seen_targets.add(candidate.target_memory_ref)
            candidates.append(candidate)

    return candidates[:MAX_CANDIDATES]


def _merge_evidence(
    existing: Any,
    incoming: list[str],
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    existing_values = (
        existing
        if isinstance(existing, list)
        else []
    )

    for raw in [
        *existing_values,
        *incoming,
    ]:
        text = _compact(raw)[:180]
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
        if len(values) >= MAX_EVIDENCE:
            break

    return values


async def fetch_recent_active_memories(
    *,
    user_id: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=max(1, days))
    ).isoformat()

    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id,content,kind,category,structured_field,"
                "structured_value,confidence,source,source_priority,"
                "source_conversation_id,evidence,archived,superseded,"
                "status,deleted_at,last_confirmed_at,created_at,updated_at"
            )
            .eq("user_id", user_id)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(MAX_SOURCE_MEMORIES)
            .execute()
        )
    )

    return list(
        getattr(result, "data", None)
        or []
    )


async def _load_target_row(
    *,
    user_id: str,
    memory_id: str,
) -> dict[str, Any] | None:
    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id,content,kind,category,structured_field,"
                "structured_value,confidence,source,source_priority,"
                "evidence,archived,superseded,status,deleted_at,"
                "last_confirmed_at,created_at,updated_at"
            )
            .eq("user_id", user_id)
            .eq("id", memory_id)
            .limit(1)
            .execute()
        )
    )

    rows = list(
        getattr(result, "data", None)
        or []
    )
    return rows[0] if rows else None


async def _update_target_evidence(
    *,
    user_id: str,
    memory_id: str,
    evidence: list[str],
) -> None:
    await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .update(
                {
                    "evidence": evidence,
                }
            )
            .eq("user_id", user_id)
            .eq("id", memory_id)
            .execute()
        )
    )


async def merge_candidate_evidence(
    *,
    user_id: str,
    candidate: ConsolidatedMemoryCandidate,
) -> dict[str, Any]:
    target = await _load_target_row(
        user_id=user_id,
        memory_id=candidate.target_memory_ref,
    )

    if target is None or not _eligible_source(target):
        return {
            "action": "target_unavailable",
            "memory_id": candidate.target_memory_ref,
            "reason_code": (
                "consolidation.persistence.target_unavailable"
            ),
        }

    merged = _merge_evidence(
        target.get("evidence"),
        candidate.evidence,
    )
    existing = _merge_evidence(
        target.get("evidence"),
        [],
    )

    if merged == existing:
        return {
            "action": "unchanged",
            "memory_id": candidate.target_memory_ref,
            "reason_code": (
                "consolidation.persistence.unchanged"
            ),
        }

    await _update_target_evidence(
        user_id=user_id,
        memory_id=candidate.target_memory_ref,
        evidence=merged,
    )

    return {
        "action": "evidence_merged",
        "memory_id": candidate.target_memory_ref,
        "evidence_count": len(merged),
        "source_memory_refs": list(
            candidate.source_memory_refs
        ),
        "reason_code": (
            "consolidation.persistence.evidence_merged"
        ),
    }


async def consolidate_and_persist(
    *,
    user_id: str,
    days: int = 30,
) -> dict[str, Any]:
    """Run one fail-open M33 evidence-consolidation cycle for a user."""

    try:
        rows = await fetch_recent_active_memories(
            user_id=user_id,
            days=days,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "version": CONSOLIDATION_VERSION,
            "saved": 0,
            "confirmed": 0,
            "merged": 0,
            "unchanged": 0,
            "failed": 1,
            "candidates": 0,
            "source_memories": 0,
            "reason": "source_unavailable",
            "error_type": type(exc).__name__,
        }

    candidates = build_consolidation_candidates(
        rows,
        days=days,
    )

    if not candidates:
        return {
            "ok": True,
            "version": CONSOLIDATION_VERSION,
            "saved": 0,
            "confirmed": 0,
            "merged": 0,
            "unchanged": 0,
            "failed": 0,
            "candidates": 0,
            "source_memories": len(rows),
            "reason": "no_stable_pattern",
            "actions": [],
        }

    merged = 0
    unchanged = 0
    failed = 0
    actions: list[dict[str, Any]] = []

    for candidate in candidates[:MAX_CANDIDATES]:
        try:
            result = await merge_candidate_evidence(
                user_id=user_id,
                candidate=candidate,
            )
        except Exception as exc:  # noqa: BLE001
            result = {
                "action": "failed",
                "memory_id": candidate.target_memory_ref,
                "reason_code": (
                    "consolidation.persistence.failed"
                ),
                "error_type": type(exc).__name__,
            }

        actions.append(result)

        if result.get("action") == "evidence_merged":
            merged += 1
        elif result.get("action") == "unchanged":
            unchanged += 1
        else:
            failed += 1

    return {
        "ok": failed == 0,
        "version": CONSOLIDATION_VERSION,
        "saved": 0,
        "confirmed": 0,
        "merged": merged,
        "unchanged": unchanged,
        "failed": failed,
        "candidates": len(candidates),
        "source_memories": len(rows),
        "actions": actions,
    }
