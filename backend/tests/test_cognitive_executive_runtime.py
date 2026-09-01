import ast
from pathlib import Path


CHAT_PATH = Path(
    "app/routers/chat.py"
)

RUNTIME_PATH = Path(
    "app/services/cognitive_runtime.py"
)

CONTEXT_PATH = Path(
    "app/services/cognitive_turn_context.py"
)

CALENDAR_PATH = Path(
    "app/services/"
    "cognitive_calendar_orchestration.py"
)


def _function(
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


def _runtime_method(
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


def _owner_calls(
    node: ast.AST,
    owner: str,
):
    calls = []

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
            and isinstance(
                func.value,
                ast.Name,
            )
            and func.value.id
            == owner
        ):
            calls.append(
                func.attr
            )

    return calls


def test_chat_delegates_major_m31e_boundaries_to_runtime():
    source = CHAT_PATH.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    chat = _function(
        tree,
        "chat",
    )

    calls = _owner_calls(
        chat,
        "_cognitive_runtime",
    )

    required = {
        "retrieve_turn_context_sources",
        "execute_assistant_mode_command",
        "retrieve_conversation_chronology_context",
        "evaluate_comeback_affect",
        "execute_calendar_turn",
        "prepare_generation_context",
        "build_working_memory",
    }

    assert required.issubset(
        set(calls)
    )


def test_chat_no_longer_owns_giant_prompt_assembly():
    source = CHAT_PATH.read_text(
        encoding="utf-8"
    )

    forbidden = [
        "Memory response style policy:",
        "Calendar scheduling contract "
        "for this user turn",
        "## Time-of-day grounding — "
        "strict rule",
        "FINAL RESPONSE STYLE OVERRIDE "
        "— CHIEF OF STAFF MODE",
        "interaction_preferences."
        "get_interaction_preferences_block(",
        "render_profile_runtime_context(",
        "response_texture."
        "render_response_texture_block(",
    ]

    for token in forbidden:
        assert token not in source


def test_chat_foreground_has_no_direct_calendar_execution_calls():
    source = CHAT_PATH.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    chat = _function(
        tree,
        "chat",
    )

    forbidden_owners = {
        "calendar_candidate_extractor",
        "calendar_confirmation_actions",
        "calendar_draft_actions",
        "chat_calendar_helpers",
    }

    violations = []

    for owner in forbidden_owners:
        for call in _owner_calls(
            chat,
            owner,
        ):
            violations.append(
                (
                    owner,
                    call,
                )
            )

    assert violations == []



def test_calendar_orchestrator_keeps_existing_services_authoritative():
    source = CALENDAR_PATH.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    draft_calls = _owner_calls(
        tree,
        "calendar_draft_actions",
    )

    confirmation_calls = _owner_calls(
        tree,
        "calendar_confirmation_actions",
    )

    candidate_calls = _owner_calls(
        tree,
        "calendar_candidate_extractor",
    )

    assert (
        "apply_chat_calendar_draft_action"
        in draft_calls
    )

    assert (
        "apply_calendar_confirmation_decision"
        in confirmation_calls
    )

    assert (
        "extract_and_persist"
        in candidate_calls
    )

    assert ".table(" not in source
    assert ".rpc(" not in source
    assert "get_supabase" not in source

def test_context_assembly_owns_prompt_and_model_input_preparation():
    source = CONTEXT_PATH.read_text(
        encoding="utf-8"
    )

    required = [
        "Memory response style policy:",
        "Calendar scheduling contract "
        "for this user turn",
        "## Time-of-day grounding — "
        "strict rule",
        "render_user_mood_block(",
        "get_interaction_preferences_block(",
        "render_profile_runtime_context(",
        "render_response_texture_block(",
        "get_base_prompt(",
        '"cache_control"',
    ]

    for token in required:
        assert token in source


def test_stream_consumes_prepared_system_blocks():
    source = CHAT_PATH.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    stream = _function(
        tree,
        "_stream_claude_response",
    )

    args = {
        arg.arg
        for arg in stream.args.args
        + stream.args.kwonlyargs
    }

    assert "system_blocks" in args
    assert "volatile_context" not in args

    stream_source = ast.get_source_segment(
        source,
        stream,
    )

    assert stream_source is not None

    assert (
        "get_base_prompt("
        not in stream_source
    )

    assert (
        "claude.messages.stream("
        in stream_source
    )


def test_runtime_keeps_provider_and_db_internals_out():
    source = RUNTIME_PATH.read_text(
        encoding="utf-8"
    )

    forbidden = [
        "get_supabase",
        ".table(",
        ".rpc(",
        "get_claude",
        "anthropic",
        "googleapiclient",
    ]

    for token in forbidden:
        assert token not in source


def test_runtime_still_has_one_way_dependency():
    service_dir = Path(
        "app/services"
    )

    violations = []

    for path in service_dir.glob(
        "*.py"
    ):
        if path.name == (
            "cognitive_runtime.py"
        ):
            continue

        source = path.read_text(
            encoding="utf-8"
        )

        if "cognitive_runtime" in source:
            violations.append(
                path.name
            )

    assert violations == []
