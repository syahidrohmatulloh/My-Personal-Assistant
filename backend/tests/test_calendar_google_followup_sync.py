from pathlib import Path

import pytest

from app.services import calendar_draft_actions as actions


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
SERVICE = Path("app/services/calendar_draft_actions.py").read_text(encoding="utf-8")


def test_google_followup_sync_helper_is_wired_before_clarification():
    assert "sync_latest_confirmed_local_event_to_google_from_chat" in SERVICE
    assert "latest_local_google_sync_result" in CHAT
    assert '"no_confident_draft"' in CHAT
    assert '"missing_required_fields"' in CHAT


@pytest.mark.asyncio
async def test_google_followup_sync_marks_latest_confirmed_local_event(monkeypatch):
    row = {
        "id": "mem-1",
        "calendar_event_status": "confirmed_local",
        "calendar_event_title": "Bowling sama Aghnia dan Aneira",
        "calendar_event_date": "2026-06-16",
        "calendar_event_start_at": "2026-06-16T15:00:00+07:00",
        "calendar_event_end_at": "2026-06-16T16:00:00+07:00",
        "calendar_event_all_day": False,
        "calendar_event_location": "Spin City Agora",
        "google_calendar_event_id": None,
        "google_calendar_event_link": None,
    }

    monkeypatch.setattr(
        actions,
        "_find_latest_confirmed_local_calendar_event_for_google_sync",
        lambda **kwargs: row,
    )

    async def fake_token(*, user_id):
        return "token"

    async def fake_existing_google(**kwargs):
        return None

    async def fake_create_google_calendar_event(**kwargs):
        assert kwargs["title"] == "Bowling sama Aghnia dan Aneira"
        assert kwargs["event_date"] == "2026-06-16"
        assert kwargs["start_at"] == "2026-06-16T15:00:00+07:00"
        assert kwargs["end_at"] == "2026-06-16T16:00:00+07:00"
        assert kwargs["location"] == "Spin City Agora"
        return {"id": "g-1", "htmlLink": "https://calendar.google.com/event?eid=g-1"}

    def fake_mark(**kwargs):
        return {
            "attempted": True,
            "created": True,
            "reason": kwargs["source_reason"],
            "memory_id": kwargs["memory_id"],
            "title": kwargs["title"],
            "date": kwargs["event_date"],
            "start_at": kwargs["start_at"],
            "end_at": kwargs["end_at"],
            "location": kwargs["location"],
            "google_event_id": kwargs["google_event_id"],
            "google_event_link": kwargs["google_event_link"],
        }

    monkeypatch.setattr(actions, "get_active_google_calendar_access_token", fake_token)
    monkeypatch.setattr(actions, "_find_existing_google_event_for_draft", fake_existing_google)
    monkeypatch.setattr(actions, "_create_google_calendar_event", fake_create_google_calendar_event)
    monkeypatch.setattr(actions, "_mark_memory_as_synced_google", fake_mark)

    result = await actions.sync_latest_confirmed_local_event_to_google_from_chat(
        user_id="user-1",
        conversation_id="conv-1",
        user_message="masukkan ke google calendar ya",
    )

    assert result["attempted"] is True
    assert result["created"] is True
    assert result["memory_id"] == "mem-1"
    assert result["google_event_id"] == "g-1"
    assert result["location"] == "Spin City Agora"


@pytest.mark.asyncio
async def test_google_followup_sync_returns_already_synced(monkeypatch):
    row = {
        "id": "mem-1",
        "calendar_event_status": "synced_google",
        "calendar_event_title": "Bowling sama Aghnia dan Aneira",
        "calendar_event_date": "2026-06-16",
        "calendar_event_start_at": "2026-06-16T15:00:00+07:00",
        "calendar_event_end_at": "2026-06-16T16:00:00+07:00",
        "calendar_event_location": "Spin City Agora",
        "google_calendar_event_id": "g-existing",
        "google_calendar_event_link": "https://calendar.google.com/event?eid=g-existing",
    }

    monkeypatch.setattr(
        actions,
        "_find_latest_confirmed_local_calendar_event_for_google_sync",
        lambda **kwargs: row,
    )

    result = await actions.sync_latest_confirmed_local_event_to_google_from_chat(
        user_id="user-1",
        conversation_id="conv-1",
        user_message="sync ke google calendar",
    )

    assert result["reason"] == "calendar_event_already_synced"
    assert result["google_event_id"] == "g-existing"


@pytest.mark.asyncio
async def test_google_followup_sync_no_recent_local_event_is_safe(monkeypatch):
    monkeypatch.setattr(
        actions,
        "_find_latest_confirmed_local_calendar_event_for_google_sync",
        lambda **kwargs: None,
    )

    result = await actions.sync_latest_confirmed_local_event_to_google_from_chat(
        user_id="user-1",
        conversation_id="conv-1",
        user_message="masukkan ke google calendar ya",
    )

    assert result["attempted"] is True
    assert result["created"] is False
    assert result["reason"] == "no_recent_confirmed_local_event"
