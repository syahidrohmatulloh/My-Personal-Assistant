"""M31B — read-only cognitive decision trace foundation.

This module mirrors decisions made elsewhere in the runtime.

It must never become an input to cognitive behavior in M31B.
Trace failures are non-critical and must remain fail-open.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import uuid4


TRACE_VERSION = "M31B-v1"

PreviewPolicy = Literal[
    "none",
    "redacted",
    "dev",
]

AffectDecision = Literal[
    "allowed",
    "suppressed",
    "not_applicable",
]

SubsystemStatus = Literal[
    "healthy",
    "degraded",
    "failed",
    "not_applicable",
]

ActionStatus = Literal[
    "success",
    "failed",
    "deferred",
    "skipped",
]


REASON_CODES = frozenset(
    {
        "trace.created",
        "trace.finalized",
        "trace.sink.skipped_disabled",
        "trace.sink.failed",
        "trace.preview.none",
        "trace.preview.redacted",
        "trace.preview.dev",
        "memory.retrieval.skipped.gate",
        "memory.retrieval.completed",
        "memory.retrieval.degraded",
        "memory.retrieved.semantic_match",
        "memory.retrieved.structured_field",
        "memory.retrieved.personal_cue_threshold",
        "memory.selected.packed",
        "memory.dropped.context_budget",
        "memory.dropped.inactive",
        "memory.dropped.category_limit",
        "memory.dropped.item_limit",
        "memory.dropped.low_similarity",
        "memory.dropped.low_relevance",
        "memory.dropped.conflict_unresolved",
        "memory.dropped.privacy_filter",
        "attention.intent.general",
        "attention.intent.identity",
        "attention.intent.self_regulation",
        "attention.truncated.memory_budget",
        "attention.truncated.total_budget",
        "affect.warm_comeback.allowed.safe_return",
        "affect.warm_comeback.suppressed.mode_not_partner_dynamic",
        "affect.warm_comeback.suppressed.assistant_mode_not_life_companion",
        "affect.warm_comeback.suppressed.user_distressed",
        "affect.warm_comeback.suppressed.urgent_or_crisis",
        "affect.warm_comeback.suppressed.serious_work_task",
        "affect.warm_comeback.suppressed.cooldown_active",
        "affect.warm_comeback.suppressed.insufficient_history",
        "affect.warm_comeback.suppressed.gap_below_minimum",
        "affect.warm_comeback.suppressed.gap_not_meaningful_vs_cadence",
        "policy.assistant_mode.life_companion",
        "policy.assistant_mode.chief_of_staff",
        "policy.companion_mode.professional",
        "policy.companion_mode.friendly",
        "policy.companion_mode.affectionate",
        "policy.companion_mode.partner",
        "policy.mood_realism.stable",
        "policy.mood_realism.dynamic",
        "policy.command.explicit_assistant_mode",
        "policy.fallback.safe_default",
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
        "action.detected.calendar",
        "action.detected.reminder",
        "action.detected.memory_encoding",
        "action.requires_confirmation.calendar_write",
        "action.authorized.explicit_user_request",
        "action.deferred.requires_confirmation",
        "action.executed.success",
        "action.executed.failed",
        "action.skipped.policy_gate",
        "action.background.encoding_scheduled",
        "action.background.encoding_skipped",
        "temporal.resolved.absolute",
        "temporal.resolved.relative",
        "temporal.ambiguous",
        "temporal.none",
        "perception.personal_cue.detected",
        "perception.mode_command.detected",
        "perception.calendar_candidate.detected",
        "subsystem.healthy",
        "subsystem.degraded.memory_retrieval",
        "subsystem.failed.memory_retrieval",
        "subsystem.degraded.life_model",
        "subsystem.failed.life_model",
        "subsystem.degraded.calendar",
        "subsystem.failed.calendar",
        "subsystem.degraded.temporal",
        "subsystem.failed.temporal",
        "subsystem.degraded.trace_sink",
        "subsystem.failed.llm",
        "legacy.chatpy.orchestrates_memory",
        "legacy.chatpy.assembles_context",
        "legacy.chatpy.applies_affect_policy",
        "legacy.chatpy.routes_actions",
    }
)


_M30_WARM_COMEBACK_REASON_CODES = {
    "mode_not_partner_dynamic":
        "affect.warm_comeback.suppressed.mode_not_partner_dynamic",
    "assistant_mode_not_life_companion":
        "affect.warm_comeback.suppressed.assistant_mode_not_life_companion",
    "user_distressed":
        "affect.warm_comeback.suppressed.user_distressed",
    "urgent_or_crisis":
        "affect.warm_comeback.suppressed.urgent_or_crisis",
    "serious_work_task":
        "affect.warm_comeback.suppressed.serious_work_task",
    "cooldown_active":
        "affect.warm_comeback.suppressed.cooldown_active",
    "insufficient_history":
        "affect.warm_comeback.suppressed.insufficient_history",
    "gap_below_minimum":
        "affect.warm_comeback.suppressed.gap_below_minimum",
    "gap_not_meaningful_vs_cadence":
        "affect.warm_comeback.suppressed.gap_not_meaningful_vs_cadence",
}


@dataclass
class TemporalTrace:
    resolution_type: str
    resolved_iso: str | None = None
    confidence: float | None = None
    raw_preview: str | None = None


@dataclass
class PerceptionTrace:
    route_signals: list[str] = field(default_factory=list)
    personal_cue: bool | None = None
    temporal: list[TemporalTrace] = field(default_factory=list)
    calendar_candidate_detected: bool | None = None
    mode_command_detected: bool | None = None
    latency_ms: float | None = None


@dataclass
class MemoryCandidateTrace:
    memory_ref: str
    category: str | None = None
    structured_field: str | None = None
    similarity_score: float | None = None
    retrieval_score: float | None = None
    confidence_score: float | None = None
    packing_score: float | None = None
    salience_score: float | None = None
    selected_for_prompt: bool | None = None
    reason_codes: list[str] = field(default_factory=list)
    preview: str | None = None


@dataclass
class MemoryTrace:
    retrieval_attempted: bool
    retrieval_gate_reason: str | None = None
    retrieval_strategy: str | None = None
    total_candidates: int = 0
    candidates: list[MemoryCandidateTrace] = field(default_factory=list)
    latency_ms: float | None = None
    subsystem_status: str = "healthy"


@dataclass
class AttentionTrace:
    packing_intent: str | None = None
    selected_memory_refs: list[str] = field(default_factory=list)
    selected_summary_refs: list[str] = field(default_factory=list)
    dropped_memory_count: int = 0
    dropped_summary_count: int = 0
    packed_context_chars: int | None = None
    packed_context_budget_chars: int | None = None
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class AffectRuleTrace:
    rule_id: str
    decision: str
    reason_codes: list[str] = field(default_factory=list)
    runtime_reason: str | None = None


@dataclass
class MetacognitiveTrace:
    response_posture: str
    evidence_trust: str
    durable_projection_posture: str
    allow_background_inference: bool
    unverified_memory_refs: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class ConfirmationTrace:
    action_type: str
    required: bool
    reason_codes: list[str] = field(default_factory=list)
    authorization_source: str | None = None


@dataclass
class PolicyTrace:
    assistant_mode: str | None = None
    companion_mode: str | None = None
    mood_realism: str | None = None
    affect_rules: list[AffectRuleTrace] = field(default_factory=list)
    metacognition: MetacognitiveTrace | None = None
    confirmation_requirements: list[ConfirmationTrace] = field(
        default_factory=list
    )
    policy_markers: list[str] = field(default_factory=list)


@dataclass
class ActionRecordTrace:
    action_type: str
    status: str
    reason_codes: list[str] = field(default_factory=list)
    target_ref: str | None = None


@dataclass
class ActionTrace:
    detected_intents: list[str] = field(default_factory=list)
    executed: list[ActionRecordTrace] = field(default_factory=list)
    deferred: list[ActionRecordTrace] = field(default_factory=list)
    latency_ms: float | None = None


@dataclass
class ContextSectionTrace:
    section_type: str
    char_count: int
    item_count: int | None = None
    preview: str | None = None


@dataclass
class ContextAssemblyTrace:
    total_context_chars: int | None = None
    sections: list[ContextSectionTrace] = field(default_factory=list)
    history_message_count: int | None = None
    truncation_occurred: bool | None = None
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class SubsystemHealth:
    subsystem: str
    status: str
    reason_codes: list[str] = field(default_factory=list)
    latency_ms: float | None = None


@dataclass
class CognitiveDecisionTrace:
    trace_id: str
    version: str
    timestamp_utc: datetime
    turn_ref: str | None = None
    conversation_ref: str | None = None
    user_ref: str | None = None
    perception: PerceptionTrace | None = None
    memory: MemoryTrace | None = None
    attention: AttentionTrace | None = None
    policy: PolicyTrace | None = None
    action: ActionTrace | None = None
    context: ContextAssemblyTrace | None = None
    subsystem_health: list[SubsystemHealth] = field(default_factory=list)
    legacy_markers: list[str] = field(default_factory=list)


class TraceSink(Protocol):
    def emit(
        self,
        trace: CognitiveDecisionTrace,
    ) -> None:
        ...


class NullTraceSink:
    def emit(
        self,
        trace: CognitiveDecisionTrace,
    ) -> None:
        return None


class TestTraceSink:
    __test__ = False

    def __init__(self) -> None:
        self.traces: list[CognitiveDecisionTrace] = []

    def emit(
        self,
        trace: CognitiveDecisionTrace,
    ) -> None:
        self.traces.append(trace)


class LoggingTraceSink:
    def __init__(
        self,
        *,
        enabled: bool = False,
        preview_policy: PreviewPolicy = "none",
        logger: logging.Logger | None = None,
    ) -> None:
        self.enabled = enabled
        self.preview_policy = preview_policy
        self.logger = logger or logging.getLogger(
            "app.cognitive_trace"
        )

    def emit(
        self,
        trace: CognitiveDecisionTrace,
    ) -> None:
        if not self.enabled:
            return

        payload = serialize_trace(
            trace,
            preview_policy=self.preview_policy,
            for_logging=True,
        )

        self.logger.info(
            "cognitive_trace=%s",
            json.dumps(
                payload,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )


def new_trace(
    *,
    turn_ref: str | None = None,
    conversation_ref: str | None = None,
    user_ref: str | None = None,
    now: datetime | None = None,
) -> CognitiveDecisionTrace:
    timestamp = now or datetime.now(timezone.utc)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=timezone.utc
        )

    return CognitiveDecisionTrace(
        trace_id=f"tr_{uuid4().hex}",
        version=TRACE_VERSION,
        timestamp_utc=timestamp.astimezone(
            timezone.utc
        ),
        turn_ref=turn_ref,
        conversation_ref=conversation_ref,
        user_ref=user_ref,
    )


def validate_reason_codes(
    reason_codes: list[str] | tuple[str, ...],
) -> None:
    unknown = sorted(
        {
            str(code)
            for code in reason_codes
            if str(code) not in REASON_CODES
        }
    )

    if unknown:
        raise ValueError(
            "Unknown M31B reason code(s): "
            + ", ".join(unknown)
        )


def _iter_reason_codes(
    value: Any,
):
    if is_dataclass(value):
        for item in fields(value):
            field_value = getattr(
                value,
                item.name,
            )

            if item.name in {
                "reason_codes",
                "policy_markers",
                "legacy_markers",
            }:
                if isinstance(
                    field_value,
                    (list, tuple),
                ):
                    for code in field_value:
                        yield str(code)
                continue

            yield from _iter_reason_codes(
                field_value
            )

        return

    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {
                "reason_codes",
                "policy_markers",
                "legacy_markers",
            }:
                if isinstance(
                    nested,
                    (list, tuple),
                ):
                    for code in nested:
                        yield str(code)
                continue

            yield from _iter_reason_codes(
                nested
            )

        return

    if isinstance(
        value,
        (list, tuple),
    ):
        for nested in value:
            yield from _iter_reason_codes(
                nested
            )


def validate_trace(
    trace: CognitiveDecisionTrace,
) -> None:
    if trace.version != TRACE_VERSION:
        raise ValueError(
            f"Unsupported trace version: {trace.version}"
        )

    if trace.timestamp_utc.tzinfo is None:
        raise ValueError(
            "timestamp_utc must be timezone-aware"
        )

    validate_reason_codes(
        list(
            _iter_reason_codes(trace)
        )
    )

    if trace.memory:
        if trace.memory.subsystem_status not in {
            "healthy",
            "degraded",
            "failed",
            "not_applicable",
        }:
            raise ValueError(
                "Invalid memory subsystem_status"
            )

        for candidate in trace.memory.candidates:
            if candidate.salience_score is not None:
                raise ValueError(
                    "M31B salience_score must remain None until M31G"
                )

    if trace.policy:
        if (
            trace.policy.assistant_mode is not None
            and trace.policy.assistant_mode
            not in {
                "life_companion",
                "chief_of_staff",
            }
        ):
            raise ValueError(
                "Invalid current assistant_mode"
            )

        if (
            trace.policy.companion_mode is not None
            and trace.policy.companion_mode
            not in {
                "professional",
                "friendly",
                "affectionate",
                "partner",
            }
        ):
            raise ValueError(
                "Invalid current companion_mode"
            )

        if (
            trace.policy.mood_realism is not None
            and trace.policy.mood_realism
            not in {
                "stable",
                "dynamic",
            }
        ):
            raise ValueError(
                "Invalid current mood_realism"
            )

        for affect in trace.policy.affect_rules:
            if affect.decision not in {
                "allowed",
                "suppressed",
                "not_applicable",
            }:
                raise ValueError(
                    "Invalid affect decision"
                )

        metacognition = trace.policy.metacognition

        if metacognition is not None:
            if metacognition.response_posture not in {
                "proceed",
                "caution",
                "clarify",
            }:
                raise ValueError(
                    "Invalid metacognitive response_posture"
                )

            if metacognition.evidence_trust not in {
                "not_applicable",
                "trusted",
                "mixed",
                "unverified",
                "unavailable",
            }:
                raise ValueError(
                    "Invalid metacognitive evidence_trust"
                )

            if (
                metacognition.durable_projection_posture
                not in {
                    "eligible",
                    "hold_for_confirmation",
                }
            ):
                raise ValueError(
                    "Invalid metacognitive durable_projection_posture"
                )

    for health in trace.subsystem_health:
        if health.status not in {
            "healthy",
            "degraded",
            "failed",
            "not_applicable",
        }:
            raise ValueError(
                "Invalid subsystem health status"
            )

    if trace.action:
        for record in (
            trace.action.executed
            + trace.action.deferred
        ):
            if record.status not in {
                "success",
                "failed",
                "deferred",
                "skipped",
            }:
                raise ValueError(
                    "Invalid action trace status"
                )


def build_warm_comeback_affect_trace(
    decision: dict[str, Any] | None,
) -> AffectRuleTrace:
    if not decision:
        return AffectRuleTrace(
            rule_id="warm_comeback",
            decision="not_applicable",
        )

    runtime_reason = str(
        decision.get(
            "must_suppress_reason"
        )
        or ""
    ).strip()

    if runtime_reason:
        reason_code = (
            _M30_WARM_COMEBACK_REASON_CODES.get(
                runtime_reason
            )
        )

        if not reason_code:
            raise ValueError(
                "Unknown M30 warm comeback reason: "
                + runtime_reason
            )

        return AffectRuleTrace(
            rule_id="warm_comeback",
            decision="suppressed",
            reason_codes=[
                reason_code
            ],
            runtime_reason=runtime_reason,
        )

    if (
        decision.get(
            "expression_policy"
        )
        == "one_short_warm_line"
    ):
        return AffectRuleTrace(
            rule_id="warm_comeback",
            decision="allowed",
            reason_codes=[
                "affect.warm_comeback.allowed.safe_return"
            ],
            runtime_reason=None,
        )

    return AffectRuleTrace(
        rule_id="warm_comeback",
        decision="not_applicable",
    )


def _datetime_to_text(
    value: datetime,
) -> str:
    normalized = value.astimezone(
        timezone.utc
    )

    return normalized.isoformat().replace(
        "+00:00",
        "Z",
    )


def _to_primitive(
    value: Any,
) -> Any:
    if isinstance(
        value,
        datetime,
    ):
        return _datetime_to_text(
            value
        )

    if is_dataclass(value):
        return {
            item.name: _to_primitive(
                getattr(
                    value,
                    item.name,
                )
            )
            for item in fields(value)
        }

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _to_primitive(
                nested
            )
            for key, nested in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _to_primitive(
                nested
            )
            for nested in value
        ]

    return value


_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+"
    r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

_BEARER_RE = re.compile(
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"
)

_SK_RE = re.compile(
    r"\bsk-[A-Za-z0-9_-]{8,}\b"
)


def _bounded_preview(
    value: str,
    *,
    max_chars: int = 240,
) -> str:
    normalized = " ".join(
        str(value).split()
    )

    return normalized[
        :max_chars
    ]


def _sanitize_preview(
    value: Any,
    *,
    preview_policy: PreviewPolicy,
) -> Any:
    if value is None:
        return None

    if preview_policy == "none":
        return None

    text = _bounded_preview(
        str(value)
    )

    if preview_policy == "dev":
        return text

    text = _EMAIL_RE.sub(
        "[redacted-email]",
        text,
    )

    text = _BEARER_RE.sub(
        "Bearer [redacted-token]",
        text,
    )

    text = _SK_RE.sub(
        "[redacted-token]",
        text,
    )

    return text


def _apply_preview_policy(
    value: Any,
    *,
    preview_policy: PreviewPolicy,
) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}

        for key, nested in value.items():
            if key in {
                "preview",
                "raw_preview",
            }:
                result[key] = _sanitize_preview(
                    nested,
                    preview_policy=preview_policy,
                )
            else:
                result[key] = (
                    _apply_preview_policy(
                        nested,
                        preview_policy=preview_policy,
                    )
                )

        return result

    if isinstance(value, list):
        return [
            _apply_preview_policy(
                nested,
                preview_policy=preview_policy,
            )
            for nested in value
        ]

    return value


def _hash_ref(
    value: str,
) -> str:
    digest = hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()[:16]

    return f"ref_{digest}"


def _pseudonymize_refs(
    value: Any,
) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}

        for key, nested in value.items():
            if (
                key.endswith(
                    "_ref"
                )
                and isinstance(
                    nested,
                    str,
                )
            ):
                result[key] = _hash_ref(
                    nested
                )
                continue

            if (
                key.endswith(
                    "_refs"
                )
                and isinstance(
                    nested,
                    list,
                )
            ):
                result[key] = [
                    _hash_ref(
                        str(item)
                    )
                    for item in nested
                ]
                continue

            result[key] = (
                _pseudonymize_refs(
                    nested
                )
            )

        return result

    if isinstance(value, list):
        return [
            _pseudonymize_refs(
                nested
            )
            for nested in value
        ]

    return value


def serialize_trace(
    trace: CognitiveDecisionTrace,
    *,
    preview_policy: PreviewPolicy = "none",
    for_logging: bool = False,
) -> dict[str, Any]:
    if preview_policy not in {
        "none",
        "redacted",
        "dev",
    }:
        raise ValueError(
            "Invalid preview policy"
        )

    validate_trace(trace)

    payload = _to_primitive(
        trace
    )

    payload = _apply_preview_policy(
        payload,
        preview_policy=preview_policy,
    )

    if for_logging:
        payload = _pseudonymize_refs(
            payload
        )

    return payload


def semantic_trace_dict(
    trace: CognitiveDecisionTrace,
) -> dict[str, Any]:
    payload = serialize_trace(
        trace,
        preview_policy="dev",
        for_logging=False,
    )

    def strip_volatile(
        value: Any,
    ) -> Any:
        if isinstance(value, dict):
            result = {}

            for key, nested in value.items():
                if key in {
                    "trace_id",
                    "timestamp_utc",
                    "latency_ms",
                }:
                    continue

                result[key] = strip_volatile(
                    nested
                )

            return result

        if isinstance(value, list):
            return [
                strip_volatile(
                    nested
                )
                for nested in value
            ]

        return value

    return strip_volatile(
        payload
    )


def emit_trace_fail_open(
    sink: TraceSink,
    trace: CognitiveDecisionTrace,
    *,
    logger: logging.Logger | None = None,
) -> bool:
    try:
        validate_trace(
            trace
        )
        sink.emit(
            trace
        )
        return True

    except Exception as exc:
        target_logger = (
            logger
            or logging.getLogger(
                "app.cognitive_trace"
            )
        )

        try:
            target_logger.warning(
                "cognitive trace emission failed: %s",
                exc,
            )
        except Exception:
            pass

        return False


# ---------------------------------------------------------------------------
# M31B chat observation bridge
# ---------------------------------------------------------------------------

_TRACE_SINK_OVERRIDE: TraceSink | None = None


def get_trace_sink(
    *,
    logging_enabled: bool = False,
    preview_policy: str = "none",
) -> TraceSink:
    """Return test override or production-safe configured sink."""

    if _TRACE_SINK_OVERRIDE is not None:
        return _TRACE_SINK_OVERRIDE

    if not logging_enabled:
        return NullTraceSink()

    safe_policy: PreviewPolicy = (
        preview_policy
        if preview_policy in {
            "none",
            "redacted",
            "dev",
        }
        else "none"
    )

    return LoggingTraceSink(
        enabled=True,
        preview_policy=safe_policy,
    )


def set_trace_sink_for_testing(
    sink: TraceSink,
) -> None:
    """Install an in-memory/test sink."""

    global _TRACE_SINK_OVERRIDE
    _TRACE_SINK_OVERRIDE = sink


def reset_trace_sink() -> None:
    """Remove test override and restore configured default behavior."""

    global _TRACE_SINK_OVERRIDE
    _TRACE_SINK_OVERRIDE = None


def _policy_markers(
    *,
    assistant_mode: str | None,
    companion_mode: str | None,
    mood_realism: str | None,
) -> list[str]:
    markers: list[str] = []

    assistant_code = {
        "life_companion":
            "policy.assistant_mode.life_companion",
        "chief_of_staff":
            "policy.assistant_mode.chief_of_staff",
    }.get(
        str(
            assistant_mode
            or ""
        )
    )

    if assistant_code:
        markers.append(
            assistant_code
        )

    companion_code = {
        "professional":
            "policy.companion_mode.professional",
        "friendly":
            "policy.companion_mode.friendly",
        "affectionate":
            "policy.companion_mode.affectionate",
        "partner":
            "policy.companion_mode.partner",
    }.get(
        str(
            companion_mode
            or ""
        )
    )

    if companion_code:
        markers.append(
            companion_code
        )

    realism_code = {
        "stable":
            "policy.mood_realism.stable",
        "dynamic":
            "policy.mood_realism.dynamic",
    }.get(
        str(
            mood_realism
            or ""
        )
    )

    if realism_code:
        markers.append(
            realism_code
        )

    return markers


def _attention_reason_codes(
    packing_intent: str | None,
) -> list[str]:
    code = {
        "general":
            "attention.intent.general",
        "identity":
            "attention.intent.identity",
        "self_regulation":
            "attention.intent.self_regulation",
    }.get(
        str(
            packing_intent
            or ""
        )
    )

    return [
        code
    ] if code else []


def _optional_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _memory_row_ref(
    row: dict[str, Any],
) -> str | None:
    for key in (
        "id",
        "memory_id",
    ):
        value = row.get(
            key
        )

        if value:
            return str(
                value
            )

    return None


def _build_memory_observation(
    *,
    diagnostics: Any,
    legacy_memories: list[dict[str, Any]] | None,
    selected_memory_refs: list[str],
) -> tuple[
    MemoryTrace | None,
    SubsystemHealth | None,
]:
    if diagnostics is None:
        return (
            None,
            None,
        )

    attempted = bool(
        getattr(
            diagnostics,
            "attempted",
            False,
        )
    )

    gate_reason_raw = getattr(
        diagnostics,
        "gate_reason",
        None,
    )

    gate_reason = (
        str(
            gate_reason_raw
        )
        if gate_reason_raw
        else None
    )

    strategy_raw = getattr(
        diagnostics,
        "strategy",
        None,
    )

    strategy = (
        str(
            strategy_raw
        )
        if strategy_raw
        else None
    )

    subsystem_status = str(
        getattr(
            diagnostics,
            "subsystem_status",
            "healthy",
        )
        or "healthy"
    )

    selected = set(
        selected_memory_refs
    )

    candidates: list[
        MemoryCandidateTrace
    ] = []

    for row in (
        legacy_memories
        or []
    ):
        if not isinstance(
            row,
            dict,
        ):
            continue

        memory_ref = _memory_row_ref(
            row
        )

        if not memory_ref:
            continue

        reason_codes: list[str] = []

        if row.get(
            "similarity"
        ) is not None:
            reason_codes.append(
                "memory.retrieved.semantic_match"
            )

        if row.get(
            "structured_field"
        ):
            reason_codes.append(
                "memory.retrieved.structured_field"
            )

        if (
            gate_reason
            and gate_reason.startswith(
                "personal_cue:"
            )
        ):
            reason_codes.append(
                "memory.retrieved.personal_cue_threshold"
            )

        selected_for_prompt = (
            memory_ref
            in selected
        )

        if selected_for_prompt:
            reason_codes.append(
                "memory.selected.packed"
            )

        candidates.append(
            MemoryCandidateTrace(
                memory_ref=memory_ref,
                category=(
                    str(
                        row.get(
                            "category"
                        )
                    )
                    if row.get(
                        "category"
                    )
                    else None
                ),
                structured_field=(
                    str(
                        row.get(
                            "structured_field"
                        )
                    )
                    if row.get(
                        "structured_field"
                    )
                    else None
                ),
                similarity_score=_optional_float(
                    row.get(
                        "similarity"
                    )
                ),
                retrieval_score=_optional_float(
                    row.get(
                        "retrieval_score"
                    )
                ),
                confidence_score=_optional_float(
                    row.get(
                        "confidence"
                    )
                ),
                # Packing score is private to the current
                # packer and is NOT recomputed by M31B.
                packing_score=None,
                # Salience does not exist canonically
                # until M31G.
                salience_score=None,
                selected_for_prompt=(
                    selected_for_prompt
                ),
                reason_codes=reason_codes,
                preview=None,
            )
        )

    memory_trace = MemoryTrace(
        retrieval_attempted=attempted,
        retrieval_gate_reason=gate_reason,
        retrieval_strategy=strategy,
        total_candidates=int(
            getattr(
                diagnostics,
                "fetched_count",
                len(
                    legacy_memories
                    or []
                ),
            )
            or 0
        ),
        candidates=candidates,
        latency_ms=_optional_float(
            getattr(
                diagnostics,
                "latency_ms",
                None,
            )
        ),
        subsystem_status=subsystem_status,
    )

    health_codes = {
        "healthy": [
            "subsystem.healthy"
        ],
        "degraded": [
            "subsystem.degraded.memory_retrieval"
        ],
        "failed": [
            "subsystem.failed.memory_retrieval"
        ],
        "not_applicable": [],
    }.get(
        subsystem_status,
        [],
    )

    health = SubsystemHealth(
        subsystem="memory_retrieval",
        status=subsystem_status,
        reason_codes=health_codes,
        latency_ms=memory_trace.latency_ms,
    )

    return (
        memory_trace,
        health,
    )


def build_metacognitive_policy_trace(
    decision: Any,
) -> MetacognitiveTrace | None:
    if decision is None:
        return None

    return MetacognitiveTrace(
        response_posture=str(
            getattr(
                decision,
                "response_posture",
                "",
            )
            or ""
        ),
        evidence_trust=str(
            getattr(
                decision,
                "evidence_trust",
                "",
            )
            or ""
        ),
        durable_projection_posture=str(
            getattr(
                decision,
                "durable_projection_posture",
                "",
            )
            or ""
        ),
        allow_background_inference=bool(
            getattr(
                decision,
                "allow_background_inference",
                False,
            )
        ),
        unverified_memory_refs=[
            str(value)
            for value in (
                getattr(
                    decision,
                    "unverified_memory_refs",
                    (),
                )
                or ()
            )
        ],
        reason_codes=[
            str(value)
            for value in (
                getattr(
                    decision,
                    "reason_codes",
                    (),
                )
                or ()
            )
        ],
    )


def build_chat_observation_trace(
    *,
    turn_ref: str | None,
    conversation_ref: str | None,
    user_ref: str | None,
    assistant_mode: str | None,
    companion_settings_row: dict[str, Any] | None,
    comeback_affect_decision: dict[str, Any] | None,
    packed_memory_context: Any,
    memory_retrieval_diagnostics: Any = None,
    legacy_memories: list[dict[str, Any]] | None = None,
    metacognitive_decision: Any = None,
    now: datetime | None = None,
) -> CognitiveDecisionTrace:
    """Mirror chat decisions already made by the current runtime.

    Important M31B boundaries:
    - no raw user message is accepted;
    - no retrieval/packing decision is recomputed;
    - no private packer score is recomputed;
    - no salience is inferred;
    - MemoryTrace stays absent until retrieval diagnostics are
      exposed directly by the retrieval subsystem.
    """

    settings_row = (
        companion_settings_row
        if isinstance(
            companion_settings_row,
            dict,
        )
        else {}
    )

    companion_mode = str(
        settings_row.get(
            "companion_mode"
        )
        or ""
    ) or None

    mood_realism = str(
        settings_row.get(
            "mood_realism"
        )
        or ""
    ) or None

    packing_intent = getattr(
        packed_memory_context,
        "intent",
        None,
    )

    selected_memory_refs = [
        str(value)
        for value in (
            getattr(
                packed_memory_context,
                "memory_ids",
                (),
            )
            or ()
        )
    ]

    selected_summary_refs = [
        str(value)
        for value in (
            getattr(
                packed_memory_context,
                "summary_ids",
                (),
            )
            or ()
        )
    ]

    attention = AttentionTrace(
        packing_intent=(
            str(
                packing_intent
            )
            if packing_intent is not None
            else None
        ),
        selected_memory_refs=selected_memory_refs,
        selected_summary_refs=selected_summary_refs,
        dropped_memory_count=int(
            getattr(
                packed_memory_context,
                "dropped_memory_count",
                0,
            )
            or 0
        ),
        dropped_summary_count=int(
            getattr(
                packed_memory_context,
                "dropped_summary_count",
                0,
            )
            or 0
        ),
        packed_context_chars=int(
            getattr(
                packed_memory_context,
                "total_chars",
                0,
            )
            or 0
        ),
        packed_context_budget_chars=None,
        reason_codes=_attention_reason_codes(
            (
                str(
                    packing_intent
                )
                if packing_intent is not None
                else None
            )
        ),
    )

    policy = PolicyTrace(
        assistant_mode=(
            str(
                assistant_mode
            )
            if assistant_mode is not None
            else None
        ),
        companion_mode=companion_mode,
        mood_realism=mood_realism,
        affect_rules=[
            build_warm_comeback_affect_trace(
                comeback_affect_decision
            )
        ],
        metacognition=build_metacognitive_policy_trace(
            metacognitive_decision
        ),
        policy_markers=_policy_markers(
            assistant_mode=assistant_mode,
            companion_mode=companion_mode,
            mood_realism=mood_realism,
        ),
    )

    trace = new_trace(
        turn_ref=(
            str(
                turn_ref
            )
            if turn_ref is not None
            else None
        ),
        conversation_ref=(
            str(
                conversation_ref
            )
            if conversation_ref is not None
            else None
        ),
        user_ref=(
            str(
                user_ref
            )
            if user_ref is not None
            else None
        ),
        now=now,
    )

    trace.attention = attention
    trace.policy = policy

    memory_trace, memory_health = (
        _build_memory_observation(
            diagnostics=memory_retrieval_diagnostics,
            legacy_memories=legacy_memories,
            selected_memory_refs=selected_memory_refs,
        )
    )

    trace.memory = memory_trace

    if memory_health is not None:
        trace.subsystem_health.append(
            memory_health
        )

    # These markers describe actual orchestration already visible
    # in chat.py. They do not participate in behavior.
    trace.legacy_markers.extend(
        [
            "legacy.chatpy.orchestrates_memory",
            "legacy.chatpy.assembles_context",
            "legacy.chatpy.applies_affect_policy",
        ]
    )

    validate_trace(
        trace
    )

    return trace


def record_chat_observation_fail_open(
    *,
    sink: TraceSink,
    turn_ref: str | None,
    conversation_ref: str | None,
    user_ref: str | None,
    assistant_mode: str | None,
    companion_settings_row: dict[str, Any] | None,
    comeback_affect_decision: dict[str, Any] | None,
    packed_memory_context: Any,
    memory_retrieval_diagnostics: Any = None,
    legacy_memories: list[dict[str, Any]] | None = None,
    metacognitive_decision: Any = None,
    logger: logging.Logger | None = None,
) -> bool:
    """Build + emit one partial M31B trace without risking chat."""

    target_logger = (
        logger
        or logging.getLogger(
            "app.cognitive_trace"
        )
    )

    try:
        trace = build_chat_observation_trace(
            turn_ref=turn_ref,
            conversation_ref=conversation_ref,
            user_ref=user_ref,
            assistant_mode=assistant_mode,
            companion_settings_row=companion_settings_row,
            comeback_affect_decision=comeback_affect_decision,
            packed_memory_context=packed_memory_context,
            memory_retrieval_diagnostics=memory_retrieval_diagnostics,
            legacy_memories=legacy_memories,
            metacognitive_decision=metacognitive_decision,
        )

    except Exception as exc:
        try:
            target_logger.warning(
                "cognitive trace observation build failed: %s",
                type(exc).__name__,
            )
        except Exception:
            pass

        return False

    return emit_trace_fail_open(
        sink,
        trace,
        logger=target_logger,
    )
