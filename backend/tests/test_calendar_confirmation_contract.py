from pathlib import Path

CONTEXT = Path("app/services/cognitive_turn_context.py").read_text(encoding="utf-8")
EXTRACTOR = Path("app/services/calendar_candidate_extractor.py").read_text(encoding="utf-8")


def test_current_turn_calendar_contract_requires_confirmation():
    assert "Calendar scheduling contract for this user turn" in CONTEXT
    assert "ask for confirmation before adding anything" in CONTEXT
    assert "Mau aku masukin ke Calendar?" in CONTEXT
    assert "Do not say the event has already been prepared" in CONTEXT
    assert "Confirmation should happen in chat" in CONTEXT


def test_old_calendar_prepared_candidate_phrases_are_removed_from_chat_prompt():
    assert "Aku siapkan sebagai kandidat calendar" not in CONTEXT
    assert "Aku siapkan sebagai kandidat kalender" not in CONTEXT
    assert "Cek di fitur Calendar untuk konfirmasi dan simpan" not in CONTEXT
    assert "do NOT use the phrase \'Calendar event\'" not in CONTEXT
    assert "Pending schedule suggestions are internal only" in CONTEXT or "do not expose implementation names" in CONTEXT


def test_dedupe_uses_time_match_even_when_title_differs():
    assert "_same_calendar_time_for_dedupe" in EXTRACTOR
    assert "slightly different title" in EXTRACTOR
    assert "calendar_event_status.in.(confirmed_local,synced_google)" in EXTRACTOR
