import ast
from datetime import datetime, timezone
from pathlib import Path

from app.services import attention_salience
from app.services import cognitive_runtime
from app.services import cognitive_trace
from app.services import metacognitive_policy
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
            )
        ),
    )


def _attention_decision():
    return attention_salience.AttentionDecision(
        version=attention_salience.ATTENTION_SALIENCE_VERSION,
        level="high",
        candidates=(
            attention_salience.CandidateSalience(
                memory_ref="mem-1",
                score=0.78,
                tier="high",
                reason_codes=(
                    "attention.salience.category.core",
                    "attention.salience.tier.high",
                ),
            ),
        ),
        salient_memory_refs=(
            "mem-1",
        ),
        attended_memory_refs=(
            "mem-1",
        ),
        suppressed_memory_refs=(),
        reason_codes=(
            "attention.focus.selected",
            "attention.salience.level.high",
        ),
    )


def test_runtime_finalization_owns_m31g_attention_and_one_trace(
    monkeypatch,
) -> None:
    metacognitive = (
        metacognitive_policy
        .safe_default_decision()
    )
    attention = _attention_decision()

    monkeypatch.setattr(
        metacognitive_policy,
        "evaluate_metacognitive_policy",
        lambda **_kwargs: metacognitive,
    )

    monkeypatch.setattr(
        attention_salience,
        "evaluate_attention_salience",
        lambda **_kwargs: attention,
    )

    monkeypatch.setattr(
        attention_salience,
        "render_prompt_directive",
        lambda *_args, **_kwargs: "ATTENTION-DIRECTIVE",
    )

    trace_calls = []

    def fake_record(**kwargs):
        trace_calls.append(
            kwargs
        )
        return True

    monkeypatch.setattr(
        cognitive_trace,
        "record_chat_observation_fail_open",
        fake_record,
    )

    runtime = (
        cognitive_runtime
        .create_cognitive_runtime()
    )

    result = (
        runtime
        .finalize_metacognitive_turn(
            working_state=_state(),
            legacy_memories=[
                {
                    "id": "mem-1",
                    "category": "identity",
                    "content": "Private context",
                }
            ],
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
    )

    assert (
        result.attention_decision
        is attention
    )

    assert (
        result.attention_prompt_directive
        == "ATTENTION-DIRECTIVE"
    )

    assert (
        result.working_state
        .attention
        .level
        == "high"
    )

    assert (
        result.working_state
        .attention
        .attended_memory_refs
        == (
            "mem-1",
        )
    )

    assert result.trace_recorded is True
    assert len(trace_calls) == 1

    assert (
        trace_calls[0][
            "metacognitive_decision"
        ]
        is metacognitive
    )

    assert (
        trace_calls[0][
            "attention_decision"
        ]
        is attention
    )


def test_attention_failure_is_fail_open_and_does_not_block_trace(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        attention_salience,
        "evaluate_attention_salience",
        lambda **_kwargs: (
            _raise_runtime_error()
        ),
    )

    trace_calls = []

    monkeypatch.setattr(
        cognitive_trace,
        "record_chat_observation_fail_open",
        lambda **kwargs: (
            trace_calls.append(kwargs)
            or True
        ),
    )

    runtime = (
        cognitive_runtime
        .create_cognitive_runtime()
    )

    result = (
        runtime
        .finalize_metacognitive_turn(
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
    )

    assert (
        result.attention_decision.level
        == "normal"
    )

    assert (
        "attention.salience.fallback.safe_default"
        in result.attention_decision.reason_codes
    )

    assert (
        result.attention_prompt_directive
        is None
    )

    assert (
        result.working_state
        .attention
        .level
        == "normal"
    )

    assert len(trace_calls) == 1


def _raise_runtime_error():
    raise RuntimeError(
        "simulated M31G failure"
    )


def test_chat_keeps_attention_service_behind_runtime_facade() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "attention_salience"
        not in source
    )

    assert (
        "_metacognitive_finalization"
        ".attention_prompt_directive"
        in source
    )


def test_runtime_owns_attention_service_dependency() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "from app.services import attention_salience"
        in source
    )

    assert (
        "def evaluate_attention_salience("
        in source
    )


def test_trace_finalization_occurs_after_attention_evaluation() -> None:
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

    finalize = next(
        node
        for node in runtime.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name
        == "finalize_metacognitive_turn"
    )

    attention_calls = [
        node
        for node in ast.walk(
            finalize
        )
        if isinstance(
            node,
            ast.Call,
        )
        and isinstance(
            node.func,
            ast.Attribute,
        )
        and node.func.attr
        == "evaluate_attention_salience"
    ]

    trace_calls = [
        node
        for node in ast.walk(
            finalize
        )
        if isinstance(
            node,
            ast.Call,
        )
        and isinstance(
            node.func,
            ast.Attribute,
        )
        and node.func.attr
        == "record_chat_observation_fail_open"
    ]

    assert len(attention_calls) == 1
    assert len(trace_calls) == 1

    assert (
        attention_calls[0].lineno
        < trace_calls[0].lineno
    )
