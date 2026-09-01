import ast
from datetime import datetime, timezone
from pathlib import Path

from app.services import cognitive_runtime
from app.services import cognitive_trace
from app.services import metacognitive_policy
from app.services import working_memory


def _state() -> working_memory.WorkingMemoryState:
    return working_memory.WorkingMemoryState(
        version=working_memory.WORKING_MEMORY_VERSION,
        created_at_utc=datetime.now(timezone.utc),
    )


def _runtime_method(
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(
        Path(
            "app/services/cognitive_runtime.py"
        ).read_text(
            encoding="utf-8"
        )
    )

    runtime = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "CognitiveRuntime"
    )

    return next(
        node
        for node in runtime.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == name
    )


def _owner_call_count(
    node: ast.AST,
    owner: str,
    attr: str,
) -> int:
    count = 0

    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue

        func = child.func

        if (
            isinstance(func, ast.Attribute)
            and func.attr == attr
            and isinstance(func.value, ast.Name)
            and func.value.id == owner
        ):
            count += 1

    return count


def test_runtime_finalization_owns_policy_and_trace(
    monkeypatch,
) -> None:
    decision = metacognitive_policy.safe_default_decision()
    calls = []

    monkeypatch.setattr(
        metacognitive_policy,
        "evaluate_metacognitive_policy",
        lambda **_kwargs: decision,
    )

    def fake_record(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(
        cognitive_trace,
        "record_chat_observation_fail_open",
        fake_record,
    )

    runtime = cognitive_runtime.create_cognitive_runtime()

    result = runtime.finalize_metacognitive_turn(
        working_state=_state(),
        legacy_memories=[],
        user_message="hello",
        recent_messages=[],
        turn_ref="turn-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=None,
        memory_retrieval_diagnostics=None,
    )

    assert result.decision is decision
    assert result.prompt_directive is None
    assert result.trace_recorded is True
    assert len(calls) == 1
    assert (
        calls[0]["metacognitive_decision"]
        is decision
    )


def test_runtime_policy_failure_is_fail_open(
    monkeypatch,
) -> None:
    def fail(**_kwargs):
        raise RuntimeError("simulated policy failure")

    monkeypatch.setattr(
        metacognitive_policy,
        "evaluate_metacognitive_policy",
        fail,
    )

    monkeypatch.setattr(
        cognitive_trace,
        "record_chat_observation_fail_open",
        lambda **_kwargs: True,
    )

    runtime = cognitive_runtime.create_cognitive_runtime()

    result = runtime.finalize_metacognitive_turn(
        working_state=_state(),
        legacy_memories=[],
        user_message="hello",
        recent_messages=[],
        turn_ref=None,
        conversation_ref=None,
        user_ref=None,
        assistant_mode=None,
        companion_settings_row=None,
        comeback_affect_decision=None,
        packed_memory_context=None,
        memory_retrieval_diagnostics=None,
    )

    assert result.decision.response_posture == "proceed"
    assert (
        "metacognition.fallback.safe_default"
        in result.decision.reason_codes
    )


def test_prepare_context_defers_trace_until_metacognition() -> None:
    prepare = _runtime_method(
        "prepare_generation_context"
    )

    finalize = _runtime_method(
        "finalize_metacognitive_turn"
    )

    assert (
        _owner_call_count(
            prepare,
            "self",
            "record_chat_observation_fail_open",
        )
        == 0
    )

    assert (
        _owner_call_count(
            finalize,
            "self",
            "record_chat_observation_fail_open",
        )
        == 1
    )


def test_chat_wires_working_memory_into_metacognitive_finalization() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    snapshot_index = source.index(
        "_working_memory_state = "
        "_cognitive_runtime.build_working_memory("
    )

    finalization_index = source.index(
        "_metacognitive_finalization = ("
    )

    stream_index = source.index(
        "return StreamingResponse(",
        finalization_index,
    )

    assert snapshot_index < finalization_index < stream_index

    block_end = source.index(
        "\n    )",
        finalization_index,
    )

    block = source[
        finalization_index:block_end
    ]

    assert (
        "working_state=_working_memory_state"
        in block
    )

    assert (
        "user_message=body.message"
        in block
    )


def test_chat_uses_policy_for_prompt_and_inference_projection() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "_metacognitive_finalization.prompt_directive"
        in source
    )

    assert (
        "metacognitive_projection_posture="
        in source
    )

    assert (
        "metacognitive_allow_background_inference="
        in source
    )

    assert (
        "projection_posture=("
        in source
    )

    assert (
        "metacognitive_projection_posture"
        in source
    )

    assert (
        "metacognitive_allow_background_inference"
        in source
    )


def test_chat_keeps_metacognitive_service_behind_runtime_facade() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "metacognitive_policy"
        not in source
    )
