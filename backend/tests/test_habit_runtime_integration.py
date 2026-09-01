from __future__ import annotations

import ast
import asyncio
from pathlib import Path

from app.services import cognitive_runtime
from app.services import habit_learning


def _runtime_method(name: str):
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
        if isinstance(
            node,
            ast.ClassDef,
        )
        and node.name
        == "CognitiveRuntime"
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


def _owner_calls(
    node: ast.AST,
    owner: str,
    attr: str,
):
    return [
        child
        for child in ast.walk(
            node
        )
        if isinstance(
            child,
            ast.Call,
        )
        and isinstance(
            child.func,
            ast.Attribute,
        )
        and child.func.attr == attr
        and isinstance(
            child.func.value,
            ast.Name,
        )
        and child.func.value.id == owner
    ]


def test_runtime_version_remains_m31d_v1() -> None:
    assert (
        cognitive_runtime
        .COGNITIVE_RUNTIME_VERSION
        == "M31D-v1"
    )


def test_runtime_owns_habit_signal_boundary(
    monkeypatch,
) -> None:
    calls = []

    monkeypatch.setattr(
        habit_learning,
        "classify_habit_signal",
        lambda message: (
            calls.append(message)
            or "occurrence"
        ),
    )

    runtime = (
        cognitive_runtime
        .create_cognitive_runtime()
    )

    result = (
        runtime.classify_habit_signal(
            "Aku habis gym"
        )
    )

    assert result == "occurrence"
    assert calls == [
        "Aku habis gym"
    ]


def test_runtime_owns_habit_learning_operation(
    monkeypatch,
) -> None:
    calls = []
    sentinel = object()

    async def fake_learn(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(
        habit_learning,
        "learn_from_chat",
        fake_learn,
    )

    runtime = (
        cognitive_runtime
        .create_cognitive_runtime()
    )

    result = asyncio.run(
        runtime.learn_habits_from_chat(
            user_id="user-1",
            conversation_id="conv-1",
            user_message="Aku habis gym",
        )
    )

    assert result is sentinel
    assert calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conv-1",
            "user_message": "Aku habis gym",
        }
    ]


def test_chat_keeps_habit_service_behind_runtime_facade() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "from app.services import habit_learning"
        not in source
    )
    assert "habit_learning." not in source
    assert (
        "_cognitive_runtime.learn_habits_from_chat"
        in source
    )
    assert (
        "_cognitive_runtime.learn_habits_from_chat"
        in source
    )


def test_chat_gates_inferred_occurrence_learning_with_m31f() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'habit_signal == "occurrence"'
        in source
    )
    assert (
        "metacognitive_allow_background_inference"
        in source
    )


def test_explicit_habit_correction_bypasses_inference_hold() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'habit_signal == "explicit_correction"'
        in source
    )

    correction_index = source.index(
        'habit_signal == "explicit_correction"'
    )
    occurrence_index = source.index(
        'habit_signal == "occurrence"'
    )
    inference_gate_index = source.rfind(
        "metacognitive_allow_background_inference",
        correction_index,
        occurrence_index,
    )

    # The explicit-correction branch appears before the inference-gated
    # occurrence branch in the boolean expression.
    assert correction_index < occurrence_index
    assert inference_gate_index != -1


def test_chat_schedules_one_habit_background_operation() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        source.count(
            "_cognitive_runtime.learn_habits_from_chat"
        )
        == 1
    )


def test_runtime_does_not_embed_or_touch_database_for_habit_logic() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text(
        encoding="utf-8"
    )

    for token in (
        "get_supabase",
        "embed_document",
        ".table(",
    ):
        assert token not in source


def test_habit_service_never_imports_cognitive_runtime() -> None:
    source = Path(
        "app/services/habit_learning.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "cognitive_runtime" not in source


def test_m32_does_not_add_second_cognitive_trace() -> None:
    source = Path(
        "app/services/habit_learning.py"
    ).read_text(
        encoding="utf-8"
    )

    # Docstrings may name CognitiveDecisionTrace while documenting the
    # invariant. Only executable cognitive-trace dependencies are forbidden.
    assert "from app.services import cognitive_trace" not in source
    assert "from app.services.cognitive_trace import" not in source
    assert "cognitive_trace." not in source
    assert "record_chat_observation" not in source
    assert "cognitive_trace" not in source


def test_runtime_methods_delegate_only() -> None:
    classify = _runtime_method(
        "classify_habit_signal"
    )
    learn = _runtime_method(
        "learn_habits_from_chat"
    )

    assert len(
        _owner_calls(
            classify,
            "habit_learning",
            "classify_habit_signal",
        )
    ) == 1

    assert len(
        _owner_calls(
            learn,
            "habit_learning",
            "learn_from_chat",
        )
    ) == 1
