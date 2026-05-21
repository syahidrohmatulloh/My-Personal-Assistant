from app.routers.memory_review import _humanize_google_calendar_sync_error


def test_humanizes_scope_insufficient_error():
    msg = _humanize_google_calendar_sync_error(
        RuntimeError("ACCESS_TOKEN_SCOPE_INSUFFICIENT insufficient authentication scopes")
    )
    assert "permission is insufficient" in msg
    assert "connect Google Calendar again" in msg


def test_humanizes_disabled_calendar_api_error():
    msg = _humanize_google_calendar_sync_error(
        RuntimeError("Google Calendar API has not been used in project before or it is disabled")
    )
    assert "not enabled" in msg
    assert "Google Cloud Console" in msg


def test_humanizes_invalid_grant_error():
    msg = _humanize_google_calendar_sync_error(RuntimeError("invalid_grant"))
    assert "expired or was revoked" in msg
