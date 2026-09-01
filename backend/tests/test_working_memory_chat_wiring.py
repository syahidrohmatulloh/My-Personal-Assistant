from pathlib import Path
from types import SimpleNamespace

from app.services import working_memory


CHAT_PATH = Path(
    "app/routers/chat.py"
)


def _chat_source() -> str:
    return CHAT_PATH.read_text()


def test_chat_imports_cognitive_runtime_service() -> None:
    source = _chat_source()

    assert (
        "    cognitive_runtime,"
        in source
    )

    assert (
        "    working_memory,"
        not in source
    )


def test_chat_builds_one_working_memory_snapshot() -> None:
    source = _chat_source()

    assert (
        source.count(
            "_working_memory_state = "
            "_cognitive_runtime.build_working_memory("
        )
        == 1
    )

    assert (
        "working_memory.build_working_memory_state("
        not in source
    )


def test_snapshot_is_built_after_packed_memory() -> None:
    source = _chat_source()

    pack_index = source.index(
        "packed_memory_context = "
        "chat_memory_assembly.pack_chat_memory_context("
    )

    snapshot_index = source.index(
        "_working_memory_state = "
        "_cognitive_runtime.build_working_memory("
    )

    assert snapshot_index > pack_index


def test_snapshot_is_built_after_final_first_message_metadata() -> None:
    source = _chat_source()

    first_message_index = source.index(
        "is_first_message = len(messages) <= 1"
    )

    snapshot_index = source.index(
        "_working_memory_state = "
        "_cognitive_runtime.build_working_memory("
    )

    assert snapshot_index > first_message_index


def test_snapshot_is_not_used_to_control_response() -> None:
    source = _chat_source()

    assignment = (
        "_working_memory_state = "
        "_cognitive_runtime.build_working_memory("
    )

    assert (
        source.count(
            assignment
        )
        == 1
    )

    assert (
        "working_memory_state="
        not in source
    )

    assert (
        "_working_memory_state,"
        not in source
    )

    assert (
        "_working_memory_state)"
        not in source
    )

    assert (
        "_working_memory_state."
        not in source
    )

    assert (
        "if _working_memory_state"
        not in source
    )

    assert (
        "volatile_context += "
        "working_memory"
        not in source
    )


def test_snapshot_builder_receives_metadata_not_raw_message() -> None:
    source = _chat_source()

    start = source.index(
        "_working_memory_state = "
        "_cognitive_runtime.build_working_memory("
    )

    end = source.index(
        "\n    )",
        start,
    )

    block = source[
        start:end
    ]

    assert "body.message" not in block
    assert "user_message=" not in block
    assert "volatile_context=" not in block

    assert (
        "volatile_context_chars=len("
        in block
    )

    assert (
        "attachment_rows=attachment_rows"
        in block
    )

    assert (
        "memory_assembly=memory_assembly"
        in block
    )

    assert (
        "packed_memory_context=packed_memory_context"
        in block
    )


def test_calendar_confirmation_is_initialized_for_all_paths() -> None:
    source = _chat_source()

    initialization = (
        "calendar_confirmation_result: "
        "dict[str, Any] | None = None"
    )

    assert initialization in source

    init_index = source.index(
        initialization
    )

    branch_index = source.index(
        "if not is_calendar_draft_action_turn:",
        init_index,
    )

    assert init_index < branch_index


def test_realistic_calendar_success_is_mirrored() -> None:
    state = working_memory.build_working_memory_state(
        user_ref="u1",
        conversation_ref="c1",
        turn_ref="m1",
        calendar_draft_action_turn=True,
        calendar_action_result={
            "attempted": True,
            "success": True,
            "updated": True,
        },
    )

    assert (
        state.calendar.action_ok
        is True
    )


def test_snapshot_remains_metadata_only() -> None:
    memory_assembly = SimpleNamespace(
        legacy_memories=[
            {
                "id": "mem-1",
                "content": "SECRET MEMORY",
            }
        ],
        related_summaries=[],
        memory_retrieval_diagnostics=(
            SimpleNamespace(
                attempted=True,
                gate_reason="default_allow",
                subsystem_status="healthy",
            )
        ),
    )

    packed = SimpleNamespace(
        memory_ids=(
            "mem-1",
        ),
        summary_ids=(),
        dropped_memory_count=0,
        dropped_summary_count=0,
        total_chars=100,
        intent="general",
        text="SECRET PACKED TEXT",
    )

    state = working_memory.build_working_memory_state(
        user_ref="u1",
        conversation_ref="c1",
        turn_ref="m1",
        memory_assembly=memory_assembly,
        packed_memory_context=packed,
        attachment_rows=[
            {
                "id": "att-1",
                "filename":
                    "SECRET_ATTACHMENT.pdf",
            }
        ],
    )

    payload = str(
        working_memory.working_memory_metadata_dict(
            state
        )
    )

    assert "SECRET MEMORY" not in payload
    assert "SECRET PACKED TEXT" not in payload
    assert "SECRET_ATTACHMENT.pdf" not in payload

    assert "mem-1" in payload
    assert "att-1" in payload
