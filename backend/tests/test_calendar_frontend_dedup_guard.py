from pathlib import Path


SOURCE = Path("../frontend/lib/calendar-snapshot.ts").read_text(encoding="utf-8")


def test_frontend_calendar_display_dedup_is_wired():
    assert "dedupeCalendarEventsForDisplay" in SOURCE
    assert "calendarEventDisplayPriority" in SOURCE
    assert "return dedupeCalendarEventsForDisplay(merged).sort(sortCalendarEvents)" in SOURCE


def test_frontend_calendar_dedup_prefers_synced_or_google():
    assert 'event.source === "synced" && event.googleEventId' in SOURCE
    assert 'event.source === "google" && event.googleEventId' in SOURCE
