from pathlib import Path

CONTEXT = Path("app/services/cognitive_turn_context.py").read_text(encoding="utf-8")


def test_calendar_event_draft_response_guidance_is_in_volatile_context():
    assert "Calendar event capability state — authoritative" in CONTEXT
    assert "is_calendar_candidate_turn = (" in CONTEXT
    assert "temporal_calendar_policy" in CONTEXT
    assert "assess_calendar_semantics(" in CONTEXT
    assert "not is_calendar_draft_action_turn" in CONTEXT
    assert "Confirmation should happen in chat" in CONTEXT
    assert "Do not claim the event is already created in Google Calendar" in CONTEXT
    assert "Do not say you cannot help with calendar handling" in CONTEXT
    assert "Aku catat ke Calendar ya beb" in CONTEXT or "aku catat" in CONTEXT.lower()
    assert "is_calendar_candidate_turn = (" in CONTEXT
    assert "not is_calendar_draft_action_turn" in CONTEXT
    assert "Never infer Calendar action success from user wording alone" in CONTEXT
    assert "If an authoritative Calendar action result is present" in CONTEXT
    assert "Without an authoritative success result" in CONTEXT


def test_calendar_user_facing_language_rule_blocks_old_candidate_wording():
    assert "Calendar user-facing language rule — strict" in CONTEXT
    assert "Never use the phrases" in CONTEXT
    assert "Calendar Candidate capability state" not in CONTEXT
    assert "Aku siapkan ini sebagai Calendar Candidate" not in CONTEXT
    assert "Preferred Indonesian wording: Aku siapkan ini sebagai Calendar Candidate" not in CONTEXT
    assert "kandidat calendar" not in CONTEXT
    assert "kandidat kalender" not in CONTEXT
