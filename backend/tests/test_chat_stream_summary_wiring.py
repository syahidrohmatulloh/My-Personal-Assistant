from pathlib import Path


def test_chat_stream_keeps_conversation_summary_service_imported() -> None:
    source = Path("app/routers/chat.py").read_text(encoding="utf-8")

    assert "conversation_summary.summarize_conversation" in source
    assert "    conversation_summary," in source
