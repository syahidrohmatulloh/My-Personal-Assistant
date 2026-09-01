import ast
import logging
from pathlib import Path

from app.services import cognitive_runtime
from app.services import cognitive_trace
from app.services import working_memory



def _m31e_parse(path: str) -> ast.Module:
    return ast.parse(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def _m31e_top_level_function(
    tree: ast.Module,
    name: str,
):
    matches = [
        node
        for node in tree.body
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == name
    ]

    assert len(matches) == 1

    return matches[0]


def _m31e_runtime_method(
    tree: ast.Module,
    name: str,
):
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

    matches = [
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
    ]

    assert len(matches) == 1

    return matches[0]


def _m31e_owner_call_count(
    node: ast.AST,
    owner: str,
    attr: str,
) -> int:
    count = 0

    for child in ast.walk(node):
        if not isinstance(
            child,
            ast.Call,
        ):
            continue

        func = child.func

        if (
            isinstance(
                func,
                ast.Attribute,
            )
            and func.attr == attr
            and isinstance(
                func.value,
                ast.Name,
            )
            and func.value.id == owner
        ):
            count += 1

    return count


def _m31e_service_import_names(
    tree: ast.Module,
) -> set[str]:
    names: set[str] = set()

    for node in tree.body:
        if not isinstance(
            node,
            ast.ImportFrom,
        ):
            continue

        if node.module != "app.services":
            continue

        names.update(
            alias.name
            for alias in node.names
        )

    return names


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
    chat_tree = _m31e_parse(
        "app/routers/chat.py"
    )

    runtime_tree = _m31e_parse(
        "app/services/cognitive_runtime.py"
    )

    chat = _m31e_top_level_function(
        chat_tree,
        "chat",
    )

    prepare = _m31e_runtime_method(
        runtime_tree,
        "prepare_generation_context",
    )

    finalize = _m31e_runtime_method(
        runtime_tree,
        "finalize_metacognitive_turn",
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "_cognitive_runtime",
            "build_working_memory",
        )
        == 1
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "_cognitive_runtime",
            "finalize_metacognitive_turn",
        )
        == 1
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "_cognitive_runtime",
            "record_chat_observation_fail_open",
        )
        == 0
    )

    assert (
        _m31e_owner_call_count(
            prepare,
            "self",
            "record_chat_observation_fail_open",
        )
        == 0
    )

    assert (
        _m31e_owner_call_count(
            finalize,
            "self",
            "record_chat_observation_fail_open",
        )
        == 1
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "cognitive_trace",
            "record_chat_observation_fail_open",
        )
        == 0
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "working_memory",
            "build_working_memory_state",
        )
        == 0
    )


def test_chat_imports_only_runtime_facade_for_m31_boundary() -> None:
    chat_tree = _m31e_parse(
        "app/routers/chat.py"
    )

    imports = (
        _m31e_service_import_names(
            chat_tree
        )
    )

    assert "cognitive_runtime" in imports
    assert "cognitive_trace" not in imports
    assert "working_memory" not in imports

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
    chat_tree = _m31e_parse(
        "app/routers/chat.py"
    )

    runtime_tree = _m31e_parse(
        "app/services/cognitive_runtime.py"
    )

    chat = _m31e_top_level_function(
        chat_tree,
        "chat",
    )

    prepare = _m31e_runtime_method(
        runtime_tree,
        "prepare_generation_context",
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "_cognitive_runtime",
            "pack_chat_memory_context",
        )
        == 0
    )

    assert (
        _m31e_owner_call_count(
            prepare,
            "self",
            "pack_chat_memory_context",
        )
        == 1
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "chat_memory_assembly",
            "pack_chat_memory_context",
        )
        == 0
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
    chat_tree = _m31e_parse(
        "app/routers/chat.py"
    )

    runtime_tree = _m31e_parse(
        "app/services/cognitive_runtime.py"
    )

    chat = _m31e_top_level_function(
        chat_tree,
        "chat",
    )

    source_fan_in = (
        _m31e_runtime_method(
            runtime_tree,
            "retrieve_turn_context_sources",
        )
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "_cognitive_runtime",
            "retrieve_chat_memory_assembly",
        )
        == 0
    )

    assert (
        _m31e_owner_call_count(
            source_fan_in,
            "self",
            "retrieve_chat_memory_assembly",
        )
        == 1
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "chat_memory_assembly",
            "retrieve_chat_memory_assembly",
        )
        == 0
    )


def test_chat_no_longer_imports_chat_memory_assembly() -> None:
    chat_tree = _m31e_parse(
        "app/routers/chat.py"
    )

    imports = (
        _m31e_service_import_names(
            chat_tree
        )
    )

    assert (
        "chat_memory_assembly"
        not in imports
    )

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


def test_runtime_owns_life_context_retrieval_boundary(
    monkeypatch,
) -> None:
    import asyncio

    from app.services import life_model

    calls = []

    async def fake_get_context(
        user_id,
        mood_days=14,
    ):
        calls.append(
            {
                "user_id": user_id,
                "mood_days": mood_days,
            }
        )

        return {
            "identity": {
                "profile": {
                    "name": "Test",
                }
            }
        }

    monkeypatch.setattr(
        life_model,
        "get_context",
        fake_get_context,
    )

    runtime = (
        cognitive_runtime.create_cognitive_runtime()
    )

    result = asyncio.run(
        runtime.retrieve_life_context(
            user_id="user-123456",
            mood_days=21,
        )
    )

    assert result == {
        "identity": {
            "profile": {
                "name": "Test",
            }
        }
    }

    assert calls == [
        {
            "user_id": "user-123456",
            "mood_days": 21,
        }
    ]


def test_runtime_life_context_preserves_fail_open_semantics(
    monkeypatch,
    caplog,
) -> None:
    import asyncio

    from app.services import life_model

    async def fake_get_context(
        _user_id,
        mood_days=14,
    ):
        del mood_days
        raise RuntimeError(
            "simulated life-context failure"
        )

    monkeypatch.setattr(
        life_model,
        "get_context",
        fake_get_context,
    )

    logger = logging.getLogger(
        "tests.cognitive_runtime.life_context"
    )

    runtime = (
        cognitive_runtime.create_cognitive_runtime(
            logger=logger,
        )
    )

    with caplog.at_level(
        logging.WARNING,
        logger=logger.name,
    ):
        result = asyncio.run(
            runtime.retrieve_life_context(
                user_id="user-123456",
            )
        )

    assert result == {}

    assert (
        "life_model.get_context failed "
        "user=user-123"
        in caplog.text
    )


def test_runtime_life_context_rejects_non_dict_result(
    monkeypatch,
) -> None:
    import asyncio

    from app.services import life_model

    async def fake_get_context(
        _user_id,
        mood_days=14,
    ):
        del mood_days
        return [
            "invalid-context-shape",
        ]

    monkeypatch.setattr(
        life_model,
        "get_context",
        fake_get_context,
    )

    runtime = (
        cognitive_runtime.create_cognitive_runtime()
    )

    result = asyncio.run(
        runtime.retrieve_life_context(
            user_id="user-1",
        )
    )

    assert result == {}



def test_chat_delegates_life_context_to_runtime() -> None:
    chat_source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    chat_tree = ast.parse(
        chat_source
    )

    runtime_tree = _m31e_parse(
        "app/services/cognitive_runtime.py"
    )

    chat = _m31e_top_level_function(
        chat_tree,
        "chat",
    )

    source_fan_in = (
        _m31e_runtime_method(
            runtime_tree,
            "retrieve_turn_context_sources",
        )
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "_cognitive_runtime",
            "retrieve_life_context",
        )
        == 0
    )

    assert (
        _m31e_owner_call_count(
            source_fan_in,
            "self",
            "retrieve_life_context",
        )
        == 1
    )

    assert (
        "_safe_life_model_context("
        not in chat_source
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "life_model",
            "get_context",
        )
        == 0
    )

    imports = (
        _m31e_service_import_names(
            chat_tree
        )
    )

    assert "life_model" not in imports

def test_runtime_life_context_keeps_authoritative_service() -> None:
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text()

    assert (
        "life_model.get_context("
        in source
    )

    assert "get_user_context" not in source
    assert ".rpc(" not in source
    assert ".table(" not in source


def test_runtime_owns_conversation_chronology_context_boundary(
    monkeypatch,
) -> None:
    import asyncio

    from app.services import conversation_chronology

    calls = []

    async def fake_build_context_if_relevant(
        *,
        user_id,
        query_text,
    ):
        calls.append(
            {
                "user_id": user_id,
                "query_text": query_text,
            }
        )

        return "CHRONOLOGY SENTINEL"

    monkeypatch.setattr(
        conversation_chronology,
        "build_context_if_relevant",
        fake_build_context_if_relevant,
    )

    runtime = (
        cognitive_runtime.create_cognitive_runtime()
    )

    result = asyncio.run(
        runtime.retrieve_conversation_chronology_context(
            user_id="user-123",
            query_text="when did we first chat?",
        )
    )

    assert result == "CHRONOLOGY SENTINEL"

    assert calls == [
        {
            "user_id": "user-123",
            "query_text": "when did we first chat?",
        }
    ]



def test_chat_delegates_conversation_chronology_to_runtime() -> None:
    chat_tree = _m31e_parse(
        "app/routers/chat.py"
    )

    chat = _m31e_top_level_function(
        chat_tree,
        "chat",
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "_cognitive_runtime",
            "retrieve_conversation_chronology_context",
        )
        == 1
    )

    assert (
        _m31e_owner_call_count(
            chat,
            "conversation_chronology",
            "build_context_if_relevant",
        )
        == 0
    )

    imports = (
        _m31e_service_import_names(
            chat_tree
        )
    )

    assert (
        "conversation_chronology"
        not in imports
    )

def test_runtime_chronology_keeps_authoritative_service() -> None:
    import ast

    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text()

    tree = ast.parse(source)

    runtime_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "CognitiveRuntime"
    )

    method = next(
        node
        for node in runtime_class.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name
        == "retrieve_conversation_chronology_context"
    )

    delegate_calls = []

    forbidden_calls = []

    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        if (
            isinstance(func, ast.Attribute)
            and func.attr
            == "build_context_if_relevant"
            and isinstance(func.value, ast.Name)
            and func.value.id
            == "conversation_chronology"
        ):
            delegate_calls.append(node)

        if (
            isinstance(func, ast.Attribute)
            and func.attr
            in {
                "get_conversation_chronology",
                "render_chronology_context",
                "table",
                "rpc",
            }
        ):
            forbidden_calls.append(
                func.attr
            )

    assert len(delegate_calls) == 1

    assert forbidden_calls == []
