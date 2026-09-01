from pathlib import Path

CONTEXT = Path("app/services/cognitive_turn_context.py").read_text(encoding="utf-8")


def test_time_of_day_grounding_strict_rule_exists():
    assert "## Time-of-day grounding — strict rule" in CONTEXT
    assert "Before using any time-of-day label" in CONTEXT
    assert "Never infer time-of-day from conversational cues" in CONTEXT
    assert "If browser-provided user local time is unavailable, ask the user" in CONTEXT
    assert "This rule applies to greetings, reactions" in CONTEXT
    assert "Browser-provided user local time available this turn" in CONTEXT


def test_time_of_day_rule_uses_raw_client_context_local_time():
    assert "local_time_available = bool(" in CONTEXT
    assert 'raw_client_context.get("local_time")' in CONTEXT
    assert "render_client_time_context(raw_client_context, profile)" in CONTEXT
