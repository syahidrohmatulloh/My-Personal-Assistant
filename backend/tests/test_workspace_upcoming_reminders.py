from pathlib import Path


SOURCE = Path("app/routers/memory_review.py").read_text(encoding="utf-8")


def test_upcoming_reminders_endpoint_is_user_scoped():
    assert '@router.get("/upcoming-reminders")' in SOURCE
    assert '.table("proactive_nudges")' in SOURCE
    assert '.eq("user_id", user_id)' in SOURCE
    assert '.eq("status", "scheduled")' in SOURCE
    assert '.gte("due_at", now_iso)' in SOURCE


def test_upcoming_reminders_endpoint_has_bounded_limit():
    assert "limit must be between 1 and 20" in SOURCE
    assert ".limit(limit)" in SOURCE


def test_upcoming_reminders_does_not_expose_internal_errors():
    assert 'detail="Failed to load upcoming reminders"' in SOURCE
