from pathlib import Path

from app.services import calendar_draft_actions


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
SERVICE = Path("app/services/calendar_draft_actions.py").read_text(encoding="utf-8")


def test_google_calendar_create_request_requires_google_signal():
    positives = [
        "tolong masukin ke Google Calendar jam 3 sore meeting di Plaza Indonesia",
        "sync ke google kalender acara bowling jam 12",
        "masukin ke Google jam 3 sore meeting dengan Budi",
        "masukkan ke Google Calendar besok jam 10",
        "tambahin ke Google Kalender acara padel nanti sore",
        "catat ke Google jam 2 siang jemput Aneira",
        "bikin di Google Calendar meeting besok pagi",
        "buat di Google Cal acara golf hari minggu",
    ]

    for message in positives:
        assert calendar_draft_actions.is_google_calendar_create_request(message), message

    negatives = [
        "masukin ke kalender jam 3 sore meeting",
        "catat ke calendar dulu ya",
        "buat agenda lokal jam 2",
    ]

    for message in negatives:
        assert not calendar_draft_actions.is_google_calendar_create_request(message), message


def test_chat_wires_direct_google_create_and_blocks_duplicate_candidate():
    assert "create_google_calendar_event_from_chat" in CHAT
    assert "should_create_google_calendar_event" in CHAT
    assert "not should_create_google_calendar_event" in CHAT


def test_service_can_update_and_delete_synced_google_events():
    assert "_apply_synced_google_calendar_action" in SERVICE
    assert "_patch_google_calendar_event" in SERVICE
    assert "_delete_google_calendar_event" in SERVICE
    assert "chat_google_calendar_delete" in SERVICE


def test_service_can_create_google_calendar_event_from_chat():
    assert "create_google_calendar_event_from_chat" in SERVICE
    assert "_create_google_calendar_event" in SERVICE
    assert "calendar_event_status" in SERVICE
    assert "synced_google" in SERVICE
    assert "google_calendar_event_id" in SERVICE


def test_synced_google_no_longer_returns_ui_confirmation_noop():
    assert "synced_google_requires_ui_confirmation" not in SERVICE


def test_google_create_from_chat_is_idempotent_with_existing_calendar_memory():
    assert "_find_existing_calendar_memory_for_draft" in SERVICE
    assert "calendar_event_already_synced" in SERVICE
    assert "synced_existing_local_event" in SERVICE
    assert "_mark_memory_as_synced_google" in SERVICE


def test_google_create_from_chat_reuses_existing_google_event():
    assert "_find_existing_google_event_for_draft" in SERVICE
    assert "linked_existing_google_event" in SERVICE
    assert "list_google_calendar_events_for_action" in SERVICE


def test_google_create_from_chat_archives_duplicate_calendar_memories():
    assert "_archive_duplicate_calendar_memories_for_event" in SERVICE
    assert "duplicate_cleanup" in SERVICE
    assert "archived_duplicates" in SERVICE

