from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
EXTRACTOR = Path("app/services/calendar_candidate_extractor.py").read_text(encoding="utf-8")


def test_current_turn_calendar_contract_requires_confirmation():
    assert "Calendar scheduling contract for this user turn" in CHAT
    assert "ask for confirmation before adding anything" in CHAT
    assert "Mau aku masukin ke Calendar?" in CHAT
    assert "Do not say the event has already been prepared" in CHAT
    assert "Confirmation should happen in chat" in CHAT


def test_old_calendar_prepared_candidate_phrases_are_removed_from_chat_prompt():
    assert "Aku siapkan sebagai kandidat calendar" not in CHAT
    assert "Aku siapkan sebagai kandidat kalender" not in CHAT
    assert "Cek di fitur Calendar untuk konfirmasi dan simpan" not in CHAT
    assert "do NOT use the phrase \'Calendar event\'" not in CHAT
    assert "Pending schedule suggestions are internal only" in CHAT or "do not expose implementation names" in CHAT


def test_dedupe_uses_time_match_even_when_title_differs():
    assert "_same_calendar_time_for_dedupe" in EXTRACTOR
    assert "slightly different title" in EXTRACTOR
    assert "calendar_event_status.in.(confirmed_local,synced_google)" in EXTRACTOR
