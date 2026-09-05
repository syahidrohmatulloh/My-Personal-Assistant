from dataclasses import fields
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import metacognitive_policy
from app.services import working_memory


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _state(
    *,
    history_count: int = 3,
    retrieval_status: str | None = "healthy",
    retrieval_gate_reason: str | None = None,
    packing_intent: str | None = "general",
    selected_memory_refs: tuple[str, ...] = (),
) -> working_memory.WorkingMemoryState:
    return working_memory.WorkingMemoryState(
        version=working_memory.WORKING_MEMORY_VERSION,
        created_at_utc=NOW,
        history=working_memory.HistoryWorkingState(
            message_count=history_count,
        ),
        memory=working_memory.MemoryWorkingState(
            retrieval_attempted=(
                retrieval_status
                not in {None, "not_applicable"}
            ),
            retrieval_gate_reason=retrieval_gate_reason,
            retrieval_status=retrieval_status,
            selected_memory_refs=selected_memory_refs,
            packing_intent=packing_intent,
        ),
    )


def test_default_general_turn_proceeds() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(),
        user_message="jelaskan perbedaan LLM dan VLM",
        recent_messages=[],
        now=NOW,
    )

    assert decision.response_posture == "proceed"
    assert decision.evidence_trust == "not_applicable"
    assert decision.durable_projection_posture == "eligible"
    assert decision.allow_background_inference is True
    assert (
        "metacognition.response.proceed"
        in decision.reason_codes
    )


def test_only_selected_memory_rows_affect_trust() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            packing_intent="identity",
            selected_memory_refs=("trusted",),
        ),
        legacy_memories=[
            {
                "id": "trusted",
                "status": "active",
                "created_at": NOW.isoformat(),
                "confidence": 0.95,
            },
            {
                "id": "not-selected",
                "status": "active",
                "created_at": NOW.isoformat(),
                "confidence": 0.10,
            },
        ],
        user_message="apa timezone saya?",
        now=NOW,
    )

    assert decision.evidence_trust == "trusted"
    assert decision.response_posture == "proceed"
    assert decision.unverified_memory_refs == ()


def test_low_confidence_selected_personal_memory_clarifies() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            packing_intent="identity",
            selected_memory_refs=("low",),
        ),
        legacy_memories=[
            {
                "id": "low",
                "status": "active",
                "created_at": NOW.isoformat(),
                "confidence": 0.20,
            }
        ],
        user_message="apa nama panggilan saya?",
        now=NOW,
    )

    assert decision.evidence_trust == "unverified"
    assert decision.response_posture == "clarify"
    assert (
        decision.durable_projection_posture
        == "hold_for_confirmation"
    )
    assert decision.allow_background_inference is False
    assert decision.unverified_memory_refs == ("low",)


def test_stale_memory_is_unverified() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            selected_memory_refs=("stale",),
        ),
        legacy_memories=[
            {
                "id": "stale",
                "status": "active",
                "created_at": (
                    NOW - timedelta(days=500)
                ).isoformat(),
                "confidence": 0.95,
            }
        ],
        user_message="lanjutkan",
        now=NOW,
    )

    assert decision.evidence_trust == "unverified"
    assert decision.response_posture == "caution"


def test_canonically_confirmed_old_memory_remains_trusted() -> None:
    old = (NOW - timedelta(days=700)).isoformat()

    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            packing_intent="identity",
            selected_memory_refs=("confirmed",),
        ),
        legacy_memories=[
            {
                "id": "confirmed",
                "status": "active",
                "created_at": old,
                "last_user_confirmed_at": old,
                "confidence": 0.95,
            }
        ],
        user_message="apa data profil saya?",
        now=NOW,
    )

    assert decision.evidence_trust == "trusted"
    assert decision.response_posture == "proceed"


def test_mixed_evidence_answers_cautiously_and_holds_projection() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            selected_memory_refs=("good", "weak"),
        ),
        legacy_memories=[
            {
                "id": "good",
                "status": "active",
                "created_at": NOW.isoformat(),
                "confidence": 0.95,
            },
            {
                "id": "weak",
                "status": "active",
                "created_at": NOW.isoformat(),
                "confidence": 0.20,
            },
        ],
        user_message="bandingkan konteksnya",
        now=NOW,
    )

    assert decision.evidence_trust == "mixed"
    assert decision.response_posture == "caution"
    assert (
        decision.durable_projection_posture
        == "hold_for_confirmation"
    )
    assert decision.allow_background_inference is False


def test_structured_memory_contradiction_clarifies() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            packing_intent="identity",
            selected_memory_refs=("a", "b"),
        ),
        legacy_memories=[
            {
                "id": "a",
                "status": "active",
                "confidence": 0.95,
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
            {
                "id": "b",
                "status": "active",
                "confidence": 0.95,
                "structured_field": "timezone",
                "structured_value": "Asia/Makassar",
            },
        ],
        user_message="timezone saya yang mana?",
        now=NOW,
    )

    assert decision.response_posture == "clarify"
    assert (
        "metacognition.response.clarify.contradiction"
        in decision.reason_codes
    )


def test_first_turn_unresolved_referent_clarifies() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            history_count=1,
        ),
        user_message="yang tadi",
        recent_messages=[],
        now=NOW,
    )

    assert decision.response_posture == "clarify"
    assert (
        "metacognition.response.clarify.ambiguity"
        in decision.reason_codes
    )


def test_single_rephrase_is_caution_and_holds_inference() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(),
        user_message="bukan itu, maksud saya versi sebelumnya",
        recent_messages=[
            {
                "role": "user",
                "content": "tolong ubah bagian tadi",
            }
        ],
        now=NOW,
    )

    assert decision.response_posture == "caution"
    assert decision.allow_background_inference is False
    assert (
        "metacognition.rephrase.detected"
        in decision.reason_codes
    )


def test_repeated_rephrase_clarifies() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(),
        user_message="bukan itu, maksud saya yang pertama",
        recent_messages=[
            {
                "role": "user",
                "content": "maksud saya bukan bagian itu",
            },
            {
                "role": "assistant",
                "content": "ok",
            },
        ],
        now=NOW,
    )

    assert decision.response_posture == "clarify"
    assert (
        "metacognition.response.clarify.repeated_rephrase"
        in decision.reason_codes
    )


def test_failed_required_personal_retrieval_clarifies() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            retrieval_status="failed",
            retrieval_gate_reason="personal_cue:identity",
            packing_intent="identity",
        ),
        user_message="apa ulang tahun saya?",
        now=NOW,
    )

    assert decision.evidence_trust == "unavailable"
    assert decision.response_posture == "clarify"


def test_degraded_required_personal_retrieval_is_caution() -> None:
    decision = metacognitive_policy.evaluate_metacognitive_policy(
        working_state=_state(
            retrieval_status="degraded",
            retrieval_gate_reason="personal_cue:identity",
            packing_intent="identity",
        ),
        user_message="apa ulang tahun saya?",
        now=NOW,
    )

    assert decision.evidence_trust == "unavailable"
    assert decision.response_posture == "caution"


def test_prompt_directive_is_high_level_and_content_free() -> None:
    decision = metacognitive_policy.MetacognitiveDecision(
        version="M31F-v1",
        response_posture="clarify",
        evidence_trust="unverified",
        durable_projection_posture="hold_for_confirmation",
        allow_background_inference=False,
        reason_codes=(
            "metacognition.response.clarify.contradiction",
        ),
        unverified_memory_refs=("SECRET-REF",),
    )

    directive = metacognitive_policy.render_prompt_directive(
        decision
    )

    assert directive is not None
    assert "Ask ONE concise clarification question" in directive
    assert "SECRET-REF" not in directive


def test_safe_default_is_behavior_preserving() -> None:
    decision = metacognitive_policy.safe_default_decision()

    assert decision.response_posture == "proceed"
    assert decision.durable_projection_posture == "eligible"
    assert decision.allow_background_inference is True
    assert (
        "metacognition.fallback.safe_default"
        in decision.reason_codes
    )


def test_decision_keeps_confidence_salience_relevance_separate() -> None:
    names = {
        item.name
        for item in fields(
            metacognitive_policy.MetacognitiveDecision
        )
    }

    assert names.isdisjoint(
        {
            "confidence",
            "confidence_score",
            "salience",
            "salience_score",
            "relevance",
            "relevance_score",
        }
    )

    assert (
        metacognitive_policy.decision_has_separate_score_axes()
        is True
    )
