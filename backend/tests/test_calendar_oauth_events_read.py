import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.routers import calendar_oauth


def test_google_events_params_expand_recurring_events_and_order_by_start():
    params = calendar_oauth._build_google_calendar_events_params(
        start_dt=datetime(2026, 6, 12, tzinfo=timezone.utc),
        end_dt=datetime(2026, 6, 13, tzinfo=timezone.utc),
        time_zone="Asia/Jakarta",
    )

    assert params["singleEvents"] == "true"
    assert params["orderBy"] == "startTime"
    assert params["showDeleted"] == "false"
    assert params["timeZone"] == "Asia/Jakarta"
    assert params["maxResults"] == 250
    assert params["timeMin"] == "2026-06-12T00:00:00Z"
    assert params["timeMax"] == "2026-06-13T00:00:00Z"


def test_normalize_timed_google_event_returns_only_sanitized_fields():
    raw = {
        "id": "google-1",
        "summary": "Meeting",
        "description": "private description",
        "attendees": [{"email": "private@example.com"}],
        "status": "confirmed",
        "location": "Menara Mandiri",
        "htmlLink": "https://calendar.google.com/event?eid=1",
        "start": {"dateTime": "2026-06-12T10:00:00+07:00"},
        "end": {"dateTime": "2026-06-12T11:00:00+07:00"},
    }

    event = calendar_oauth._normalize_google_calendar_event(
        raw,
        time_zone="Asia/Jakarta",
    )

    assert event == {
        "id": "google-1",
        "title": "Meeting",
        "event_date": "2026-06-12",
        "start_at": "2026-06-12T10:00:00+07:00",
        "end_at": "2026-06-12T11:00:00+07:00",
        "all_day": False,
        "location": "Menara Mandiri",
        "html_link": "https://calendar.google.com/event?eid=1",
        "status": "confirmed",
        "source": "google",
        "is_recurring": False,
        "recurring_event_id": None,
        "original_start_at": None,
    }
    assert "description" not in event
    assert "attendees" not in event


def test_normalize_all_day_google_event_uses_start_date():
    event = calendar_oauth._normalize_google_calendar_event(
        {
            "id": "google-all-day",
            "summary": "Holiday",
            "status": "confirmed",
            "start": {"date": "2026-06-14"},
            "end": {"date": "2026-06-15"},
        },
        time_zone="Asia/Jakarta",
    )

    assert event is not None
    assert event["event_date"] == "2026-06-14"
    assert event["start_at"] is None
    assert event["end_at"] is None
    assert event["all_day"] is True


def test_cancelled_google_event_is_not_returned():
    event = calendar_oauth._normalize_google_calendar_event(
        {
            "id": "cancelled-event",
            "status": "cancelled",
            "start": {"date": "2026-06-14"},
            "end": {"date": "2026-06-15"},
        },
        time_zone=None,
    )

    assert event is None


def test_disconnected_user_gets_empty_non_error_response(monkeypatch):
    monkeypatch.setattr(
        calendar_oauth,
        "_get_connection",
        lambda *, user_id: None,
    )

    result = asyncio.run(
        calendar_oauth.google_calendar_oauth_events(
            start="2026-06-12T00:00:00Z",
            end="2026-06-13T00:00:00Z",
            time_zone="Asia/Jakarta",
            user_id="user-1",
        )
    )

    assert result == {
        "connected": False,
        "reauth_required": False,
        "events": [],
        "truncated": False,
    }


def test_connected_user_receives_normalized_events(monkeypatch):
    monkeypatch.setattr(
        calendar_oauth,
        "_get_connection",
        lambda *, user_id: {"status": "active"},
    )

    async def fake_access_token(*, user_id):
        assert user_id == "user-1"
        return "access-token"

    async def fake_list_events(**kwargs):
        assert kwargs["access_token"] == "access-token"
        assert kwargs["time_zone"] == "Asia/Jakarta"
        return (
            [
                {
                    "id": "google-1",
                    "title": "Meeting",
                    "event_date": "2026-06-12",
                    "start_at": "2026-06-12T10:00:00+07:00",
                    "end_at": "2026-06-12T11:00:00+07:00",
                    "all_day": False,
                    "location": None,
                    "html_link": None,
                    "status": "confirmed",
                    "source": "google",
                }
            ],
            False,
        )

    monkeypatch.setattr(
        calendar_oauth,
        "get_active_google_calendar_access_token",
        fake_access_token,
    )
    monkeypatch.setattr(
        calendar_oauth,
        "_list_google_calendar_events",
        fake_list_events,
    )

    result = asyncio.run(
        calendar_oauth.google_calendar_oauth_events(
            start="2026-06-12T00:00:00Z",
            end="2026-06-13T00:00:00Z",
            time_zone="Asia/Jakarta",
            user_id="user-1",
        )
    )

    assert result["connected"] is True
    assert result["truncated"] is False
    assert result["events"][0]["id"] == "google-1"


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("not-a-date", "2026-06-13T00:00:00Z"),
        ("2026-06-13T00:00:00Z", "2026-06-12T00:00:00Z"),
        ("2026-06-12T00:00:00", "2026-06-13T00:00:00Z"),
        ("2026-06-01T00:00:00Z", "2026-07-03T00:00:00Z"),
    ],
)
def test_invalid_event_ranges_are_rejected(start, end):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            calendar_oauth.google_calendar_oauth_events(
                start=start,
                end=end,
                time_zone="Asia/Jakarta",
                user_id="user-1",
            )
        )

    assert exc_info.value.status_code == 400


def test_invalid_iana_timezone_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            calendar_oauth.google_calendar_oauth_events(
                start="2026-06-12T00:00:00Z",
                end="2026-06-13T00:00:00Z",
                time_zone="Not/A-Timezone",
                user_id="user-1",
            )
        )

    assert exc_info.value.status_code == 400

def test_normalize_recurring_google_instance_preserves_series_metadata():
    event = calendar_oauth._normalize_google_calendar_event(
        {
            "id": "instance-1",
            "recurringEventId": "series-1",
            "summary": "Learning reminder",
            "status": "confirmed",
            "start": {
                "dateTime": "2026-06-12T12:00:00+07:00"
            },
            "end": {
                "dateTime": "2026-06-12T12:30:00+07:00"
            },
            "originalStartTime": {
                "dateTime": "2026-06-12T12:00:00+07:00"
            },
        },
        time_zone="Asia/Jakarta",
    )

    assert event is not None
    assert event["is_recurring"] is True
    assert event["recurring_event_id"] == "series-1"
    assert (
        event["original_start_at"]
        == "2026-06-12T12:00:00+07:00"
    )

