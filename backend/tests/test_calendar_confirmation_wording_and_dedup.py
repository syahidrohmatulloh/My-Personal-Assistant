from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
EXTRACTOR = Path("app/services/calendar_candidate_extractor.py").read_text(encoding="utf-8")


def test_chat_calendar_guidance_asks_confirmation_not_prepared_candidate():
    assert "Calendar confirmation UX rule — strict" in CHAT
    assert "Mau aku masukin ke Calendar?" in CHAT
    assert "do NOT say it has been prepared" in CHAT
    assert "Aku siapkan sebagai kandidat calendar" not in CHAT
    assert "Aku siapkan sebagai kandidat kalender" not in CHAT
    assert "Cek di fitur Calendar untuk konfirmasi dan simpan" not in CHAT


def test_chat_bans_candidate_language_for_user_facing_calendar():
    assert "Never use user-facing terms" in CHAT
    assert "kandidat calendar" not in CHAT
    assert "kandidat kalender" not in CHAT
    assert "Calendar Candidate" not in CHAT


def test_calendar_extractor_uses_broad_duplicate_check():
    assert "_find_existing_calendar_item" in EXTRACTOR
    assert "_normalise_title_for_dedupe" in EXTRACTOR
    assert "calendar_event_status.in.(confirmed_local,synced_google)" in EXTRACTOR
