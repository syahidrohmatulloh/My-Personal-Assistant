from app.services import calendar_intent
from app.services.calendar_candidate_extractor import _candidate_from_intent_draft
from pathlib import Path


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
EXTRACTOR = Path("app/services/calendar_candidate_extractor.py").read_text(encoding="utf-8")


def test_calendar_intent_normalises_valid_draft():
    draft = calendar_intent.normalise_calendar_intent_draft(
        {
            "is_calendar_candidate": True,
            "title": "Jemput Aneira — Lomba Dance",
            "event_date": "2026-05-23",
            "start_at": "2026-05-23T14:00:00+07:00",
            "end_at": None,
            "all_day": False,
            "location": "Gajah Mada Plaza",
            "confidence": 0.82,
            "reason": "explicit_calendar_request_with_context",
        }
    )

    assert draft is not None
    assert draft["event_date"] == "2026-05-23"
    assert draft["start_at"] == "2026-05-23T14:00:00+07:00"
    assert draft["end_at"] == "2026-05-23T15:00:00+07:00"
    assert draft["location"] == "Gajah Mada Plaza"


def test_candidate_from_intent_draft_keeps_location_in_content():
    draft = {
        "title": "Jemput Aneira — Lomba Dance",
        "event_date": "2026-05-23",
        "start_at": "2026-05-23T14:00:00+07:00",
        "end_at": "2026-05-23T15:00:00+07:00",
        "all_day": False,
        "location": "Gajah Mada Plaza",
        "confidence": 0.82,
        "reason": "haiku_calendar_intent",
    }

    candidate = _candidate_from_intent_draft(draft, "tolong masukkan ke kalender")

    assert candidate is not None
    assert candidate.title == "Jemput Aneira — Lomba Dance"
    assert candidate.event_date == "2026-05-23"
    assert candidate.start_at == "2026-05-23T14:00:00+07:00"
    assert "Gajah Mada Plaza" in candidate.content
    assert "location=Gajah Mada Plaza" in candidate.structured_value


def test_chat_passes_recent_messages_to_calendar_intent_fallback():
    assert "recent_messages=[" in CHAT
    assert "calendar_candidate_extractor.extract_and_persist" in CHAT


def test_extractor_has_haiku_fallback_wiring():
    assert "calendar_intent.extract_calendar_intent_draft" in EXTRACTOR
    assert "_candidate_from_intent_draft" in EXTRACTOR
