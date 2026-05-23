from pathlib import Path

from app.services import calendar_draft_actions

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
SERVICE = Path("app/services/calendar_draft_actions.py").read_text(encoding="utf-8")
INTENT = Path("app/services/calendar_intent.py").read_text(encoding="utf-8")


def test_soft_detail_followup_triggers_calendar_action():
    positives = [
        "boleh dibuat lebih detil hehe",
        "buat lebih detail ya",
        "bikin lebih spesifik",
        "perjelas event yang tadi",
        "detailin jadwal itu",
    ]

    for message in positives:
        assert calendar_draft_actions.is_calendar_draft_action_request(message), message


def test_calendar_user_facing_language_bans_candidate_wording():
    assert "Calendar user-facing language rule — strict" in CHAT
    assert "Never use the phrases" in CHAT
    assert "kandidat calendar" not in CHAT
    assert "kandidat kalender" not in CHAT
    assert "Calendar Candidate capability state" not in CHAT
    assert "Aku siapkan ini sebagai Calendar Candidate" not in CHAT


def test_calendar_action_prompt_knows_detail_update():
    assert "_SOFT_UPDATE_TERMS" in SERVICE
    assert "more detailed/specific/jelas/detil" in SERVICE
    assert "improve title/location using recent context" in SERVICE


def test_calendar_intent_prompt_does_not_use_calendar_candidate_user_wording():
    assert "Calendar Candidate" not in INTENT
    assert "Calendar event draft" in INTENT
