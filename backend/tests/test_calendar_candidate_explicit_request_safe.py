from datetime import date

from app.services.calendar_candidate_extractor import extract_candidate, has_calendar_signal


def test_explicit_masukin_kalender_request_should_be_detected():
    message = "beb masukin ke kalender, besok aku jam 8-10 pagi ada acara sharing session sama HMIF ITB di Menara Mandiri 2 Lantai 10 ya"

    assert has_calendar_signal(message) is True

    candidate = extract_candidate(
        text=message,
        base_date=date(2026, 5, 23),
        timezone_offset_minutes=420,
    )

    assert candidate is not None
    assert candidate.event_date == "2026-05-24"
    assert candidate.start_at == "2026-05-24T08:00:00+07:00"
    assert candidate.end_at == "2026-05-24T10:00:00+07:00"
    assert "sharing session" in candidate.title.lower()
    assert "kalender" not in candidate.title.lower()
