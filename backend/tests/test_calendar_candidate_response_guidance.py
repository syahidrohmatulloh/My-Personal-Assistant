from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_calendar_candidate_response_guidance_is_in_volatile_context():
    assert "Calendar Candidate capability state — authoritative" in CHAT
    assert "calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(body.message)" in CHAT
    assert "Memories → Calendar" in CHAT
    assert "Do not claim the event is already created in Google Calendar" in CHAT
    assert "Do not say you cannot help with calendar handling" in CHAT
