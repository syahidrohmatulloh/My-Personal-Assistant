import logging
from pathlib import Path

from app.services import cognitive_runtime
from app.services import cognitive_trace
from app.services import working_memory


def test_runtime_version() -> None:
    assert (
        cognitive_runtime.COGNITIVE_RUNTIME_VERSION
        == "M31D-v1"
    )


def test_runtime_is_lightweight_facade() -> None:
    runtime = cognitive_runtime.create_cognitive_runtime()

    assert isinstance(
        runtime,
        cognitive_runtime.CognitiveRuntime,
    )

    assert runtime.version == "M31D-v1"


def test_default_runtime_uses_null_trace_sink() -> None:
    runtime = cognitive_runtime.create_cognitive_runtime()

    assert isinstance(
        runtime.trace_sink,
        cognitive_trace.NullTraceSink,
    )


def test_logging_runtime_uses_existing_logging_sink() -> None:
    runtime = cognitive_runtime.create_cognitive_runtime(
        trace_logging_enabled=True,
        trace_preview_policy="none",
    )

    assert isinstance(
        runtime.trace_sink,
        cognitive_trace.LoggingTraceSink,
    )

    assert (
        runtime.trace_sink.preview_policy
        == "none"
    )


def test_invalid_preview_policy_fails_safe() -> None:
    runtime = cognitive_runtime.create_cognitive_runtime(
        trace_logging_enabled=True,
        trace_preview_policy="unsafe",
    )

    assert isinstance(
        runtime.trace_sink,
        cognitive_trace.LoggingTraceSink,
    )

    assert (
        runtime.trace_sink.preview_policy
        == "none"
    )


def test_runtime_owns_working_memory_builder_boundary(
    monkeypatch,
) -> None:
    calls = []

    sentinel = object()

    def fake_builder(**kwargs):
        calls.append(
            kwargs
        )
        return sentinel

    monkeypatch.setattr(
        working_memory,
        "build_working_memory_state",
        fake_builder,
    )

    runtime = cognitive_runtime.create_cognitive_runtime()

    result = runtime.build_working_memory(
        user_ref="user-1",
        conversation_ref="conv-1",
        turn_ref="turn-1",
        history_message_count=5,
    )

    assert result is sentinel

    assert calls == [
        {
            "user_ref": "user-1",
            "conversation_ref": "conv-1",
            "turn_ref": "turn-1",
            "history_message_count": 5,
        }
    ]


def test_runtime_does_not_modify_working_memory_semantics() -> None:
    runtime = cognitive_runtime.create_cognitive_runtime()

    state = runtime.build_working_memory(
        user_ref="user-1",
        conversation_ref="conv-1",
        turn_ref="turn-1",
        assistant_mode="life_companion",
        companion_settings_row={
            "companion_mode": "friendly",
            "mood_realism": "stable",
        },
    )

    assert isinstance(
        state,
        working_memory.WorkingMemoryState,
    )

    assert (
        state.version
        == working_memory.WORKING_MEMORY_VERSION
    )

    assert state.turn.user_ref == "user-1"

    assert (
        state.mode.assistant_mode
        == "life_companion"
    )


def test_runtime_owns_trace_delegation_boundary(
    monkeypatch,
) -> None:
    calls = []

    logger = logging.getLogger(
        "tests.cognitive_runtime"
    )

    sink = cognitive_trace.TestTraceSink()

    def fake_record(**kwargs):
        calls.append(
            kwargs
        )
        return True

    monkeypatch.setattr(
        cognitive_trace,
        "record_chat_observation_fail_open",
        fake_record,
    )

    runtime = cognitive_runtime.CognitiveRuntime(
        trace_sink=sink,
        logger=logger,
    )

    result = runtime.record_chat_observation_fail_open(
        turn_ref="turn-1",
        conversation_ref="conv-1",
        user_ref="user-1",
        assistant_mode="life_companion",
        companion_settings_row={},
        comeback_affect_decision=None,
        packed_memory_context=None,
        memory_retrieval_diagnostics=None,
        legacy_memories=[],
    )

    assert result is True
    assert len(calls) == 1

    call = calls[0]

    assert call["sink"] is sink
    assert call["logger"] is logger

    assert call["turn_ref"] == "turn-1"
    assert call["conversation_ref"] == "conv-1"
    assert call["user_ref"] == "user-1"


def test_trace_failure_semantics_remain_fail_open(
    monkeypatch,
) -> None:
    sink = cognitive_trace.TestTraceSink()

    runtime = cognitive_runtime.CognitiveRuntime(
        trace_sink=sink,
    )

    def fake_record(**_kwargs):
        return False

    monkeypatch.setattr(
        cognitive_trace,
        "record_chat_observation_fail_open",
        fake_record,
    )

    assert (
        runtime.record_chat_observation_fail_open(
            turn_ref=None,
            conversation_ref=None,
            user_ref=None,
            assistant_mode=None,
            companion_settings_row=None,
            comeback_affect_decision=None,
            packed_memory_context=None,
        )
        is False
    )


def test_runtime_has_no_direct_db_or_provider_dependency() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
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
        "googleapiclient",
    ]

    for token in forbidden:
        assert token not in source


def test_runtime_does_not_implement_later_phase_logic() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text()

    forbidden = [
        "packing_score",
        "salience_score",
        "metacognitive",
        "habit",
        "consolidation",
        "dream_cycle",
    ]

    for token in forbidden:
        assert token not in source.lower()


def test_runtime_dependency_direction_is_one_way() -> None:
    service_dir = Path(
        "app/services"
    )

    violations = []

    for path in service_dir.glob(
        "*.py"
    ):
        if (
            path.name
            == "cognitive_runtime.py"
        ):
            continue

        source = path.read_text()

        if (
            "cognitive_runtime"
            in source
        ):
            violations.append(
                path.name
            )

    assert violations == []


def test_runtime_does_not_depend_on_chat_router() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text()

    assert "app.routers.chat" not in source
    assert "from app.routers" not in source


def test_chat_creates_one_runtime_per_turn() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    assert (
        source.count(
            "_cognitive_runtime = "
            "cognitive_runtime.create_cognitive_runtime("
        )
        == 1
    )

    assert (
        "trace_logging_enabled="
        "settings.COGNITIVE_TRACE_LOG"
        in source
    )

    assert (
        "trace_preview_policy="
        "settings.COGNITIVE_TRACE_PREVIEW_POLICY"
        in source
    )


def test_chat_delegates_trace_and_working_memory_to_runtime() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    assert (
        source.count(
            "_cognitive_runtime."
            "record_chat_observation_fail_open("
        )
        == 1
    )

    assert (
        source.count(
            "_cognitive_runtime."
            "build_working_memory("
        )
        == 1
    )

    assert (
        "cognitive_trace."
        "record_chat_observation_fail_open("
        not in source
    )

    assert (
        "working_memory."
        "build_working_memory_state("
        not in source
    )


def test_chat_imports_only_runtime_facade_for_m31_boundary() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    service_import_start = source.index(
        "from app.services import ("
    )

    service_import_end = source.index(
        ")\nfrom app.services.user_mood_prompt",
        service_import_start,
    )

    imports = source[
        service_import_start:service_import_end
    ]

    assert "cognitive_runtime," in imports
    assert "cognitive_trace," not in imports
    assert "working_memory," not in imports


def test_m31b_and_m31c_services_remain_authoritative() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text()

    assert (
        "working_memory.build_working_memory_state("
        in source
    )

    assert (
        "cognitive_trace.record_chat_observation_fail_open("
        in source
    )

    assert (
        "cognitive_trace.get_trace_sink("
        in source
    )


def test_runtime_owns_memory_packing_delegation_boundary(
    monkeypatch,
) -> None:
    from app.services import chat_memory_assembly

    calls = []

    sentinel = object()

    def fake_pack(**kwargs):
        calls.append(
            kwargs
        )
        return sentinel

    monkeypatch.setattr(
        chat_memory_assembly,
        "pack_chat_memory_context",
        fake_pack,
    )

    runtime = (
        cognitive_runtime.create_cognitive_runtime()
    )

    logger = logging.getLogger(
        "tests.cognitive_runtime.packing"
    )

    result = runtime.pack_chat_memory_context(
        legacy_memories=[
            {
                "id": "mem-1",
            }
        ],
        related_summaries=[
            {
                "id": "sum-1",
            }
        ],
        query_text="hello",
        user_id="user-1",
        logger=logger,
    )

    assert result is sentinel

    assert len(calls) == 1

    assert calls[0] == {
        "legacy_memories": [
            {
                "id": "mem-1",
            }
        ],
        "related_summaries": [
            {
                "id": "sum-1",
            }
        ],
        "query_text": "hello",
        "user_id": "user-1",
        "logger": logger,
    }


def test_chat_delegates_memory_packing_to_runtime() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    assert (
        source.count(
            "_cognitive_runtime."
            "pack_chat_memory_context("
        )
        == 1
    )

    assert (
        "chat_memory_assembly."
        "pack_chat_memory_context("
        not in source
    )




def test_runtime_packing_keeps_authoritative_service() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text()

    assert (
        "chat_memory_assembly."
        "pack_chat_memory_context("
        in source
    )

    assert "pack_memory_context_for_prompt(" not in source
    assert "_packing_score(" not in source
    assert "_query_intent(" not in source



def test_runtime_owns_memory_retrieval_delegation_boundary(
    monkeypatch,
) -> None:
    import asyncio

    from app.services import chat_memory_assembly

    calls = []

    sentinel = object()

    async def fake_retrieve(**kwargs):
        calls.append(
            kwargs
        )
        return sentinel

    monkeypatch.setattr(
        chat_memory_assembly,
        "retrieve_chat_memory_assembly",
        fake_retrieve,
    )

    runtime = (
        cognitive_runtime.create_cognitive_runtime()
    )

    result = asyncio.run(
        runtime.retrieve_chat_memory_assembly(
            user_id="user-1",
            query_text="hello",
            conversation_id="conv-1",
            memory_limit=9,
            summary_limit=4,
        )
    )

    assert result is sentinel

    assert calls == [
        {
            "user_id": "user-1",
            "query_text": "hello",
            "conversation_id": "conv-1",
            "memory_limit": 9,
            "summary_limit": 4,
        }
    ]


def test_chat_delegates_memory_retrieval_to_runtime() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    assert (
        source.count(
            "_cognitive_runtime."
            "retrieve_chat_memory_assembly("
        )
        == 1
    )

    assert (
        "chat_memory_assembly."
        "retrieve_chat_memory_assembly("
        not in source
    )



def test_chat_no_longer_imports_chat_memory_assembly() -> None:
    source = Path(
        "app/routers/chat.py"
    ).read_text()

    service_import_start = source.index(
        "from app.services import ("
    )

    service_import_end = source.index(
        "from app.services.user_mood_prompt",
        service_import_start,
    )

    imports = source[
        service_import_start:
        service_import_end
    ]

    assert "chat_memory_assembly," not in imports


def test_runtime_retrieval_keeps_authoritative_service() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text()

    assert (
        "chat_memory_assembly."
        "retrieve_chat_memory_assembly("
        in source
    )

    assert "memory.retrieve_relevant(" not in source

    assert (
        "conversation_summary."
        "retrieve_related_summaries("
        not in source
    )

    assert "embed_query(" not in source
    assert "rank_memory_rows(" not in source
