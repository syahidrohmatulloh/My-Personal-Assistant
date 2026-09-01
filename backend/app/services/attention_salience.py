"""M31G — deterministic intrinsic memory salience and attention overlay.

Canonical boundaries from the M31 ADR:
- memory salience is intrinsic importance to the user's life;
- salience is independent of the current query;
- confidence, salience, and relevance remain separate axes;
- existing retrieval/packing decides query relevance before M31G runs;
- M31G scores only memories already selected for the prompt;
- metacognitive trust/clarification policy may suppress attention emphasis
  without changing the underlying salience score;
- no LLM, database, embedding, network, or durable write occurs here.

M31G therefore does not replace retrieval ranking or memory packing. It adds a
deterministic attention overlay to the already-selected memory set.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.services import working_memory


ATTENTION_SALIENCE_VERSION = "M31G-v1"
MAX_ATTENDED_MEMORIES = 2

AttentionLevel = Literal[
    "normal",
    "elevated",
    "high",
]

SalienceTier = Literal[
    "low",
    "medium",
    "high",
]


ATTENTION_REASON_CODES = frozenset(
    {
        "attention.salience.level.normal",
        "attention.salience.level.elevated",
        "attention.salience.level.high",
        "attention.salience.category.critical",
        "attention.salience.category.core",
        "attention.salience.category.durable",
        "attention.salience.category.context",
        "attention.salience.structured.core_field",
        "attention.salience.structured.other_field",
        "attention.salience.tier.low",
        "attention.salience.tier.medium",
        "attention.salience.tier.high",
        "attention.focus.selected",
        "attention.focus.suppressed_unverified",
        "attention.focus.suppressed_clarify",
        "attention.salience.fallback.safe_default",
    }
)


_CATEGORY_BASE = {
    "important_dates": 0.78,
    "constraints": 0.74,
    "identity": 0.66,
    "relationships": 0.66,
    "goals": 0.60,
    "projects": 0.54,
    "routines": 0.50,
    "preferences": 0.48,
    "context": 0.32,
}

_CRITICAL_CATEGORIES = {
    "important_dates",
    "constraints",
}

_CORE_CATEGORIES = {
    "identity",
    "relationships",
}

_DURABLE_CATEGORIES = {
    "goals",
    "projects",
    "routines",
    "preferences",
}

_CORE_STRUCTURED_FIELDS = {
    "birthday",
    "birthdate",
    "timezone",
    "preferred_name",
    "nickname",
    "assistant_name",
    "daughter_name",
    "child_name",
    "spouse_name",
    "location",
}


@dataclass(frozen=True)
class CandidateSalience:
    memory_ref: str
    score: float
    tier: SalienceTier
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class AttentionDecision:
    version: str
    level: AttentionLevel
    candidates: tuple[CandidateSalience, ...]
    salient_memory_refs: tuple[str, ...]
    attended_memory_refs: tuple[str, ...]
    suppressed_memory_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fold(value: Any) -> str:
    return _text(value).casefold()


def _memory_ref(row: Mapping[str, Any]) -> str | None:
    value = row.get("id") or row.get("memory_id")
    text = _text(value)
    return text or None


def _append_reason(reasons: list[str], code: str) -> None:
    if code not in ATTENTION_REASON_CODES:
        raise ValueError(f"Unknown M31G attention reason code: {code}")
    if code not in reasons:
        reasons.append(code)



def _category_reason(category: str) -> str:
    if category in _CRITICAL_CATEGORIES:
        return "attention.salience.category.critical"
    if category in _CORE_CATEGORIES:
        return "attention.salience.category.core"
    if category in _DURABLE_CATEGORIES:
        return "attention.salience.category.durable"
    return "attention.salience.category.context"


def _tier(score: float) -> SalienceTier:
    if score >= 0.70:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def _score_row(row: Mapping[str, Any]) -> tuple[float, SalienceTier, tuple[str, ...]]:
    """Compute intrinsic salience without consulting query/retrieval axes."""

    category = _fold(row.get("category"))
    structured_field = _fold(row.get("structured_field"))

    score = _CATEGORY_BASE.get(category, 0.40)
    reasons: list[str] = []

    _append_reason(
        reasons,
        _category_reason(category),
    )

    if structured_field:
        if structured_field in _CORE_STRUCTURED_FIELDS:
            score += 0.12
            _append_reason(
                reasons,
                "attention.salience.structured.core_field",
            )
        else:
            score += 0.04
            _append_reason(
                reasons,
                "attention.salience.structured.other_field",
            )

    # Canonical M31G salience intentionally ignores the legacy
    # ``row["salience"]`` retrieval hint. That implementation field belongs
    # to memory.py ranking and must not be relabeled as intrinsic salience.

    score = round(
        max(0.0, min(1.0, score)),
        3,
    )

    tier = _tier(score)

    _append_reason(
        reasons,
        f"attention.salience.tier.{tier}",
    )

    return (
        score,
        tier,
        tuple(reasons),
    )


def _selected_rows(
    *,
    state: working_memory.WorkingMemoryState,
    legacy_memories: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, dict[str, Any]], ...]:
    selected_order = {
        memory_ref: index
        for index, memory_ref in enumerate(
            state.memory.selected_memory_refs
        )
    }

    if not selected_order:
        return ()

    seen: set[str] = set()
    rows: list[tuple[int, dict[str, Any]]] = []

    for raw in legacy_memories:
        ref = _memory_ref(raw)
        if (
            not ref
            or ref not in selected_order
            or ref in seen
        ):
            continue

        rows.append(
            (
                selected_order[ref],
                dict(raw),
            )
        )
        seen.add(ref)

    rows.sort(
        key=lambda item: item[0]
    )

    return tuple(rows)


def safe_default_decision() -> AttentionDecision:
    """Behavior-preserving fail-open decision: no salience emphasis."""

    return AttentionDecision(
        version=ATTENTION_SALIENCE_VERSION,
        level="normal",
        candidates=(),
        salient_memory_refs=(),
        attended_memory_refs=(),
        suppressed_memory_refs=(),
        reason_codes=(
            "attention.salience.fallback.safe_default",
            "attention.salience.level.normal",
        ),
    )


def evaluate_attention_salience(
    *,
    working_state: working_memory.WorkingMemoryState,
    legacy_memories: Sequence[Mapping[str, Any]] = (),
    unverified_memory_refs: Sequence[str] = (),
    response_posture: str = "proceed",
) -> AttentionDecision:
    """Score intrinsic salience and choose which selected memories get emphasis.

    No current user query is accepted by this API. Query relevance has already
    been resolved by retrieval + packing before this service runs.
    """

    working_memory.validate_working_memory_state(
        working_state
    )

    rows = _selected_rows(
        state=working_state,
        legacy_memories=legacy_memories,
    )

    candidates_with_order: list[
        tuple[int, CandidateSalience]
    ] = []

    for order, row in rows:
        ref = _memory_ref(row)
        if not ref:
            continue

        score, tier, reasons = _score_row(row)

        candidates_with_order.append(
            (
                order,
                CandidateSalience(
                    memory_ref=ref,
                    score=score,
                    tier=tier,
                    reason_codes=reasons,
                ),
            )
        )

    candidates = tuple(
        candidate
        for _order, candidate in candidates_with_order
    )

    ranked_salient = [
        (order, candidate)
        for order, candidate in candidates_with_order
        if candidate.tier in {"medium", "high"}
    ]

    ranked_salient.sort(
        key=lambda item: (
            -item[1].score,
            item[0],
        )
    )

    salient_refs = tuple(
        candidate.memory_ref
        for _order, candidate in ranked_salient
    )

    unverified = {
        _text(value)
        for value in unverified_memory_refs
        if _text(value)
    }

    reasons: list[str] = []
    suppressed: list[str] = []
    eligible: list[CandidateSalience] = []

    if response_posture == "clarify":
        suppressed.extend(salient_refs)

        if salient_refs:
            _append_reason(
                reasons,
                "attention.focus.suppressed_clarify",
            )
    else:
        for _order, candidate in ranked_salient:
            if candidate.memory_ref in unverified:
                suppressed.append(
                    candidate.memory_ref
                )
                continue

            eligible.append(
                candidate
            )

        if suppressed:
            _append_reason(
                reasons,
                "attention.focus.suppressed_unverified",
            )

    attended = tuple(
        candidate.memory_ref
        for candidate in eligible[
            :MAX_ATTENDED_MEMORIES
        ]
    )

    if attended:
        _append_reason(
            reasons,
            "attention.focus.selected",
        )

    attended_tiers = {
        candidate.tier
        for candidate in eligible[
            :MAX_ATTENDED_MEMORIES
        ]
    }

    if "high" in attended_tiers:
        level: AttentionLevel = "high"
    elif "medium" in attended_tiers:
        level = "elevated"
    else:
        level = "normal"

    _append_reason(
        reasons,
        f"attention.salience.level.{level}",
    )

    return AttentionDecision(
        version=ATTENTION_SALIENCE_VERSION,
        level=level,
        candidates=candidates,
        salient_memory_refs=salient_refs,
        attended_memory_refs=attended,
        suppressed_memory_refs=tuple(suppressed),
        reason_codes=tuple(reasons),
    )


def render_prompt_directive(
    decision: AttentionDecision,
    *,
    legacy_memories: Sequence[Mapping[str, Any]] = (),
) -> str | None:
    """Render a bounded private prompt overlay for attended memory items."""

    if not decision.attended_memory_refs:
        return None

    rows_by_ref: dict[str, Mapping[str, Any]] = {}

    for row in legacy_memories:
        ref = _memory_ref(row)
        if ref and ref not in rows_by_ref:
            rows_by_ref[ref] = row

    lines: list[str] = []

    for ref in decision.attended_memory_refs:
        row = rows_by_ref.get(ref)

        if not row:
            continue

        content = " ".join(
            _text(
                row.get("content")
            ).split()
        )

        if not content:
            continue

        if len(content) > 220:
            content = (
                content[:219].rstrip()
                + "…"
            )

        lines.append(
            f"- {content}"
        )

    if not lines:
        return None

    return (
        "## M31G attention policy\n"
        "These memories were already selected as relevant context and have "
        "higher intrinsic life importance. Give them proportionate attention "
        "when they materially help answer the current request.\n"
        + "\n".join(lines)
        + "\n"
        "- Salience is NOT confidence and is NOT query relevance.\n"
        "- Current explicit user statements and epistemic/clarification policy "
        "take precedence over remembered context.\n"
        "- Do not mention salience scores, internal memory identifiers, or "
        "this policy."
    )
