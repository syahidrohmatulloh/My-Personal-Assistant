import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.services.cognitive_trace import (
    REASON_CODES,
    AffectRuleTrace,
    AttentionTrace,
    CognitiveDecisionTrace,
    LoggingTraceSink,
    MemoryCandidateTrace,
    MemoryTrace,
    NullTraceSink,
    PerceptionTrace,
    PolicyTrace,
    TestTraceSink,
    build_warm_comeback_affect_trace,
    emit_trace_fail_open,
    new_trace,
    semantic_trace_dict,
    serialize_trace,
    validate_trace,
)


def _trace(
    **overrides,
) -> CognitiveDecisionTrace:
    base = {
        "trace_id": "tr_test",
        "version": "M31B-v1",
        "timestamp_utc": datetime(
            2026,
            9,
            1,
            1,
            0,
            tzinfo=timezone.utc,
        ),
        "turn_ref": "turn-123",
        "conversation_ref": "conversation-456",
        "user_ref": "user-789",
    }

    base.update(
        overrides
    )

    return CognitiveDecisionTrace(
        **base
    )


def test_reason_registry_matches_locked_taxonomy() -> None:
    assert len(REASON_CODES) == 80

    assert (
        "affect.warm_comeback.suppressed.serious_work_task"
        in REASON_CODES
    )

    assert (
        "memory.selected.high_salience"
        not in REASON_CODES
    )


def test_minimal_trace_serializes_safely() -> None:
    trace = _trace()

    payload = serialize_trace(
        trace
    )

    assert payload["trace_id"] == "tr_test"
    assert payload["version"] == "M31B-v1"
    assert (
        payload["timestamp_utc"]
        == "2026-09-01T01:00:00Z"
    )

    assert payload["memory"] is None
    assert payload["policy"] is None


def test_new_trace_generates_aware_timestamp() -> None:
    trace = new_trace(
        user_ref="user-1"
    )

    assert trace.trace_id.startswith(
        "tr_"
    )

    assert trace.version == "M31B-v1"
    assert trace.timestamp_utc.tzinfo is not None


def test_unknown_reason_code_is_rejected() -> None:
    trace = _trace(
        attention=AttentionTrace(
            reason_codes=[
                "memory.magic.unknown"
            ]
        )
    )

    with pytest.raises(
        ValueError,
        match="Unknown M31B reason code",
    ):
        validate_trace(
            trace
        )


def test_m31b_salience_must_remain_none() -> None:
    trace = _trace(
        memory=MemoryTrace(
            retrieval_attempted=True,
            candidates=[
                MemoryCandidateTrace(
                    memory_ref="m1",
                    salience_score=0.99,
                )
            ],
        )
    )

    with pytest.raises(
        ValueError,
        match="salience_score must remain None",
    ):
        validate_trace(
            trace
        )


def test_preview_none_removes_raw_preview_content() -> None:
    trace = _trace(
        memory=MemoryTrace(
            retrieval_attempted=True,
            candidates=[
                MemoryCandidateTrace(
                    memory_ref="m1",
                    preview="private memory text",
                )
            ],
        )
    )

    payload = serialize_trace(
        trace,
        preview_policy="none",
    )

    assert (
        payload["memory"]["candidates"][0]["preview"]
        is None
    )


def test_redacted_preview_scrubs_email_and_token() -> None:
    trace = _trace(
        memory=MemoryTrace(
            retrieval_attempted=True,
            candidates=[
                MemoryCandidateTrace(
                    memory_ref="m1",
                    preview=(
                        "email me at person@example.com "
                        "using sk-supersecret1234567890"
                    ),
                )
            ],
        )
    )

    payload = serialize_trace(
        trace,
        preview_policy="redacted",
    )

    preview = (
        payload["memory"]["candidates"][0]["preview"]
    )

    assert "person@example.com" not in preview
    assert "sk-supersecret1234567890" not in preview
    assert "[redacted-email]" in preview
    assert "[redacted-token]" in preview


def test_logging_serializer_pseudonymizes_refs() -> None:
    trace = _trace(
        memory=MemoryTrace(
            retrieval_attempted=True,
            candidates=[
                MemoryCandidateTrace(
                    memory_ref="memory-secret-id",
                )
            ],
        ),
        attention=AttentionTrace(
            selected_memory_refs=[
                "memory-secret-id"
            ],
        ),
    )

    payload = serialize_trace(
        trace,
        preview_policy="none",
        for_logging=True,
    )

    encoded = json.dumps(
        payload
    )

    assert "user-789" not in encoded
    assert "conversation-456" not in encoded
    assert "turn-123" not in encoded
    assert "memory-secret-id" not in encoded
    assert "ref_" in encoded


def test_null_sink_has_no_side_effect() -> None:
    trace = _trace()

    sink = NullTraceSink()

    assert emit_trace_fail_open(
        sink,
        trace,
    )


def test_test_sink_captures_trace() -> None:
    trace = _trace()

    sink = TestTraceSink()

    assert emit_trace_fail_open(
        sink,
        trace,
    )

    assert sink.traces == [
        trace
    ]


def test_disabled_logging_sink_emits_nothing(
    caplog,
) -> None:
    logger = logging.getLogger(
        "tests.cognitive_trace.disabled"
    )

    caplog.set_level(
        logging.INFO,
        logger=logger.name,
    )

    sink = LoggingTraceSink(
        enabled=False,
        logger=logger,
    )

    sink.emit(
        _trace()
    )

    assert "cognitive_trace=" not in caplog.text


def test_enabled_logging_sink_uses_safe_serialization(
    caplog,
) -> None:
    logger = logging.getLogger(
        "tests.cognitive_trace.enabled"
    )

    caplog.set_level(
        logging.INFO,
        logger=logger.name,
    )

    sink = LoggingTraceSink(
        enabled=True,
        preview_policy="none",
        logger=logger,
    )

    trace = _trace(
        memory=MemoryTrace(
            retrieval_attempted=True,
            candidates=[
                MemoryCandidateTrace(
                    memory_ref="memory-raw-ref",
                    preview="private user content",
                )
            ],
        )
    )

    sink.emit(
        trace
    )

    assert "cognitive_trace=" in caplog.text
    assert "private user content" not in caplog.text
    assert "memory-raw-ref" not in caplog.text
    assert "user-789" not in caplog.text


def test_sink_failure_is_fail_open() -> None:
    class BrokenSink:
        def emit(
            self,
            trace,
        ) -> None:
            raise RuntimeError(
                "boom"
            )

    assert not emit_trace_fail_open(
        BrokenSink(),
        _trace(),
    )


def test_warm_comeback_serious_work_mapping() -> None:
    affect = build_warm_comeback_affect_trace(
        {
            "label": "none",
            "expression_policy": "suppress_total",
            "must_suppress_reason": "serious_work_task",
        }
    )

    assert affect.decision == "suppressed"
    assert affect.runtime_reason == "serious_work_task"
    assert affect.reason_codes == [
        "affect.warm_comeback.suppressed.serious_work_task"
    ]


def test_warm_comeback_allowed_is_permission_only() -> None:
    affect = build_warm_comeback_affect_trace(
        {
            "label": "warm_return",
            "expression_policy": "one_short_warm_line",
            "must_suppress_reason": None,
        }
    )

    assert affect.decision == "allowed"
    assert affect.reason_codes == [
        "affect.warm_comeback.allowed.safe_return"
    ]


def test_semantic_trace_comparison_ignores_runtime_noise() -> None:
    first = _trace(
        trace_id="tr_1",
        timestamp_utc=datetime(
            2026,
            9,
            1,
            1,
            0,
            tzinfo=timezone.utc,
        ),
        perception=PerceptionTrace(
            personal_cue=True,
            latency_ms=1.0,
        ),
        policy=PolicyTrace(
            assistant_mode="life_companion",
            companion_mode="partner",
            mood_realism="dynamic",
            affect_rules=[
                AffectRuleTrace(
                    rule_id="warm_comeback",
                    decision="not_applicable",
                )
            ],
        ),
    )

    second = _trace(
        trace_id="tr_2",
        timestamp_utc=datetime(
            2026,
            9,
            1,
            2,
            0,
            tzinfo=timezone.utc,
        ),
        perception=PerceptionTrace(
            personal_cue=True,
            latency_ms=999.0,
        ),
        policy=PolicyTrace(
            assistant_mode="life_companion",
            companion_mode="partner",
            mood_realism="dynamic",
            affect_rules=[
                AffectRuleTrace(
                    rule_id="warm_comeback",
                    decision="not_applicable",
                )
            ],
        ),
    )

    assert (
        semantic_trace_dict(first)
        == semantic_trace_dict(second)
    )


def test_semantic_trace_keeps_actual_decision_changes() -> None:
    first = _trace(
        policy=PolicyTrace(
            assistant_mode="life_companion",
        )
    )

    second = _trace(
        policy=PolicyTrace(
            assistant_mode="chief_of_staff",
        )
    )

    assert (
        semantic_trace_dict(first)
        != semantic_trace_dict(second)
    )
