import asyncio
from pathlib import Path

from app.services import calendar_draft_actions
from app.services import calendar_pending_actions


SCHEMA = Path(
    "schema_phase_calendar_pending_actions.sql"
).read_text(encoding="utf-8")


def _target():
    return {
        "id": "google:instance-1",
        "_record_source": "google",
        "calendar_event_title": "Learning reminder",
        "calendar_event_date": "2026-06-12",
        "calendar_event_start_at": (
            "2026-06-12T12:00:00+07:00"
        ),
        "calendar_event_end_at": (
            "2026-06-12T12:30:00+07:00"
        ),
        "calendar_event_all_day": False,
        "google_calendar_event_id": "instance-1",
        "google_calendar_id": "primary",
        "google_recurring_event_id": "series-1",
        "calendar_event_is_recurring": True,
    }


def _action():
    return {
        "is_calendar_action": True,
        "action": "update",
        "target_memory_id": "google:instance-1",
        "start_at": "2026-06-12T13:00:00+07:00",
        "end_at": "2026-06-12T13:30:00+07:00",
        "confidence": 0.97,
    }


def test_pending_schema_has_expiry_rls_and_one_pending_per_chat():
    assert "create table if not exists public.calendar_pending_actions" in SCHEMA
    assert "expires_at timestamptz not null" in SCHEMA
    assert "where status = 'pending'" in SCHEMA
    assert "enable row level security" in SCHEMA
    assert "auth.uid() = user_id" in SCHEMA


def test_parse_recurring_scope_replies():
    assert (
        calendar_pending_actions.parse_recurring_scope(
            "hari ini saja"
        )
        == "this_instance"
    )
    assert (
        calendar_pending_actions.parse_recurring_scope(
            "ini dan seterusnya"
        )
        == "this_and_following"
    )
    assert (
        calendar_pending_actions.parse_recurring_scope(
            "seluruh rangkaian"
        )
        == "entire_series"
    )


def test_full_action_with_scope_is_not_treated_as_scope_only():
    assert not (
        calendar_pending_actions
        .is_recurring_scope_only_reply(
            "ubah Learning reminder hari ini saja jadi jam 13"
        )
    )


def test_initial_recurring_action_is_persisted(monkeypatch):
    async def fake_load_records(**kwargs):
        return [_target()], False

    async def fake_extract(**kwargs):
        return _action()

    async def fake_apply(**kwargs):
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": "update",
            "source": "google",
            "reason": "recurring_scope_required",
        }

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {
            "id": "pending-1",
            "expires_at": "2026-06-12T06:30:00+00:00",
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
        "_apply_direct_google_calendar_action",
        fake_apply,
    )
    monkeypatch.setattr(
        calendar_pending_actions,
        "create_pending_recurring_action",
        fake_create,
    )

    result = asyncio.run(
        calendar_draft_actions
        .apply_chat_calendar_draft_action(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message=(
                "ubah Learning reminder jadi jam 13.00"
            ),
        )
    )

    assert result["reason"] == "recurring_scope_required"
    assert result["pending_action_saved"] is True
    assert result["pending_action_id"] == "pending-1"
    assert (
        captured["target"]["google_calendar_event_id"]
        == "instance-1"
    )
    assert captured["action"]["start_at"].endswith(
        "13:00:00+07:00"
    )


def test_scope_only_reply_resumes_saved_action(monkeypatch):
    monkeypatch.setattr(
        calendar_pending_actions,
        "load_pending_recurring_action",
        lambda **kwargs: {
            "id": "pending-1",
            "action_type": "update",
            "target_snapshot": _target(),
            "requested_action": _action(),
        },
    )

    captured = {}

    async def fake_apply(**kwargs):
        captured.update(kwargs)
        return {
            "attempted": True,
            "success": True,
            "updated": True,
            "deleted": False,
            "action": "update",
            "source": "google",
            "reason": None,
        }

    completed = []

    monkeypatch.setattr(
        calendar_draft_actions,
        "_apply_direct_google_calendar_action",
        fake_apply,
    )
    monkeypatch.setattr(
        calendar_pending_actions,
        "mark_pending_recurring_action_completed",
        lambda **kwargs: completed.append(kwargs),
    )

    result = asyncio.run(
        calendar_draft_actions
        .apply_chat_calendar_draft_action(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message="hari ini saja",
        )
    )

    assert result["success"] is True
    assert (
        captured["action"]["recurring_scope"]
        == "this_instance"
    )
    assert captured["action"]["start_at"].endswith(
        "13:00:00+07:00"
    )
    assert completed == [
        {
            "pending_action_id": "pending-1",
            "user_id": "user-1",
        }
    ]


def test_missing_or_expired_pending_action_is_safe(monkeypatch):
    monkeypatch.setattr(
        calendar_pending_actions,
        "load_pending_recurring_action",
        lambda **kwargs: None,
    )

    result = asyncio.run(
        calendar_draft_actions
        .apply_chat_calendar_draft_action(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message="hari ini saja",
        )
    )

    assert result["success"] is False
    assert result["reason"] == "no_pending_recurring_action"
