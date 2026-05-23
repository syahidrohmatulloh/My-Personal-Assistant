from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_time_of_day_grounding_strict_rule_exists():
    assert "## Time-of-day grounding — strict rule" in CHAT
    assert "Before using any time-of-day label" in CHAT
    assert "Never infer time-of-day from conversational cues" in CHAT
    assert "If browser-provided user local time is unavailable, ask the user" in CHAT
    assert "This rule applies to greetings, reactions" in CHAT
    assert "Browser-provided user local time available this turn" in CHAT


def test_time_of_day_rule_uses_raw_client_context_local_time():
    assert "local_time_available = bool(" in CHAT
    assert 'raw_client_context.get("local_time")' in CHAT
    assert "render_client_time_context(raw_client_context, profile)" in CHAT
