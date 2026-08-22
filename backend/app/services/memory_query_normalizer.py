"""Controlled query normalization for memory retrieval.

This module is intentionally conservative:
- public/current queries should already be blocked by memory_retrieval_gate;
- normalization only enriches clearly personal memory queries;
- the original user wording is always preserved at the front of the retrieval query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedMemoryQuery:
    original: str
    query: str
    applied: bool
    reason: str


_SELF_REGULATION_HINTS = (
    "self regulation",
    "overthinking",
    "rest reminder",
    "remind me to rest",
    "gentle reminder",
    "without pressure",
    "calm nudge",
    "emotional pattern",
)

_SELF_REGULATION_TERMS = (
    "overthinking",
    "kepikiran",
    "marah",
    "cemas",
    "anxious",
    "insecure",
    "burnout",
    "stress",
    "stressed",
    "galau",
    "bad mood",
    "overwhelmed",
    "spiral",
    "panik",
    "panic",
)

_ALREADY_RICH_TERMS = (
    "ingat",
    "ingatkan",
    "remind",
    "reminder",
    "istirahat",
    "rest",
    "preference",
    "preferensi",
)


def _compact(text: str | None) -> str:
    return " ".join((text or "").split())


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(term.casefold() in folded for term in terms)


def _append_missing(original: str, hints: tuple[str, ...]) -> str:
    folded = original.casefold()
    missing = [hint for hint in hints if hint.casefold() not in folded]
    if not missing:
        return original
    return original + " | memory retrieval hints: " + "; ".join(missing)


def normalize_memory_query(
    query_text: str | None,
    *,
    gate_decision: Any | None = None,
) -> NormalizedMemoryQuery:
    """Return the query string that should be embedded for memory retrieval."""
    original = _compact(query_text)
    if not original:
        return NormalizedMemoryQuery(original="", query="", applied=False, reason="empty")

    should_retrieve = getattr(gate_decision, "should_retrieve", True)
    if should_retrieve is False:
        return NormalizedMemoryQuery(
            original=original,
            query=original,
            applied=False,
            reason="gate_blocked",
        )

    reason = str(getattr(gate_decision, "reason", "") or "")

    is_self_regulation = (
        reason == "personal_cue:self_regulation"
        or _contains_any(original, _SELF_REGULATION_TERMS)
    )

    # Only enrich sparse self-regulation queries. Rich reminder/rest/preference
    # wording already retrieves well and does not need extra terms.
    if is_self_regulation and not _contains_any(original, _ALREADY_RICH_TERMS):
        return NormalizedMemoryQuery(
            original=original,
            query=_append_missing(original, _SELF_REGULATION_HINTS),
            applied=True,
            reason="self_regulation_sparse_query",
        )

    return NormalizedMemoryQuery(
        original=original,
        query=original,
        applied=False,
        reason="no_change",
    )
