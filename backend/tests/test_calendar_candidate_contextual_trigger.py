import ast
from app.services.calendar_candidate_extractor import (
    has_calendar_signal,
    should_attempt_calendar_candidate_extraction,
)
from pathlib import Path


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
CALENDAR_ORCHESTRATION = Path(
    "app/services/cognitive_calendar_orchestration.py"
).read_text(encoding="utf-8")
HELPERS = Path("app/services/chat_calendar_helpers.py").read_text(encoding="utf-8")


def test_contextual_calendar_candidate_followup_triggers_attempt():
    message = "tolong masukan ulang ke kalender candidate yang jemput aneira"

    assert has_calendar_signal(message) is False
    assert should_attempt_calendar_candidate_extraction(message) is True


def test_explicit_calendar_without_date_can_attempt_haiku_fallback():
    message = "tolong masukkan ke kalender ya"

    assert should_attempt_calendar_candidate_extraction(message) is True




def test_chat_uses_broader_calendar_attempt_trigger():
    chat_tree = ast.parse(CHAT)

    chat_fn = next(
        node
        for node in chat_tree.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name == "chat"
    )

    orchestration_tree = ast.parse(
        CALENDAR_ORCHESTRATION
    )

    def calls(
        tree_or_node,
        owner,
        attr,
    ):
        return [
            node
            for node in ast.walk(
                tree_or_node
            )
            if isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Attribute,
            )
            and node.func.attr == attr
            and isinstance(
                node.func.value,
                ast.Name,
            )
            and node.func.value.id == owner
        ]

    assert (
        len(
            calls(
                chat_fn,
                "_cognitive_runtime",
                "execute_calendar_turn",
            )
        )
        == 1
    )

    assert (
        len(
            calls(
                orchestration_tree,
                "chat_calendar_helpers",
                "should_hard_gate_calendar_candidate",
            )
        )
        == 1
    )

    assert (
        len(
            calls(
                orchestration_tree,
                "calendar_candidate_extractor",
                "extract_and_persist",
            )
        )
        == 1
    )

    assert (
        len(
            calls(
                chat_fn,
                "calendar_candidate_extractor",
                "extract_and_persist",
            )
        )
        == 0
    )

    assert (
        "temporal_calendar_policy"
        in HELPERS
    )
    assert (
        ".assess_calendar_semantics("
        in HELPERS
    )
    assert (
        "calendar_candidate_extractor."
        "should_attempt_calendar_candidate_extraction(raw)"
        not in HELPERS
    )
