from datetime import date

from app.services.calendar_candidate_extractor import (
    extract_candidate,
    has_calendar_signal,
)


def test_detects_indonesian_meeting_with_time():
    assert has_calendar_signal("besok jam 3 sore meeting sama GH Risk bahas Indosat")


def test_extracts_tomorrow_afternoon_meeting():
    cand = extract_candidate(
        text="besok jam 3 sore meeting sama GH Risk bahas Indosat",
        base_date=date(2026, 5, 21),
        timezone_offset_minutes=420,
    )

    assert cand is not None
    assert cand.event_date == "2026-05-22"
    assert cand.start_at == "2026-05-22T15:00:00+07:00"
    assert cand.end_at == "2026-05-22T16:00:00+07:00"
    assert cand.all_day is False
    assert "due_date=2026-05-22" in cand.structured_value


def test_extracts_lusa_all_day_presentation():
    cand = extract_candidate(
        text="lusa presentasi pipeline ke direktur",
        base_date=date(2026, 5, 21),
    )

    assert cand is not None
    assert cand.event_date == "2026-05-23"
    assert cand.start_at is None
    assert cand.all_day is True


def test_extracts_english_pm_call():
    cand = extract_candidate(
        text="tomorrow 3 PM call with John",
        base_date=date(2026, 5, 21),
        timezone_offset_minutes=420,
    )

    assert cand is not None
    assert cand.event_date == "2026-05-22"
    assert cand.start_at == "2026-05-22T15:00:00+07:00"


def test_ignores_regular_chat():
    assert has_calendar_signal("aku suka mangga") is False
