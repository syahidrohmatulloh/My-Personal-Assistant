from app.services.calendar_candidate_extractor import (
    has_calendar_signal,
    should_attempt_calendar_candidate_extraction,
)
from pathlib import Path


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_contextual_calendar_candidate_followup_triggers_attempt():
    message = "tolong masukan ulang ke kalender candidate yang jemput aneira"

    assert has_calendar_signal(message) is False
    assert should_attempt_calendar_candidate_extraction(message) is True


def test_explicit_calendar_without_date_can_attempt_haiku_fallback():
    message = "tolong masukkan ke kalender ya"

    assert should_attempt_calendar_candidate_extraction(message) is True


def test_chat_uses_broader_calendar_attempt_trigger():
    assert "_should_hard_gate_calendar_candidate(body.message)" in CHAT
    assert "calendar_candidate_hard_gate" in CHAT
    assert "calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(raw)" in CHAT
    assert "calendar_candidate_extractor.extract_and_persist" in CHAT
