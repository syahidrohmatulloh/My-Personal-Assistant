"""M31F — deterministic metacognitive policy.

M31F turns already-produced cognitive state into deterministic epistemic and
clarification policy. The LLM may render the response, but it does not decide
whether Aliyya should proceed, answer cautiously, or clarify.

Boundaries:
- deterministic and side-effect free;
- consumes WorkingMemoryState plus already-retrieved memory metadata;
- reuses memory lifecycle governance instead of inventing a new trust score;
- never computes salience or relevance;
- never collapses confidence/salience/relevance into one scalar;
- never calls an LLM, database, embedder, or external service;
- never writes durable state;
- never copies raw memory content into the decision or trace.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any, Literal

from app.services import memory_lifecycle_governance
from app.services import working_memory


METACOGNITIVE_POLICY_VERSION = "M31F-v1"
REPHRASE_CLARIFICATION_THRESHOLD = 2

ResponsePosture = Literal[
    "proceed",
    "caution",
    "clarify",
]

EvidenceTrust = Literal[
    "not_applicable",
    "trusted",
    "mixed",
    "unverified",
    "unavailable",
]

DurableProjectionPosture = Literal[
    "eligible",
    "hold_for_confirmation",
]


METACOGNITIVE_REASON_CODES = frozenset(
    {
        "metacognition.evidence.not_applicable",
        "metacognition.evidence.trusted",
        "metacognition.evidence.mixed",
        "metacognition.evidence.unverified",
        "metacognition.evidence.unavailable",
        "metacognition.retrieval.degraded",
        "metacognition.retrieval.failed",
        "metacognition.response.proceed",
        "metacognition.response.caution",
        "metacognition.response.clarify.ambiguity",
        "metacognition.response.clarify.contradiction",
        "metacognition.response.clarify.repeated_rephrase",
        "metacognition.response.clarify.personal_context_unavailable",
        "metacognition.projection.eligible",
        "metacognition.projection.hold_for_confirmation",
        "metacognition.background_inference.allowed",
        "metacognition.background_inference.held",
        "metacognition.rephrase.detected",
        "metacognition.fallback.safe_default",
    }
)


_REPHRASE_CUES = (
    "maksud saya",
    "maksudku",
    "maksud gue",
    "bukan itu",
    "bukan begitu",
    "bukan gitu",
    "salah tangkap",
    "salah paham",
    "kamu salah",
    "kok bukan",
    "i mean",
    "what i meant",
    "not what i meant",
    "that's not what i meant",
    "that is not what i meant",
    "no, i meant",
    "not that",
    "you misunderstood",
)

_SHORT_REFERENTS = {
    "itu",
    "ini",
    "dia",
    "mereka",
    "yang itu",
    "yang ini",
    "yang tadi",
    "yang barusan",
    "yang mana",
    "that",
    "this",
    "it",
    "that one",
    "this one",
    "the one",
}


@dataclass(frozen=True)
class MetacognitiveSignals:
    ambiguity_detected: bool = False
    contradiction_detected: bool = False
    repeated_rephrase_count: int = 0
    personal_context_required: bool = False


@dataclass(frozen=True)
class MetacognitiveDecision:
    version: str
    response_posture: ResponsePosture
    evidence_trust: EvidenceTrust
    durable_projection_posture: DurableProjectionPosture
    allow_background_inference: bool
    reason_codes: tuple[str, ...]
    unverified_memory_refs: tuple[str, ...] = ()


def _norm(value: Any) -> str:
    text = " ".join(str(value or "").strip().lower().split())
    return re.sub(r"[?!.,;:]+$", "", text).strip()


def _memory_ref(row: Mapping[str, Any]) -> str | None:
    value = row.get("id") or row.get("memory_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _append_reason(reasons: list[str], code: str) -> None:
    if code not in METACOGNITIVE_REASON_CODES:
        raise ValueError(f"Unknown metacognitive reason code: {code}")
    if code not in reasons:
        reasons.append(code)


def _selected_memory_rows(
    *,
    working_state: working_memory.WorkingMemoryState,
    legacy_memories: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    selected_refs = set(working_state.memory.selected_memory_refs)
    if not selected_refs:
        return ()

    rows: list[dict[str, Any]] = []
    for raw in legacy_memories:
        ref = _memory_ref(raw)
        if ref and ref in selected_refs:
            rows.append(dict(raw))
    return tuple(rows)


def _assess_evidence(
    rows: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
) -> tuple[EvidenceTrust, tuple[str, ...]]:
    if not rows:
        return ("not_applicable", ())

    trusted_count = 0
    unverified_refs: list[str] = []

    for raw in rows:
        row = dict(raw)
        assessment = memory_lifecycle_governance.assess_memory_lifecycle(
            row,
            now=now,
        )

        if assessment.hidden or assessment.needs_confirmation:
            ref = _memory_ref(row)
            if ref and ref not in unverified_refs:
                unverified_refs.append(ref)
        else:
            trusted_count += 1

    if unverified_refs and trusted_count:
        trust: EvidenceTrust = "mixed"
    elif unverified_refs:
        trust = "unverified"
    else:
        trust = "trusted"

    return (trust, tuple(unverified_refs))


def _structured_contradiction_detected(
    rows: Sequence[Mapping[str, Any]],
) -> bool:
    by_field: dict[str, set[str]] = {}

    for row in rows:
        field = _norm(row.get("structured_field"))
        value = _norm(row.get("structured_value"))

        if not field or not value:
            continue

        by_field.setdefault(field, set()).add(value)

    return any(len(values) > 1 for values in by_field.values())


def _is_rephrase_message(value: Any) -> bool:
    text = _norm(value)
    return bool(text) and any(cue in text for cue in _REPHRASE_CUES)


def _recent_user_texts(
    recent_messages: Sequence[Mapping[str, Any]],
    *,
    current_user_message: str,
) -> tuple[str, ...]:
    texts: list[str] = []

    for row in recent_messages:
        if str(row.get("role") or "").lower() != "user":
            continue

        content = row.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content)

    if not texts or _norm(texts[-1]) != _norm(current_user_message):
        texts.append(current_user_message)

    return tuple(texts[-6:])


def _rephrase_count(
    recent_messages: Sequence[Mapping[str, Any]],
    *,
    current_user_message: str,
) -> int:
    texts = _recent_user_texts(
        recent_messages,
        current_user_message=current_user_message,
    )

    if not texts or not _is_rephrase_message(texts[-1]):
        return 0

    return sum(1 for text in texts if _is_rephrase_message(text))


def _looks_ambiguous_without_history(
    user_message: str,
    *,
    history_message_count: int,
) -> bool:
    if history_message_count > 1:
        return False

    text = _norm(user_message)
    return text in _SHORT_REFERENTS


def _personal_context_required(
    state: working_memory.WorkingMemoryState,
) -> bool:
    if state.memory.packing_intent in {"identity", "self_regulation"}:
        return True

    reason = str(state.memory.retrieval_gate_reason or "")
    return reason.startswith("personal_cue:")


def derive_metacognitive_signals(
    *,
    working_state: working_memory.WorkingMemoryState,
    legacy_memories: Sequence[Mapping[str, Any]] = (),
    user_message: str,
    recent_messages: Sequence[Mapping[str, Any]] = (),
) -> tuple[MetacognitiveSignals, tuple[dict[str, Any], ...]]:
    """Derive conservative deterministic signals from existing turn state."""

    working_memory.validate_working_memory_state(working_state)

    selected_rows = _selected_memory_rows(
        working_state=working_state,
        legacy_memories=legacy_memories,
    )

    signals = MetacognitiveSignals(
        ambiguity_detected=_looks_ambiguous_without_history(
            user_message,
            history_message_count=working_state.history.message_count,
        ),
        contradiction_detected=_structured_contradiction_detected(
            selected_rows
        ),
        repeated_rephrase_count=_rephrase_count(
            recent_messages,
            current_user_message=user_message,
        ),
        personal_context_required=_personal_context_required(
            working_state
        ),
    )

    return (signals, selected_rows)


def safe_default_decision() -> MetacognitiveDecision:
    """Behavior-preserving fail-open fallback."""

    return MetacognitiveDecision(
        version=METACOGNITIVE_POLICY_VERSION,
        response_posture="proceed",
        evidence_trust="not_applicable",
        durable_projection_posture="eligible",
        allow_background_inference=True,
        reason_codes=(
            "metacognition.fallback.safe_default",
            "metacognition.response.proceed",
            "metacognition.projection.eligible",
            "metacognition.background_inference.allowed",
        ),
        unverified_memory_refs=(),
    )


def evaluate_metacognitive_policy(
    *,
    working_state: working_memory.WorkingMemoryState,
    legacy_memories: Sequence[Mapping[str, Any]] = (),
    user_message: str,
    recent_messages: Sequence[Mapping[str, Any]] = (),
    now: datetime | None = None,
) -> MetacognitiveDecision:
    """Return the deterministic M31F policy decision for one turn."""

    signals, selected_rows = derive_metacognitive_signals(
        working_state=working_state,
        legacy_memories=legacy_memories,
        user_message=user_message,
        recent_messages=recent_messages,
    )

    evidence_trust, unverified_refs = _assess_evidence(
        selected_rows,
        now=_normalize_now(now),
    )

    reasons: list[str] = []
    _append_reason(
        reasons,
        f"metacognition.evidence.{evidence_trust}",
    )

    retrieval_status = working_state.memory.retrieval_status

    if retrieval_status == "degraded":
        _append_reason(
            reasons,
            "metacognition.retrieval.degraded",
        )

    if retrieval_status == "failed":
        _append_reason(
            reasons,
            "metacognition.retrieval.failed",
        )

    if (
        signals.personal_context_required
        and not selected_rows
        and retrieval_status in {"degraded", "failed"}
    ):
        evidence_trust = "unavailable"
        reasons = [
            code
            for code in reasons
            if not code.startswith("metacognition.evidence.")
        ]
        _append_reason(
            reasons,
            "metacognition.evidence.unavailable",
        )

    if signals.repeated_rephrase_count > 0:
        _append_reason(
            reasons,
            "metacognition.rephrase.detected",
        )

    clarification_reason: str | None = None

    if signals.ambiguity_detected:
        clarification_reason = (
            "metacognition.response.clarify.ambiguity"
        )
    elif signals.contradiction_detected:
        clarification_reason = (
            "metacognition.response.clarify.contradiction"
        )
    elif (
        signals.repeated_rephrase_count
        >= REPHRASE_CLARIFICATION_THRESHOLD
    ):
        clarification_reason = (
            "metacognition.response.clarify.repeated_rephrase"
        )
    elif (
        signals.personal_context_required
        and evidence_trust in {"unverified", "unavailable"}
        and retrieval_status != "degraded"
    ):
        clarification_reason = (
            "metacognition.response."
            "clarify.personal_context_unavailable"
        )

    if clarification_reason:
        response_posture: ResponsePosture = "clarify"
        _append_reason(reasons, clarification_reason)
    elif (
        evidence_trust in {"mixed", "unverified", "unavailable"}
        or retrieval_status in {"degraded", "failed"}
        or signals.repeated_rephrase_count == 1
    ):
        response_posture = "caution"
        _append_reason(
            reasons,
            "metacognition.response.caution",
        )
    else:
        response_posture = "proceed"
        _append_reason(
            reasons,
            "metacognition.response.proceed",
        )

    hold_projection = bool(
        response_posture == "clarify"
        or evidence_trust in {"mixed", "unverified", "unavailable"}
        or signals.repeated_rephrase_count > 0
    )

    projection_posture: DurableProjectionPosture = (
        "hold_for_confirmation"
        if hold_projection
        else "eligible"
    )

    allow_background_inference = not hold_projection

    _append_reason(
        reasons,
        "metacognition.projection." + projection_posture,
    )
    _append_reason(
        reasons,
        (
            "metacognition.background_inference.allowed"
            if allow_background_inference
            else "metacognition.background_inference.held"
        ),
    )

    return MetacognitiveDecision(
        version=METACOGNITIVE_POLICY_VERSION,
        response_posture=response_posture,
        evidence_trust=evidence_trust,
        durable_projection_posture=projection_posture,
        allow_background_inference=allow_background_inference,
        reason_codes=tuple(reasons),
        unverified_memory_refs=unverified_refs,
    )


def render_prompt_directive(
    decision: MetacognitiveDecision,
) -> str | None:
    """Render a high-priority epistemic directive for Claude.

    The directive controls response posture only. It does not expose internal
    memory identifiers or implementation details.
    """

    if decision.response_posture == "proceed":
        return None

    if decision.response_posture == "caution":
        return (
            "## M31F metacognitive response policy — CAUTION\n"
            "This is a deterministic runtime instruction.\n"
            "- You may answer, but do not present uncertain personal context "
            "as established fact.\n"
            "- Qualify memory-based claims when evidence is tentative, stale, "
            "mixed, degraded, or unavailable.\n"
            "- Prefer the user's current explicit statement over inferred or "
            "older context.\n"
            "- If the answer materially depends on a personal fact that is not "
            "reliable enough, ask the user to confirm that fact.\n"
            "- Do not mention internal memory scores, reason codes, or policy "
            "machinery."
        )

    return (
        "## M31F metacognitive response policy — CLARIFY\n"
        "This is a deterministic runtime instruction and overrides ordinary "
        "helpfulness pressure to guess.\n"
        "- Ask ONE concise clarification question before giving a substantive "
        "answer that depends on the unresolved point.\n"
        "- Do not guess missing referents, contradictory personal facts, or "
        "unavailable personal context.\n"
        "- Do not present an inferred personal detail as established fact.\n"
        "- Keep the clarification natural and specific to the conversation.\n"
        "- Do not mention internal memory scores, reason codes, or policy "
        "machinery."
    )


def decision_has_separate_score_axes() -> bool:
    """Architecture guard used by tests."""

    names = {item.name for item in fields(MetacognitiveDecision)}
    forbidden = {
        "confidence",
        "confidence_score",
        "salience",
        "salience_score",
        "relevance",
        "relevance_score",
    }
    return names.isdisjoint(forbidden)
