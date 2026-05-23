from datetime import date
from pathlib import Path

from app.services.calendar_candidate_extractor import extract_candidate, has_calendar_signal


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_chat_forces_calendar_candidate_when_extractor_signal_matches():
    assert "calendar_candidate_extractor.has_calendar_signal(user_message)" in CHAT
    assert "calendar_candidate_extractor.extract_and_persist" in CHAT
    assert "client_context=client_context" in CHAT


def test_exact_user_calendar_request_becomes_candidate():
    message = "masukin ke kalender aku jam 12.30 siang ini mau ada acara Bowling sama Mandiri Club di Agora Spin City ya"

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
