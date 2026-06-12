import asyncio

from app.services import calendar_draft_actions


def _direct_record():
    return {
        "id": "google:google-event-1",
        "_record_source": "google",
        "calendar_event_title": "Direct Google Read Test",
        "calendar_event_date": "2026-06-12",
        "calendar_event_start_at": "2026-06-12T15:30:00+07:00",
        "calendar_event_end_at": "2026-06-12T16:00:00+07:00",
        "calendar_event_all_day": False,
        "calendar_event_location": "Menara Mandiri",
        "calendar_event_status": "direct_google",
        "google_calendar_event_id": "google-event-1",
        "google_calendar_id": "primary",
    }


def test_direct_google_record_has_opaque_action_id():
    record = calendar_draft_actions._direct_google_event_to_action_record(
        {
            "id": "google-event-1",
            "title": "Direct Google Read Test",
            "event_date": "2026-06-12",
            "start_at": "2026-06-12T15:30:00+07:00",
            "end_at": "2026-06-12T16:00:00+07:00",
            "all_day": False,
            "location": "Menara Mandiri",
            "html_link": "https://calendar.google.com/event",
        }
    )

    assert record["id"] == "google:google-event-1"
    assert record["_record_source"] == "google"
    assert record["google_calendar_event_id"] == "google-event-1"
    assert record["calendar_event_location"] == "Menara Mandiri"


def test_direct_google_patch_only_changes_requested_fields():
    patch = calendar_draft_actions._build_direct_google_patch(
        _direct_record(),
        {
            "action": "update",
            "target_memory_id": "google:google-event-1",
            "start_at": "2026-06-12T16:00:00+07:00",
            "end_at": "2026-06-12T16:30:00+07:00",
            "confidence": 0.95,
        },
    )

    assert patch == {
        "start": {
            "dateTime": "2026-06-12T16:00:00+07:00"
        },
        "end": {
            "dateTime": "2026-06-12T16:30:00+07:00"
        },
    }
    assert "summary" not in patch
    assert "description" not in patch
    assert "location" not in patch


def test_apply_direct_google_update_is_behavioral(monkeypatch):
    async def fake_load_records(**kwargs):
        return [_direct_record()], False

    async def fake_extract(**kwargs):
        return {
            "is_calendar_action": True,
            "action": "update",
            "target_memory_id": "google:google-event-1",
            "start_at": "2026-06-12T16:00:00+07:00",
            "end_at": "2026-06-12T16:30:00+07:00",
            "confidence": 0.95,
        }

    async def fake_token(**kwargs):
        return "access-token"

    captured = {}

    async def fake_patch(**kwargs):
        captured.update(kwargs)
        return {
            "id": "google-event-1",
            "summary": "Direct Google Read Test",
            "htmlLink": "https://calendar.google.com/event",
        }

    monkeypatch.setattr(
        calendar_draft_actions,
        "_load_calendar_action_records",
        fake_load_records,
    )
    monkeypatch.setattr(
        calendar_draft_actions,
        "_extract_action",
        fake_extract,
    )
    monkeypatch.setattr(
        calendar_draft_actions,
        "get_active_google_calendar_access_token",
        fake_token,
    )
    monkeypatch.setattr(
        calendar_draft_actions,
        "_patch_direct_google_calendar_event",
        fake_patch,
    )

    result = asyncio.run(
        calendar_draft_actions.apply_chat_calendar_draft_action(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message=(
                "ubah Direct Google Read Test jadi jam 16.00–16.30"
            ),
            client_context={
                "local_time": "2026-06-12T10:30:00+07:00",
                "timezone": "Asia/Jakarta",
            },
        )
    )

    assert result["success"] is True
    assert result["updated"] is True
    assert result["source"] == "google"
    assert result["google_event_id"] == "google-event-1"
    assert captured["patch"]["start"]["dateTime"].endswith(
        "16:00:00+07:00"
    )
    assert captured["patch"]["end"]["dateTime"].endswith(
        "16:30:00+07:00"
    )


def test_apply_direct_google_delete_is_behavioral(monkeypatch):
    async def fake_load_records(**kwargs):
        return [_direct_record()], False

    async def fake_extract(**kwargs):
        return {
            "is_calendar_action": True,
            "action": "delete",
            "target_memory_id": "google:google-event-1",
            "confidence": 0.95,
        }

    async def fake_token(**kwargs):
        return "access-token"

    deleted = {}

    async def fake_delete(**kwargs):
        deleted.update(kwargs)

    monkeypatch.setattr(
        calendar_draft_actions,
        "_load_calendar_action_records",
        fake_load_records,
    )
    monkeypatch.setattr(
        calendar_draft_actions,
        "_extract_action",
        fake_extract,
    )
    monkeypatch.setattr(
        calendar_draft_actions,
        "get_active_google_calendar_access_token",
        fake_token,
    )
    monkeypatch.setattr(
        calendar_draft_actions,
        "_delete_google_calendar_event",
        fake_delete,
    )

    result = asyncio.run(
        calendar_draft_actions.apply_chat_calendar_draft_action(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message="hapus Direct Google Read Test dari kalender",
        )
    )

    assert result["success"] is True
    assert result["deleted"] is True
    assert result["source"] == "google"
    assert deleted["google_event_id"] == "google-event-1"


def test_authoritative_result_context_allows_success_claim_only_on_success():
    success = calendar_draft_actions.render_calendar_action_result_context(
        {
            "success": True,
            "updated": True,
            "action": "update",
            "source": "google",
            "title": "Direct Google Read Test",
        }
    )
    failure = calendar_draft_actions.render_calendar_action_result_context(
        {
            "success": False,
            "action": "update",
            "source": "google",
            "reason": "google_patch_failed",
        }
    )

    assert "success: true" in success
    assert "has completed successfully" in success
    assert "You may clearly say it was updated" in success

    assert "success: false" in failure
    assert "did not complete successfully" in failure
    assert "Do not claim it was updated" in failure
