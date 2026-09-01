from dataclasses import dataclass
from types import SimpleNamespace

from app.services import cognitive_trace


@dataclass(frozen=True)
class FakePackedMemory:
    memory_ids: tuple[str, ...] = ("mem-1",)
    summary_ids: tuple[str, ...] = ()
    dropped_memory_count: int = 0
    dropped_summary_count: int = 0
    total_chars: int = 100
    intent: str = "identity"


def _decision():
    return SimpleNamespace(
        response_posture="clarify",
        evidence_trust="unverified",
        durable_projection_posture="hold_for_confirmation",
        allow_background_inference=False,
        unverified_memory_refs=("mem-1",),
        reason_codes=(
            "metacognition.evidence.unverified",
            "metacognition.response.clarify.personal_context_unavailable",
            "metacognition.projection.hold_for_confirmation",
            "metacognition.background_inference.held",
        ),
    )


def test_chat_trace_contains_metacognitive_policy() -> None:
    trace = cognitive_trace.build_chat_observation_trace(
        turn_ref="turn-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={
            "companion_mode": "friendly",
            "mood_realism": "stable",
        },
        comeback_affect_decision=None,
        packed_memory_context=FakePackedMemory(),
        metacognitive_decision=_decision(),
    )

    assert trace.policy is not None
    assert trace.policy.metacognition is not None

    meta = trace.policy.metacognition

    assert meta.response_posture == "clarify"
    assert meta.evidence_trust == "unverified"
    assert (
        meta.durable_projection_posture
        == "hold_for_confirmation"
    )
    assert meta.allow_background_inference is False
    assert meta.unverified_memory_refs == ["mem-1"]


def test_logging_trace_pseudonymizes_unverified_refs() -> None:
    trace = cognitive_trace.build_chat_observation_trace(
        turn_ref="turn-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=FakePackedMemory(),
        metacognitive_decision=_decision(),
    )

    payload = cognitive_trace.serialize_trace(
        trace,
        preview_policy="none",
        for_logging=True,
    )

    refs = (
        payload["policy"]["metacognition"]
        ["unverified_memory_refs"]
    )

    assert refs
    assert refs[0].startswith("ref_")
    assert "mem-1" not in refs


def test_metacognitive_reason_codes_are_canonical() -> None:
    cognitive_trace.validate_reason_codes(
        [
            "metacognition.evidence.unverified",
            "metacognition.response.caution",
            "metacognition.projection.hold_for_confirmation",
            "metacognition.background_inference.held",
            "metacognition.fallback.safe_default",
        ]
    )


def test_invalid_metacognitive_posture_is_rejected() -> None:
    try:
        cognitive_trace.build_chat_observation_trace(
            turn_ref="turn-1",
            conversation_ref="conv-1",
            user_ref="user-1",
            assistant_mode="life_companion",
            companion_settings_row={},
            comeback_affect_decision=None,
            packed_memory_context=FakePackedMemory(),
            metacognitive_decision=SimpleNamespace(
                response_posture="invalid",
                evidence_trust="trusted",
                durable_projection_posture="eligible",
                allow_background_inference=True,
                unverified_memory_refs=(),
                reason_codes=(
                    "metacognition.evidence.trusted",
                ),
            ),
        )
    except ValueError as exc:
        assert "metacognitive response_posture" in str(exc)
    else:
        raise AssertionError(
            "invalid metacognitive posture should fail validation"
        )


def test_record_chat_observation_emits_one_trace_with_metacognition() -> None:
    sink = cognitive_trace.TestTraceSink()

    ok = cognitive_trace.record_chat_observation_fail_open(
        sink=sink,
        turn_ref="turn-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=FakePackedMemory(),
        metacognitive_decision=_decision(),
    )

    assert ok is True
    assert len(sink.traces) == 1
    assert (
        sink.traces[0].policy.metacognition
        is not None
    )
