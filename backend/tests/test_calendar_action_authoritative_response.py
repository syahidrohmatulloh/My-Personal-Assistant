import ast
from pathlib import Path


CHAT = Path(
    "app/routers/chat.py"
).read_text(
    encoding="utf-8"
)

CALENDAR = Path(
    "app/services/"
    "cognitive_calendar_orchestration.py"
).read_text(
    encoding="utf-8"
)

CONTEXT = Path(
    "app/services/"
    "cognitive_turn_context.py"
).read_text(
    encoding="utf-8"
)



def _module_owner_calls(
    source: str,
    owner: str,
) -> list[str]:
    tree = ast.parse(source)

    calls: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if not isinstance(
            func,
            ast.Attribute,
        ):
            continue

        root = func.value

        if (
            isinstance(
                root,
                ast.Name,
            )
            and root.id == owner
        ):
            calls.append(
                func.attr
            )

    return calls


def test_calendar_action_executes_before_model_preparation():
    action_index = CHAT.index(
        "_cognitive_runtime."
        "execute_calendar_turn("
    )

    prompt_index = CHAT.index(
        "_cognitive_runtime."
        "prepare_generation_context("
    )

    response_index = CHAT.index(
        "_stream_claude_response(",
        prompt_index,
    )

    assert (
        action_index
        < prompt_index
        < response_index
    )


def test_authoritative_result_is_added_to_volatile_context():
    assert (
        "calendar_draft_actions."
        "render_calendar_action_result_context("
        in CONTEXT
    )

    assert (
        "The Calendar action has already "
        "been attempted before this reply"
        in CONTEXT
    )

    assert (
        "Say the action succeeded only "
        "when success is true"
        in CONTEXT
    )



def test_calendar_action_has_one_foreground_execution_owner():
    chat_calls = _module_owner_calls(
        CHAT,
        "calendar_draft_actions",
    )

    calendar_calls = _module_owner_calls(
        CALENDAR,
        "calendar_draft_actions",
    )

    assert (
        "apply_chat_calendar_draft_action"
        not in chat_calls
    )

    assert (
        calendar_calls.count(
            "apply_chat_calendar_draft_action"
        )
        == 1
    )

def test_stream_receives_explicit_calendar_action_state():
    assert (
        "calendar_action_turn: bool = False"
        in CHAT
    )

    assert (
        "calendar_action_snapshot_dirty: "
        "bool = False"
        in CHAT
    )

    assert (
        "calendar_action_turn="
        "is_calendar_draft_action_turn"
        in CHAT
    )

    assert (
        "calendar_action_snapshot_dirty="
        "calendar_action_snapshot_dirty"
        in CHAT
    )


def test_failed_action_snapshot_dirty_contract_moves_to_orchestrator():
    assert (
        "calendar_action_success"
        in CALENDAR
    )

    assert (
        '"local_update_after_"'
        in CALENDAR
    )

    assert (
        '"google_patch_failed"'
        in CALENDAR
    )

    assert (
        '"local_archive_after_"'
        in CALENDAR
    )

    assert (
        '"google_delete_failed"'
        in CALENDAR
    )



def test_action_turn_skips_confirmation_in_foreground_orchestrator():
    assert (
        "if not "
        "is_calendar_draft_action_turn:"
        in CALENDAR
    )

    confirmation_calls = (
        _module_owner_calls(
            CALENDAR,
            "calendar_confirmation_actions",
        )
    )

    assert (
        "apply_calendar_confirmation_decision"
        in confirmation_calls
    )

def test_calendar_action_reply_cannot_infer_other_schedule_context():
    assert (
        "use only facts explicitly present "
        "in the authoritative result"
        in CONTEXT
    )

    assert (
        "Do not use chronology, memories, "
        "workspace cards"
        in CONTEXT
    )

    assert (
        "Do not mention another meeting "
        "or reminder"
        in CONTEXT
    )

    assert (
        "do not add conversational "
        "embellishment"
        in CONTEXT
    )


def test_calendar_action_turn_cannot_schedule_proactive_nudge():
    start = CHAT.index(
        "should_schedule_proactive_nudge = ("
    )

    end = CHAT.index(
        "\n    if should_schedule_proactive_nudge:",
        start,
    )

    block = CHAT[
        start:end
    ]

    assert (
        "not calendar_action_turn"
        in block
    )

    assert (
        "proactive_nudges."
        "should_attempt_proactive_nudge"
        in block
    )
