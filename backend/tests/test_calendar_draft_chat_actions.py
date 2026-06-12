from app.services import calendar_draft_actions
from pathlib import Path


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


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


def test_chat_wires_calendar_draft_actions_background_task():
    assert "calendar_draft_actions," in CHAT
    assert "calendar_draft_actions.apply_chat_calendar_draft_action" in CHAT
    assert "Calendar draft actions from chat" in CHAT
    assert "can update/delete local drafts and synced Google events" in CHAT
    assert "not should_apply_calendar_draft_action" in CHAT


def test_chat_has_user_facing_calendar_action_guidance():
    assert "Calendar draft action capability state — authoritative" in CHAT
    assert "The action executes in the background after this reply" in CHAT
    assert "Do not say 'sudah aku update'" in CHAT
    assert "Aku proses update-nya di Calendar ya" in CHAT
    assert "Aku proses penghapusannya ya" in CHAT
