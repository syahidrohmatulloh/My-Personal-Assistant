from pathlib import Path

CALENDAR_INTENT = Path("app/services/calendar_intent.py").read_text(encoding="utf-8")


def test_calendar_intent_uses_project_claude_client_factory():
    assert "from app.services.claude import get_claude" in CALENDAR_INTENT
    assert "return get_claude()" in CALENDAR_INTENT
    assert "Could not locate get_claude client factory" not in CALENDAR_INTENT
