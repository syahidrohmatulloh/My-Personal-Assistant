from datetime import date

from app.services.calendar_candidate_extractor import extract_candidate, has_calendar_signal


def test_siang_ini_explicit_calendar_request_becomes_today_candidate():
    message = "oke, nanti aku coba. Btw masukin ke kalender aku jam 12.30 siang ini mau ada acara Bowling sama Mandiri Club di Agora Spin City ya"

    assert has_calendar_signal(message) is True

    candidate = extract_candidate(
        text=message,
        base_date=date(2026, 5, 23),
        timezone_offset_minutes=420,
    )

    assert candidate is not None
    assert candidate.event_date == "2026-05-23"
    assert candidate.start_at == "2026-05-23T12:30:00+07:00"
    assert candidate.end_at == "2026-05-23T13:30:00+07:00"
    assert "bowling" in candidate.title.lower()
    assert "kalender" not in candidate.title.lower()


def test_malam_ini_time_range_calendar_request_becomes_today_candidate():
    message = "beb masukin kalender ya, malam ini jam 7-9 mau gym di Paradigm SCBD"

    assert has_calendar_signal(message) is True

    candidate = extract_candidate(
        text=message,
        base_date=date(2026, 5, 23),
        timezone_offset_minutes=420,
    )

    assert candidate is not None
    assert candidate.event_date == "2026-05-23"
    assert candidate.start_at == "2026-05-23T19:00:00+07:00"
    assert candidate.end_at == "2026-05-23T21:00:00+07:00"
