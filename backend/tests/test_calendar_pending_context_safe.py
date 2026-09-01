import ast
from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
TURN_CONTEXT = Path(
    "app/services/cognitive_turn_context.py"
).read_text(
    encoding="utf-8"
)
CALENDAR_ORCHESTRATION = Path(
    "app/services/cognitive_calendar_orchestration.py"
).read_text(encoding="utf-8")




def test_pending_calendar_context_does_not_use_uninitialized_conversation_id():
    context_tree = ast.parse(
        TURN_CONTEXT
    )

    calls = []

    for node in ast.walk(
        context_tree
    ):
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
            == "render_pending_calendar_confirmation_context"
            and isinstance(
                func.value,
                ast.Name,
            )
            and func.value.id
            == "calendar_confirmation_actions"
        ):
            calls.append(
                node
            )

    assert len(calls) == 1

    call = calls[0]

    conversation_kw = next(
        keyword
        for keyword in call.keywords
        if keyword.arg
        == "conversation_id"
    )

    value = conversation_kw.value

    assert isinstance(
        value,
        ast.Call,
    )
    assert isinstance(
        value.func,
        ast.Name,
    )
    assert value.func.id == "getattr"

    assert len(
        value.args
    ) == 3

    assert isinstance(
        value.args[0],
        ast.Name,
    )
    assert (
        value.args[0].id
        == "body"
    )

    assert isinstance(
        value.args[1],
        ast.Constant,
    )
    assert (
        value.args[1].value
        == "conversation_id"
    )

    assert isinstance(
        value.args[2],
        ast.Constant,
    )
    assert (
        value.args[2].value
        is None
    )


def test_pending_calendar_context_no_longer_uses_bare_conversation_id_in_chat_setup():
    chat_tree = ast.parse(CHAT)
    context_tree = ast.parse(
        TURN_CONTEXT
    )

    chat_fn = next(
        node
        for node in chat_tree.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name == "chat"
    )

    direct_chat_calls = []

    for node in ast.walk(
        chat_fn
    ):
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
            == "render_pending_calendar_confirmation_context"
            and isinstance(
                func.value,
                ast.Name,
            )
            and func.value.id
            == "calendar_confirmation_actions"
        ):
            direct_chat_calls.append(
                node
            )

    assert (
        direct_chat_calls
        == []
    )

    context_calls = []

    for node in ast.walk(
        context_tree
    ):
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
            == "render_pending_calendar_confirmation_context"
            and isinstance(
                func.value,
                ast.Name,
            )
            and func.value.id
            == "calendar_confirmation_actions"
        ):
            context_calls.append(
                node
            )

    assert len(
        context_calls
    ) == 1

    prepared_reads = [
        node
        for node in ast.walk(
            chat_fn
        )
        if isinstance(
            node,
            ast.Attribute,
        )
        and node.attr
        == "pending_calendar_confirmation_context"
        and isinstance(
            node.value,
            ast.Name,
        )
        and node.value.id
        == "generation_context"
    ]

    assert len(
        prepared_reads
    ) == 1
