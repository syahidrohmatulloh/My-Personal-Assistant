from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import attention_salience
from app.services.cognitive_trace import (
    REASON_CODES,
    MemoryCandidateTrace,
    MemoryTrace,
    TestTraceSink,
    build_chat_observation_trace,
    new_trace,
    record_chat_observation_fail_open,
    serialize_trace,
    validate_trace,
)


class Packed:
    memory_ids = (
        "mem-1",
        "mem-2",
    )
    summary_ids = ()
    dropped_memory_count = 0
    dropped_summary_count = 0
    total_chars = 400
    intent = "general"


def _decision():
    return attention_salience.AttentionDecision(
        version=attention_salience.ATTENTION_SALIENCE_VERSION,
        level="high",
        candidates=(
            attention_salience.CandidateSalience(
                memory_ref="mem-1",
                score=0.78,
                tier="high",
                reason_codes=(
                    "attention.salience.category.core",
                    "attention.salience.structured.core_field",
                    "attention.salience.tier.high",
                ),
            ),
            attention_salience.CandidateSalience(
                memory_ref="mem-2",
                score=0.32,
                tier="low",
                reason_codes=(
                    "attention.salience.category.context",
                    "attention.salience.tier.low",
                ),
            ),
        ),
        salient_memory_refs=(
            "mem-1",
        ),
        attended_memory_refs=(
            "mem-1",
        ),
        suppressed_memory_refs=(),
        reason_codes=(
            "attention.focus.selected",
            "attention.salience.level.high",
        ),
    )


def _diagnostics():
    return SimpleNamespace(
        attempted=True,
        gate_reason="personal_cue:explicit_memory",
        strategy="semantic",
        fetched_count=2,
        latency_ms=4.2,
        subsystem_status="healthy",
    )





def test_attention_reason_codes_are_registered_in_trace_taxonomy() -> None:
    assert (
        attention_salience
        .ATTENTION_REASON_CODES
        .issubset(
            REASON_CODES
        )
    )


def test_trace_carries_m31g_attention_and_candidate_salience() -> None:
    trace = build_chat_observation_trace(
        turn_ref="turn-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=Packed(),
        memory_retrieval_diagnostics=_diagnostics(),
        legacy_memories=[
            {
                "id": "mem-1",
                "category": "identity",
                "structured_field": "preferred_name",
                "confidence": 0.90,
            },
            {
                "id": "mem-2",
                "category": "context",
                "confidence": 0.90,
            },
        ],
        attention_decision=_decision(),
        now=datetime(
            2026,
            9,
            1,
            8,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert trace.attention is not None
    assert (
        trace.attention.attention_level
        == "high"
    )
    assert (
        trace.attention.salient_memory_refs
        == [
            "mem-1"
        ]
    )
    assert (
        trace.attention.attended_memory_refs
        == [
            "mem-1"
        ]
    )

    assert trace.memory is not None

    by_ref = {
        candidate.memory_ref: candidate
        for candidate in trace.memory.candidates
    }

    assert (
        by_ref["mem-1"].salience_score
        == 0.78
    )

    assert (
        "attention.salience.tier.high"
        in by_ref["mem-1"].reason_codes
    )

    assert (
        by_ref["mem-2"].salience_score
        == 0.32
    )


def test_trace_without_m31g_decision_remains_backward_compatible() -> None:
    trace = build_chat_observation_trace(
        turn_ref=None,
        conversation_ref=None,
        user_ref=None,
        assistant_mode=None,
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=Packed(),
        memory_retrieval_diagnostics=_diagnostics(),
        legacy_memories=[
            {
                "id": "mem-1",
                "category": "identity",
            }
        ],
    )

    assert trace.attention is not None
    assert (
        trace.attention.attention_level
        is None
    )

    assert trace.memory is not None
    assert (
        trace.memory.candidates[0].salience_score
        is None
    )


def test_m31g_salience_score_must_be_bounded() -> None:
    trace = new_trace()

    trace.memory = MemoryTrace(
        retrieval_attempted=True,
        candidates=[
            MemoryCandidateTrace(
                memory_ref="mem-1",
                salience_score=1.01,
            )
        ],
    )

    with pytest.raises(
        ValueError,
        match="salience_score must be between",
    ):
        validate_trace(
            trace
        )


def test_logging_pseudonymizes_attention_refs() -> None:
    trace = build_chat_observation_trace(
        turn_ref="turn-private",
        conversation_ref="conv-private",
        user_ref="user-private",
        assistant_mode=None,
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=Packed(),
        memory_retrieval_diagnostics=_diagnostics(),
        legacy_memories=[
            {
                "id": "mem-1",
                "category": "identity",
            },
            {
                "id": "mem-2",
                "category": "context",
            },
        ],
        attention_decision=_decision(),
    )

    payload = serialize_trace(
        trace,
        for_logging=True,
    )

    assert (
        payload["attention"][
            "salient_memory_refs"
        ][0]
        != "mem-1"
    )

    assert (
        payload["attention"][
            "attended_memory_refs"
        ][0]
        != "mem-1"
    )


def test_record_emits_one_trace_with_attention() -> None:
    sink = TestTraceSink()

    ok = record_chat_observation_fail_open(
        sink=sink,
        turn_ref="turn-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=Packed(),
        memory_retrieval_diagnostics=_diagnostics(),
        legacy_memories=[
            {
                "id": "mem-1",
                "category": "identity",
            },
            {
                "id": "mem-2",
                "category": "context",
            },
        ],
        attention_decision=_decision(),
    )

    assert ok is True
    assert len(sink.traces) == 1
    assert (
        sink.traces[0]
        .attention
        .attention_level
        == "high"
    )
