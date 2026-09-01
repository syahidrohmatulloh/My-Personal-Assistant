import ast
from app.services import calendar_draft_actions
from pathlib import Path


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
CALENDAR_ORCHESTRATION = Path(
    "app/services/cognitive_calendar_orchestration.py"
).read_text(encoding="utf-8")
TURN_CONTEXT = Path(
    "app/services/cognitive_turn_context.py"
).read_text(encoding="utf-8")


def test_calendar_draft_action_request_detection():
    assert calendar_draft_actions.is_calendar_draft_action_request("ubah yang jemput Aneira jadi jam 3 sore")
    assert calendar_draft_actions.is_calendar_draft_action_request("ganti lokasi padel jadi Plaza Festival")
    assert calendar_draft_actions.is_calendar_draft_action_request("reschedule bowling ke besok jam 10")
    assert calendar_draft_actions.is_calendar_draft_action_request(
        "beb tolong revisi kalender, golf dengan Indosat itu mulai di 05.52 dan selesai di jam 13.00"
    )
    assert calendar_draft_actions.is_calendar_draft_action_request(
        "koreksi jadwal meeting besok jadi jam 9"
    )
    assert not calendar_draft_actions.is_calendar_draft_action_request(
        "tolong revisi tulisan ini"
    )
    assert calendar_draft_actions.is_calendar_draft_action_request("hapus jadwal jemput Aneira")
    assert calendar_draft_actions.is_calendar_draft_action_request("batalin agenda padel nanti sore")
    assert not calendar_draft_actions.is_calendar_draft_action_request("hai beb")


def test_build_update_payload_updates_time_only():
    target = {
        "id": "abc",
        "calendar_event_title": "Jemput Aneira — Lomba Dance",
        "calendar_event_date": "2026-05-23",
        "calendar_event_start_at": "2026-05-23T14:00:00+07:00",
        "calendar_event_end_at": "2026-05-23T15:00:00+07:00",
        "calendar_event_all_day": False,
        "calendar_event_status": "confirmed_local",
    }
    action = {
        "action": "update",
        "target_memory_id": "abc",
        "start_at": "2026-05-23T15:00:00+07:00",
        "end_at": "2026-05-23T16:00:00+07:00",
        "confidence": 0.9,
    }

    payload = calendar_draft_actions._build_update_payload(target, action)

    assert payload["calendar_event_title"] == "Jemput Aneira — Lomba Dance"
    assert payload["calendar_event_start_at"] == "2026-05-23T15:00:00+07:00"
    assert payload["calendar_event_end_at"] == "2026-05-23T16:00:00+07:00"
    assert payload["calendar_event_status"] == "confirmed_local"
    assert payload["calendar_candidate"] is False


def test_build_archive_payload_soft_deletes_local_calendar_item():
    payload = calendar_draft_actions._build_archive_payload()

    assert payload["archived"] is True
    assert payload["archived_by"] == "chat_calendar_action"
    assert payload["calendar_candidate"] is False
    assert "archived_at" in payload
    assert "updated_at" in payload


def test_normalise_delete_action_requires_valid_target_and_confidence():
    records = [{"id": "abc"}]
    raw = {
        "is_calendar_action": True,
        "action": "delete",
        "target_memory_id": "abc",
        "confidence": 0.9,
        "reason": "user_requested_delete",
    }

    action = calendar_draft_actions._normalise_action(raw, records)

    assert action is not None
    assert action["action"] == "delete"
    assert action["target_memory_id"] == "abc"


def test_synced_google_detection_blocks_silent_chat_delete():
    row = {"calendar_event_status": "synced_google"}
    assert calendar_draft_actions._is_synced_google(row) is True





def test_chat_executes_calendar_draft_actions_authoritatively_before_stream():
    chat_tree = ast.parse(CHAT)

    orchestration_source = Path(
        "app/services/"
        "cognitive_calendar_orchestration.py"
    ).read_text(
        encoding="utf-8"
    )

    orchestration_tree = ast.parse(
        orchestration_source
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

    def count_call(
        tree_or_node,
        owner,
        attr,
    ):
        return sum(
            1
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
        )

    assert (
        count_call(
            orchestration_tree,
            "calendar_draft_actions",
            "apply_chat_calendar_draft_action",
        )
        == 1
    )

    assert (
        count_call(
            chat_fn,
            "calendar_draft_actions",
            "apply_chat_calendar_draft_action",
        )
        == 0
    )

    assert (
        count_call(
            chat_fn,
            "_cognitive_runtime",
            "execute_calendar_turn",
        )
        == 1
    )

def test_chat_has_user_facing_calendar_action_guidance():
    assert (
        "Calendar draft action capability state — authoritative"
        in TURN_CONTEXT
    )
    assert (
        "The Calendar action has already been attempted before this reply"
        in TURN_CONTEXT
    )
    assert (
        "Follow the authoritative Calendar action result below exactly"
        in TURN_CONTEXT
    )
    assert (
        "Say the action succeeded only when success is true"
        in TURN_CONTEXT
    )
    assert (
        "render_calendar_action_result_context"
        in TURN_CONTEXT
    )

    assert (
        "Calendar draft action capability state — authoritative"
        not in CHAT
    )


def test_stream_uses_precomputed_calendar_action_state():
    assert "calendar_action_turn: bool = False" in CHAT
    assert (
        "should_apply_calendar_draft_action = calendar_action_turn"
        in CHAT
    )
    assert (
        "should_apply_calendar_draft_action = "
        "calendar_draft_actions.is_calendar_draft_action_request("
        not in CHAT
    )


def test_colloquial_recurring_scope_reply_enters_action_flow():
    assert (
        calendar_draft_actions
        .is_calendar_draft_action_request(
            "hari ini aja"
        )
    )
    assert (
        calendar_draft_actions
        .is_calendar_draft_action_request(
            "yang ini aja"
        )
    )
