import ast
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
    tree = ast.parse(source)

    chat_fn = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name == "chat"
    )

    packed_assignments = []

    snapshot_calls = []

    for node in ast.walk(
        chat_fn
    ):
        if isinstance(
            node,
            ast.Assign,
        ):
            if (
                len(node.targets) == 1
                and isinstance(
                    node.targets[0],
                    ast.Name,
                )
                and node.targets[0].id
                == "packed_memory_context"
                and isinstance(
                    node.value,
                    ast.Attribute,
                )
                and node.value.attr
                == "packed_memory_context"
                and isinstance(
                    node.value.value,
                    ast.Name,
                )
                and node.value.value.id
                == "generation_context"
            ):
                packed_assignments.append(
                    node
                )

        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if (
            isinstance(
                func,
                ast.Attribute,
            )
            and func.attr
            == "build_working_memory"
            and isinstance(
                func.value,
                ast.Name,
            )
            and func.value.id
            == "_cognitive_runtime"
        ):
            snapshot_calls.append(
                node
            )

    assert len(
        packed_assignments
    ) == 1

    assert len(
        snapshot_calls
    ) == 1

    packed_assignment = (
        packed_assignments[0]
    )

    snapshot_call = snapshot_calls[0]

    # The packed result prepared by CognitiveRuntime is materialized
    # before the WorkingMemory snapshot is built.
    assert (
        packed_assignment.lineno
        < snapshot_call.lineno
    )

    packed_keyword = next(
        keyword
        for keyword in snapshot_call.keywords
        if keyword.arg
        == "packed_memory_context"
    )

    assert isinstance(
        packed_keyword.value,
        ast.Name,
    )

    assert (
        packed_keyword.value.id
        == "packed_memory_context"
    )

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


def test_snapshot_is_used_only_through_m31f_runtime_boundary() -> None:
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
        source.count(
            "_cognitive_runtime.finalize_metacognitive_turn("
        )
        == 1
    )

    finalization_start = source.index(
        "_metacognitive_finalization = ("
    )

    finalization_end = source.index(
        "\n    )",
        finalization_start,
    )

    finalization_block = source[
        finalization_start:finalization_end
    ]

    assert (
        "working_state=_working_memory_state"
        in finalization_block
    )

    assert (
        "_working_memory_state."
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
    orchestration_source = Path(
        "app/services/"
        "cognitive_calendar_orchestration.py"
    ).read_text()

    tree = ast.parse(
        orchestration_source
    )

    execute_fn = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name
        == "execute_calendar_turn"
    )

    initializations = []

    confirmation_branches = []

    for node in ast.walk(
        execute_fn
    ):
        if (
            isinstance(
                node,
                ast.AnnAssign,
            )
            and isinstance(
                node.target,
                ast.Name,
            )
            and node.target.id
            == "calendar_confirmation_result"
            and isinstance(
                node.value,
                ast.Constant,
            )
            and node.value.value is None
        ):
            initializations.append(
                node
            )

        if not isinstance(
            node,
            ast.If,
        ):
            continue

        test = node.test

        if (
            isinstance(
                test,
                ast.UnaryOp,
            )
            and isinstance(
                test.op,
                ast.Not,
            )
            and isinstance(
                test.operand,
                ast.Name,
            )
            and test.operand.id
            == "is_calendar_draft_action_turn"
        ):
            confirmation_branches.append(
                node
            )

    assert len(
        initializations
    ) == 1

    assert len(
        confirmation_branches
    ) >= 1

    initialization = (
        initializations[0]
    )

    first_confirmation_branch = min(
        confirmation_branches,
        key=lambda node: node.lineno,
    )

    assert (
        initialization.lineno
        < first_confirmation_branch.lineno
    )

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
