from pathlib import Path


CHAT_SOURCE = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_chat_keeps_calendar_runtime_service_imports() -> None:
    assert "calendar_candidate_extractor." in CHAT_SOURCE
    assert "    calendar_candidate_extractor," in CHAT_SOURCE

    assert "calendar_draft_actions." in CHAT_SOURCE
    assert "    calendar_draft_actions," in CHAT_SOURCE

    assert "calendar_confirmation_actions." in CHAT_SOURCE
    assert "    calendar_confirmation_actions," in CHAT_SOURCE


def test_chat_keeps_background_runtime_service_imports() -> None:
    assert "background_extraction_gate.decide" in CHAT_SOURCE
    assert "    background_extraction_gate," in CHAT_SOURCE

    assert "conversation_summary.summarize_conversation" in CHAT_SOURCE
    assert "    conversation_summary," in CHAT_SOURCE


def test_chat_keeps_safe_execute_import_while_direct_supabase_helpers_exist() -> None:
    assert "safe_execute(" in CHAT_SOURCE
    assert "from app.services.supabase_client import get_supabase, safe_execute" in CHAT_SOURCE
