from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_pending_calendar_context_does_not_use_uninitialized_conversation_id():
    assert "render_pending_calendar_confirmation_context" in CHAT
    assert 'conversation_id=getattr(body, "conversation_id", None)' in CHAT


def test_pending_calendar_context_no_longer_uses_bare_conversation_id_in_chat_setup():
    marker = "pending_calendar_confirmation_context = await calendar_confirmation_actions.render_pending_calendar_confirmation_context"
    start = CHAT.index(marker)
    block = CHAT[start: start + 220]
    assert "conversation_id=conversation_id" not in block
