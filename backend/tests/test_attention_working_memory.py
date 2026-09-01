from datetime import datetime, timezone

import pytest

from app.services import working_memory


def _state() -> working_memory.WorkingMemoryState:
    return working_memory.WorkingMemoryState(
        version=working_memory.WORKING_MEMORY_VERSION,
        created_at_utc=datetime(
            2026,
            9,
            1,
            8,
            0,
            tzinfo=timezone.utc,
        ),
        memory=working_memory.MemoryWorkingState(
            selected_memory_refs=(
                "mem-1",
                "mem-2",
            )
        ),
    )


def test_default_attention_slice_is_normal_and_empty() -> None:
    state = _state()

    assert (
        state.attention.level
        == "normal"
    )
    assert (
        state.attention.salient_memory_refs
        == ()
    )
    assert (
        state.attention.attended_memory_refs
        == ()
    )
    assert (
        state.attention.suppressed_memory_refs
        == ()
    )


def test_attention_enrichment_returns_new_immutable_working_state() -> None:
    state = _state()

    enriched = (
        working_memory
        .with_attention_state(
            state,
            level="high",
            salient_memory_refs=(
                "mem-1",
                "mem-2",
            ),
            attended_memory_refs=(
                "mem-1",
            ),
            suppressed_memory_refs=(
                "mem-2",
            ),
        )
    )

    assert enriched is not state

    assert (
        state.attention.level
        == "normal"
    )

    assert (
        enriched.attention.level
        == "high"
    )

    assert (
        enriched.attention.attended_memory_refs
        == (
            "mem-1",
        )
    )

    assert (
        enriched.attention.suppressed_memory_refs
        == (
            "mem-2",
        )
    )


def test_attention_refs_must_be_selected_memory_refs() -> None:
    state = _state()

    with pytest.raises(
        ValueError,
        match="selected memory refs",
    ):
        working_memory.with_attention_state(
            state,
            level="high",
            salient_memory_refs=(
                "not-selected",
            ),
            attended_memory_refs=(),
            suppressed_memory_refs=(),
        )


def test_attended_and_suppressed_refs_must_be_salient() -> None:
    state = _state()

    with pytest.raises(
        ValueError,
        match="salient memory refs",
    ):
        working_memory.with_attention_state(
            state,
            level="elevated",
            salient_memory_refs=(
                "mem-1",
            ),
            attended_memory_refs=(
                "mem-2",
            ),
            suppressed_memory_refs=(),
        )


def test_attended_and_suppressed_refs_must_be_disjoint() -> None:
    state = _state()

    with pytest.raises(
        ValueError,
        match="disjoint",
    ):
        working_memory.with_attention_state(
            state,
            level="high",
            salient_memory_refs=(
                "mem-1",
            ),
            attended_memory_refs=(
                "mem-1",
            ),
            suppressed_memory_refs=(
                "mem-1",
            ),
        )


def test_invalid_attention_level_is_rejected() -> None:
    state = _state()

    with pytest.raises(
        ValueError,
        match="Invalid attention level",
    ):
        working_memory.with_attention_state(
            state,
            level="critical",
            salient_memory_refs=(),
            attended_memory_refs=(),
            suppressed_memory_refs=(),
        )


def test_attention_metadata_contains_refs_not_memory_content() -> None:
    state = working_memory.build_working_memory_state(
        user_ref="user-1",
        conversation_ref="conv-1",
        turn_ref="turn-1",
        memory_assembly=type(
            "Assembly",
            (),
            {
                "legacy_memories": [
                    {
                        "id": "mem-1",
                        "content": "PRIVATE MEMORY CONTENT",
                    }
                ],
                "related_summaries": [],
                "memory_retrieval_diagnostics": None,
            },
        )(),
        packed_memory_context=type(
            "Packed",
            (),
            {
                "memory_ids": (
                    "mem-1",
                ),
                "summary_ids": (),
                "dropped_memory_count": 0,
                "dropped_summary_count": 0,
                "intent": "general",
                "total_chars": 42,
            },
        )(),
    )

    enriched = (
        working_memory
        .with_attention_state(
            state,
            level="high",
            salient_memory_refs=(
                "mem-1",
            ),
            attended_memory_refs=(
                "mem-1",
            ),
            suppressed_memory_refs=(),
        )
    )

    payload = str(
        working_memory
        .working_memory_metadata_dict(
            enriched
        )
    )

    assert (
        "PRIVATE MEMORY CONTENT"
        not in payload
    )
    assert "mem-1" in payload


def test_memory_slice_still_has_no_salience_score_axis() -> None:
    names = set(
        working_memory.MemoryWorkingState
        .__dataclass_fields__
    )

    assert "salience_score" not in names
    assert "packing_score" not in names
