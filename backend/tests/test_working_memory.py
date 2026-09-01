import inspect
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.working_memory import (
    WORKING_MEMORY_VERSION,
    WorkingMemoryState,
    build_working_memory_state,
    validate_working_memory_state,
    working_memory_metadata_dict,
)


def _packed_memory():
    return SimpleNamespace(
        memory_ids=(
            "mem-1",
            "mem-2",
        ),
        summary_ids=(
            "sum-1",
        ),
        dropped_memory_count=3,
        dropped_summary_count=2,
        intent="identity",
        total_chars=640,
    )


def _memory_assembly():
    diagnostics = SimpleNamespace(
        attempted=True,
        gate_reason="personal_cue:explicit_memory",
        subsystem_status="healthy",
    )

    return SimpleNamespace(
        legacy_memories=[
            {
                "id": "mem-1",
                "content": "private memory one",
            },
            {
                "id": "mem-2",
                "content": "private memory two",
            },
        ],
        related_summaries=[
            {
                "id": "sum-1",
                "summary": "private summary",
            }
        ],
        memory_retrieval_diagnostics=diagnostics,
    )


def test_minimal_working_memory_state() -> None:
    state = build_working_memory_state(
        user_ref="user-1",
        conversation_ref="conv-1",
        turn_ref="msg-1",
        now=datetime(
            2026,
            9,
            1,
            4,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert isinstance(
        state,
        WorkingMemoryState,
    )

    assert (
        state.version
        == WORKING_MEMORY_VERSION
    )

    assert (
        state.created_at_utc.isoformat()
        == "2026-09-01T04:00:00+00:00"
    )

    assert state.turn.user_ref == "user-1"
    assert state.turn.conversation_ref == "conv-1"
    assert state.turn.turn_ref == "msg-1"


def test_naive_now_is_normalized_to_utc() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        now=datetime(
            2026,
            9,
            1,
            4,
            0,
        ),
    )

    assert state.created_at_utc.tzinfo is not None


def test_working_memory_is_immutable() -> None:
    state = build_working_memory_state(
        user_ref="user-1",
        conversation_ref="conv-1",
        turn_ref="msg-1",
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        state.turn.user_ref = "changed"


def test_history_metadata_is_mirrored() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        history_message_count=7,
        is_first_message=False,
        history_load_latency_ms=12.4,
    )

    assert state.history.message_count == 7
    assert state.history.is_first_message is False
    assert state.history.load_latency_ms == 12.4


def test_current_modes_are_mirrored() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        assistant_mode="chief_of_staff",
        detected_mode="practical",
        companion_settings_row={
            "companion_mode": "professional",
            "mood_realism": "stable",
            "repair_gate_enabled": False,
            "preferences": {
                "assistant_mode":
                    "life_companion",
            },
        },
    )

    # Explicit current runtime value wins over settings snapshot.
    assert (
        state.mode.assistant_mode
        == "chief_of_staff"
    )

    assert (
        state.mode.detected_mode
        == "practical"
    )

    assert (
        state.mode.companion_mode
        == "professional"
    )

    assert (
        state.mode.mood_realism
        == "stable"
    )

    assert (
        state.mode.repair_gate_enabled
        is False
    )


def test_settings_can_supply_assistant_mode() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        assistant_mode=None,
        companion_settings_row={
            "companion_mode": "friendly",
            "mood_realism": "stable",
            "preferences": {
                "assistant_mode":
                    "life_companion",
            },
        },
    )

    assert (
        state.mode.assistant_mode
        == "life_companion"
    )


def test_invalid_assistant_mode_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="Invalid assistant_mode",
    ):
        build_working_memory_state(
            user_ref=None,
            conversation_ref=None,
            turn_ref=None,
            assistant_mode="coach",
        )


def test_user_and_companion_mood_stay_separate() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        companion_settings_row={
            "companion_mode": "partner",
            "mood_realism": "dynamic",
        },
        user_mood_context={
            "has_data": True,
            "current_message_signal": {
                "mood_hint": "tired",
                "confidence": 0.6,
            },
        },
        current_mood={
            "mood": "warm",
        },
    )

    assert (
        state.mood.user_mood_has_data
        is True
    )

    assert (
        state.mood.user_mood_label
        == "tired"
    )

    assert (
        state.mood.user_mood_confidence
        == 0.6
    )

    assert (
        state.mood.companion_mood_active
        is True
    )

    assert (
        state.mood.companion_mood_label
        == "warm"
    )


def test_companion_mood_inactive_outside_partner_dynamic() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        companion_settings_row={
            "companion_mode": "friendly",
            "mood_realism": "stable",
        },
        current_mood={
            "mood": "warm",
        },
    )

    assert (
        state.mood.companion_mood_active
        is False
    )


def test_temporal_state_uses_existing_client_metadata_only() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        client_context={
            "timezone": "Asia/Makassar",
            "local_time":
                "2026-09-01T12:15:00+08:00",
            "other_private_field":
                "must-not-be-retained",
        },
    )

    assert (
        state.temporal.timezone
        == "Asia/Makassar"
    )

    assert (
        state.temporal.local_time_iso
        == "2026-09-01T12:15:00+08:00"
    )

    assert (
        state.temporal.client_time_available
        is True
    )

    payload = working_memory_metadata_dict(
        state
    )

    assert (
        "must-not-be-retained"
        not in str(
            payload
        )
    )


def test_memory_state_mirrors_retrieval_and_packer() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        memory_assembly=_memory_assembly(),
        packed_memory_context=_packed_memory(),
    )

    assert (
        state.memory.retrieval_attempted
        is True
    )

    assert (
        state.memory.retrieval_gate_reason
        == "personal_cue:explicit_memory"
    )

    assert (
        state.memory.retrieval_status
        == "healthy"
    )

    assert (
        state.memory.retrieved_memory_refs
        == (
            "mem-1",
            "mem-2",
        )
    )

    assert (
        state.memory.related_summary_refs
        == (
            "sum-1",
        )
    )

    assert (
        state.memory.selected_memory_refs
        == (
            "mem-1",
            "mem-2",
        )
    )

    assert (
        state.memory.selected_summary_refs
        == (
            "sum-1",
        )
    )

    assert (
        state.memory.dropped_memory_count
        == 3
    )

    assert (
        state.memory.dropped_summary_count
        == 2
    )

    assert (
        state.memory.packing_intent
        == "identity"
    )

    assert (
        state.memory.packed_context_chars
        == 640
    )


def test_memory_content_is_not_retained() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        memory_assembly=_memory_assembly(),
        packed_memory_context=_packed_memory(),
    )

    payload = working_memory_metadata_dict(
        state
    )

    encoded = str(
        payload
    )

    assert "private memory one" not in encoded
    assert "private memory two" not in encoded
    assert "private summary" not in encoded


def test_memory_state_has_no_packing_or_salience_score() -> None:
    names = {
        field.name
        for field in state_fields(
            "MemoryWorkingState"
        )
    }

    assert "packing_score" not in names
    assert "salience_score" not in names


def state_fields(
    class_name: str,
):
    import app.services.working_memory as wm

    cls = getattr(
        wm,
        class_name,
    )

    return cls.__dataclass_fields__.values()


def test_calendar_state_retains_only_turn_flags() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        calendar_draft_action_turn=True,
        calendar_candidate_turn=False,
        calendar_action_result={
            "ok": True,
            "title": "SECRET EVENT",
        },
        calendar_confirmation_result={
            "executed": True,
            "event": "PRIVATE",
        },
        calendar_candidate_result={
            "saved": False,
            "candidate": {
                "title": "PRIVATE"
            },
        },
        calendar_snapshot_dirty=True,
    )

    assert (
        state.calendar.draft_action_turn
        is True
    )

    assert (
        state.calendar.candidate_turn
        is False
    )

    assert (
        state.calendar.action_ok
        is True
    )

    assert (
        state.calendar.confirmation_executed
        is True
    )

    assert (
        state.calendar.candidate_saved
        is False
    )

    assert (
        state.calendar.snapshot_dirty
        is True
    )

    payload = str(
        working_memory_metadata_dict(
            state
        )
    )

    assert "SECRET EVENT" not in payload
    assert "PRIVATE" not in payload


def test_attachment_state_keeps_refs_only_and_deduplicates() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        attachment_rows=[
            {
                "id": "att-1",
                "filename": "private.pdf",
            },
            {
                "id": "att-1",
                "filename": "duplicate.pdf",
            },
            {
                "id": "att-2",
                "filename": "photo.jpg",
            },
        ],
    )

    assert (
        state.attachments.attachment_refs
        == (
            "att-1",
            "att-2",
        )
    )

    assert state.attachments.count == 2

    payload = str(
        working_memory_metadata_dict(
            state
        )
    )

    assert "private.pdf" not in payload
    assert "duplicate.pdf" not in payload
    assert "photo.jpg" not in payload


def test_context_state_is_metadata_only() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        life_context_keys=[
            "identity",
            "goals",
            "people",
        ],
        chronology_context_present=True,
        pending_calendar_context_present=False,
        latest_briefing_present=True,
        volatile_context_chars=3020,
    )

    assert (
        state.context.life_context_keys
        == (
            "identity",
            "goals",
            "people",
        )
    )

    assert (
        state.context.chronology_context_present
        is True
    )

    assert (
        state.context.latest_briefing_present
        is True
    )

    assert (
        state.context.volatile_context_chars
        == 3020
    )


def test_negative_counts_are_normalized() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
        history_message_count=-10,
        volatile_context_chars=-5,
        packed_memory_context=SimpleNamespace(
            dropped_memory_count=-2,
            dropped_summary_count=-3,
            total_chars=-100,
        ),
    )

    assert state.history.message_count == 0
    assert state.memory.dropped_memory_count == 0
    assert state.memory.dropped_summary_count == 0
    assert state.memory.packed_context_chars == 0
    assert state.context.volatile_context_chars == 0


def test_metadata_dict_has_stable_primitive_shape() -> None:
    state = build_working_memory_state(
        user_ref="user-1",
        conversation_ref="conv-1",
        turn_ref="msg-1",
        now=datetime(
            2026,
            9,
            1,
            4,
            30,
            tzinfo=timezone.utc,
        ),
    )

    payload = working_memory_metadata_dict(
        state
    )

    assert (
        payload["version"]
        == "M31C-v1"
    )

    assert (
        payload["created_at_utc"]
        == "2026-09-01T04:30:00Z"
    )

    assert (
        payload["turn"]["user_ref"]
        == "user-1"
    )


def test_builder_accepts_no_raw_user_message_or_prompt() -> None:
    signature = inspect.signature(
        build_working_memory_state
    )

    names = set(
        signature.parameters
    )

    forbidden = {
        "user_message",
        "prompt",
        "system_prompt",
        "volatile_context",
        "memory_content",
        "assistant_response",
    }

    assert not (
        names
        & forbidden
    )


def test_module_has_no_persistence_or_external_dependencies() -> None:
    source = Path(
        "app/services/working_memory.py"
    ).read_text()

    forbidden = [
        "get_supabase",
        ".table(",
        ".insert(",
        ".update(",
        ".upsert(",
        ".delete(",
        "redis",
        "httpx",
        "requests.",
        "anthropic",
        "get_claude",
        "embed_query",
        "embed_document",
    ]

    for token in forbidden:
        assert token not in source


def test_module_does_not_depend_on_chat_or_trace() -> None:
    source = Path(
        "app/services/working_memory.py"
    ).read_text()

    assert (
        "app.routers.chat"
        not in source
    )

    assert (
        "cognitive_trace"
        not in source
    )


def test_validation_rejects_unknown_retrieval_status() -> None:
    state = build_working_memory_state(
        user_ref=None,
        conversation_ref=None,
        turn_ref=None,
    )

    import dataclasses

    broken_memory = dataclasses.replace(
        state.memory,
        retrieval_status="magic",
    )

    broken = dataclasses.replace(
        state,
        memory=broken_memory,
    )

    with pytest.raises(
        ValueError,
        match="Invalid retrieval_status",
    ):
        validate_working_memory_state(
            broken
        )
