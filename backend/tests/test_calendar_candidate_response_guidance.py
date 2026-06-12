from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_calendar_event_draft_response_guidance_is_in_volatile_context():
    assert "Calendar event capability state — authoritative" in CHAT
    assert "is_calendar_candidate_turn = (" in CHAT
    assert "calendar_candidate_extractor.should_attempt_calendar_candidate_extraction" in CHAT
    assert "not is_calendar_draft_action_turn" in CHAT
    assert "Confirmation should happen in chat" in CHAT
    assert "Do not claim the event is already created in Google Calendar" in CHAT
    assert "Do not say you cannot help with calendar handling" in CHAT
    assert "Aku catat ke Calendar ya beb" in CHAT or "aku catat" in CHAT.lower()
    assert "is_calendar_candidate_turn = (" in CHAT
    assert "not is_calendar_draft_action_turn" in CHAT
    assert "Never infer Calendar action success from user wording alone" in CHAT
    assert "If an authoritative Calendar action result is present" in CHAT
    assert "Without an authoritative success result" in CHAT


def test_calendar_user_facing_language_rule_blocks_old_candidate_wording():
    assert "Calendar user-facing language rule — strict" in CHAT
    assert "Never use the phrases" in CHAT
    assert "Calendar Candidate capability state" not in CHAT
    assert "Aku siapkan ini sebagai Calendar Candidate" not in CHAT
    assert "Preferred Indonesian wording: Aku siapkan ini sebagai Calendar Candidate" not in CHAT
    assert "kandidat calendar" not in CHAT
    assert "kandidat kalender" not in CHAT
