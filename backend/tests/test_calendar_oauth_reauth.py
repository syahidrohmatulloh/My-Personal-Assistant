import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.routers import calendar_oauth


def _active_token_row():
    return {
        "status": "active",
        "access_token": "encrypted-access-token",
        "refresh_token": "encrypted-refresh-token",
        "expires_at": (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat(),
    }


def test_invalid_grant_marks_connection_as_reauth_required(
    monkeypatch,
):
    monkeypatch.setattr(
        calendar_oauth,
        "_get_token_connection",
        lambda *, user_id: _active_token_row(),
    )
    monkeypatch.setattr(
        calendar_oauth,
        "require_token_encryption_configured",
        lambda: None,
    )
    monkeypatch.setattr(
        calendar_oauth,
        "decrypt_token",
        lambda value: (
            "access-token"
            if "access" in str(value)
            else "refresh-token"
        ),
    )
    monkeypatch.setattr(
        calendar_oauth,
        "_migrate_legacy_tokens",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        calendar_oauth,
        "_require_google_oauth_config",
        lambda: (
            "client-id",
            "client-secret",
            "redirect-uri",
        ),
    )

    async def fake_refresh(**kwargs):
        raise calendar_oauth.GoogleCalendarReauthRequiredError(
            "invalid grant"
        )

    marked = []

    monkeypatch.setattr(
        calendar_oauth,
        "_refresh_access_token",
        fake_refresh,
    )
    monkeypatch.setattr(
        calendar_oauth,
        "_mark_connection_reauth_required",
        lambda *, user_id: marked.append(user_id),
    )

    with pytest.raises(
        calendar_oauth.GoogleCalendarReauthRequiredError
    ):
        asyncio.run(
            calendar_oauth
            .get_active_google_calendar_access_token(
                user_id="user-1"
            )
        )

    assert marked == ["user-1"]


def test_events_return_structured_reauth_state(monkeypatch):
    monkeypatch.setattr(
        calendar_oauth,
        "_get_connection",
        lambda *, user_id: {
            "status": "reauth_required",
        },
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
        "reauth_required": True,
        "events": [],
        "truncated": False,
    }


def test_active_events_response_exposes_non_reauth_state(
    monkeypatch,
):
    monkeypatch.setattr(
        calendar_oauth,
        "_get_connection",
        lambda *, user_id: {"status": "active"},
    )

    async def fake_token(**kwargs):
        return "access-token"

    async def fake_events(**kwargs):
        return [], False

    monkeypatch.setattr(
        calendar_oauth,
        "get_active_google_calendar_access_token",
        fake_token,
    )
    monkeypatch.setattr(
        calendar_oauth,
        "_list_google_calendar_events",
        fake_events,
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
    assert result["reauth_required"] is False
