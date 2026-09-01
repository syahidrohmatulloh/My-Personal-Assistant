from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services import cognitive_trace
from app.services.cognitive_trace import (
    NullTraceSink,
    TestTraceSink,
    build_chat_observation_trace,
    record_chat_observation_fail_open,
)


@dataclass(frozen=True)
class FakePackedMemory:
    memory_count: int = 2
    summary_count: int = 1
    dropped_memory_count: int = 3
    dropped_summary_count: int = 2
    total_chars: int = 640
    memory_ids: tuple[str, ...] = (
        "mem-a",
        "mem-b",
    )
    summary_ids: tuple[str, ...] = (
        "sum-a",
    )
    intent: str = "identity"


def test_chat_observation_mirrors_packed_memory_only() -> None:
    trace = build_chat_observation_trace(
        turn_ref="msg-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={
            "companion_mode": "partner",
            "mood_realism": "dynamic",
        },
        comeback_affect_decision={
            "label": "warm_return",
            "expression_policy":
                "one_short_warm_line",
            "must_suppress_reason": None,
        },
        packed_memory_context=FakePackedMemory(),
        now=datetime(
            2026,
            9,
            1,
            1,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert trace.memory is None

    assert trace.attention is not None
    assert (
        trace.attention.packing_intent
        == "identity"
    )
    assert (
        trace.attention.selected_memory_refs
        == ["mem-a", "mem-b"]
    )
    assert (
        trace.attention.selected_summary_refs
        == ["sum-a"]
    )
    assert (
        trace.attention.dropped_memory_count
        == 3
    )
    assert (
        trace.attention.dropped_summary_count
        == 2
    )
    assert (
        trace.attention.packed_context_chars
        == 640
    )

    # Budget is intentionally absent because the packed
    # result does not expose the effective budget.
    assert (
        trace.attention.packed_context_budget_chars
        is None
    )

    assert trace.attention.reason_codes == [
        "attention.intent.identity"
    ]


def test_chat_observation_mirrors_current_policy() -> None:
    trace = build_chat_observation_trace(
        turn_ref="msg-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="chief_of_staff",
        companion_settings_row={
            "companion_mode": "professional",
            "mood_realism": "stable",
        },
        comeback_affect_decision={
            "label": "none",
            "expression_policy":
                "suppress_total",
            "must_suppress_reason":
                "assistant_mode_not_life_companion",
        },
        packed_memory_context=FakePackedMemory(
            intent="general"
        ),
    )

    assert trace.policy is not None

    assert (
        trace.policy.assistant_mode
        == "chief_of_staff"
    )
    assert (
        trace.policy.companion_mode
        == "professional"
    )
    assert (
        trace.policy.mood_realism
        == "stable"
    )

    assert trace.policy.policy_markers == [
        "policy.assistant_mode.chief_of_staff",
        "policy.companion_mode.professional",
        "policy.mood_realism.stable",
    ]

    affect = trace.policy.affect_rules[0]

    assert affect.decision == "suppressed"
    assert (
        affect.runtime_reason
        == "assistant_mode_not_life_companion"
    )

    assert affect.reason_codes == [
        "affect.warm_comeback.suppressed."
        "assistant_mode_not_life_companion"
    ]


def test_chat_observation_has_only_grounded_legacy_markers() -> None:
    trace = build_chat_observation_trace(
        turn_ref=None,
        conversation_ref=None,
        user_ref=None,
        assistant_mode="life_companion",
        companion_settings_row={
            "companion_mode": "friendly",
            "mood_realism": "stable",
        },
        comeback_affect_decision=None,
        packed_memory_context=FakePackedMemory(),
    )

    assert trace.legacy_markers == [
        "legacy.chatpy.orchestrates_memory",
        "legacy.chatpy.assembles_context",
        "legacy.chatpy.applies_affect_policy",
    ]


def test_record_chat_observation_reaches_test_sink() -> None:
    sink = TestTraceSink()

    ok = record_chat_observation_fail_open(
        sink=sink,
        turn_ref="msg-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={
            "companion_mode": "partner",
            "mood_realism": "dynamic",
        },
        comeback_affect_decision=None,
        packed_memory_context=FakePackedMemory(),
    )

    assert ok is True
    assert len(sink.traces) == 1


def test_default_runtime_sink_remains_null() -> None:
    cognitive_trace.reset_trace_sink()

    assert isinstance(
        cognitive_trace.get_trace_sink(),
        NullTraceSink,
    )


def test_chat_wiring_is_observational() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    assert (
        "cognitive_trace.record_chat_observation_fail_open("
        in source
    )

    assert (
        "sink=cognitive_trace.get_trace_sink("
        in source
    )

    hook_start = source.index(
        "cognitive_trace.record_chat_observation_fail_open("
    )

    hook_end = source.index(
        "\n    )",
        hook_start,
    )

    hook = source[
        hook_start:hook_end
    ]

    # Raw user content must not be handed to the
    # M31B observation bridge.
    assert "body.message" not in hook
    assert "user_message=" not in hook

    assert (
        "packed_memory_context=packed_memory_context"
        in hook
    )
    assert (
        "comeback_affect_decision="
        "comeback_affect_decision"
        in hook
    )


def test_explicit_logging_enable_selects_logging_sink() -> None:
    cognitive_trace.reset_trace_sink()

    sink = cognitive_trace.get_trace_sink(
        logging_enabled=True,
        preview_policy="none",
    )

    assert isinstance(
        sink,
        cognitive_trace.LoggingTraceSink,
    )

    assert sink.enabled is True
    assert sink.preview_policy == "none"


def test_trace_sink_invalid_preview_fails_safe_to_none() -> None:
    cognitive_trace.reset_trace_sink()

    sink = cognitive_trace.get_trace_sink(
        logging_enabled=True,
        preview_policy="unsafe-value",
    )

    assert isinstance(
        sink,
        cognitive_trace.LoggingTraceSink,
    )

    assert sink.preview_policy == "none"


def test_chat_trace_logging_is_explicitly_config_gated() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    assert (
        "logging_enabled=settings.COGNITIVE_TRACE_LOG"
        in source
    )

    assert (
        "preview_policy=settings.COGNITIVE_TRACE_PREVIEW_POLICY"
        in source
    )
