from pathlib import Path

MEMORY_REVIEW = Path("app/routers/memory_review.py").read_text(encoding="utf-8")


def _function_block(name: str) -> str:
    start = MEMORY_REVIEW.index(f"async def {name}(")
    next_route = MEMORY_REVIEW.find("\n@router.", start + 1)
    end = next_route if next_route != -1 else len(MEMORY_REVIEW)
    return MEMORY_REVIEW[start:end]


def test_delete_google_calendar_endpoint_exists_without_pin():
    assert '@router.post("/calendar-candidates/{memory_id}/delete-google")' in MEMORY_REVIEW
    block = _function_block("delete_google_calendar_candidate")
    assert "memory_pin.require_valid_pin" not in block
    assert "pin=body.pin" not in block
    assert "get_active_google_calendar_access_token" in block
    assert "_delete_google_calendar_event" in block
    assert '"google_calendar_event_deleted"' in block


def test_delete_google_calendar_helper_uses_google_calendar_api():
    assert "https://www.googleapis.com/calendar/v3/calendars/" in MEMORY_REVIEW
    assert "client.delete(" in MEMORY_REVIEW
    assert "quote(calendar_id" in MEMORY_REVIEW
    assert "quote(google_event_id" in MEMORY_REVIEW


def test_delete_google_archives_local_calendar_item():
    block = _function_block("delete_google_calendar_candidate")
    assert '"archived": True' in block
    assert '"archived_by": "google_calendar_delete"' in block
    assert '"calendar_event_status": "deleted_google"' in block
    assert '"calendar_candidate": False' in block
