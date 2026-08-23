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

def test_chat_stream_keeps_memory_background_wiring() -> None:
    assert "background_extraction_gate.decide" in CHAT_SOURCE
    assert "add_safe_background_task" in CHAT_SOURCE

    assert "memory.extract_and_save" in CHAT_SOURCE
    assert "    memory," in CHAT_SOURCE

    assert "memory_intelligence.extract_and_persist" in CHAT_SOURCE
    assert "    memory_intelligence," in CHAT_SOURCE

    assert "mood_memory_feedback.extract_and_persist" in CHAT_SOURCE
    assert "    mood_memory_feedback," in CHAT_SOURCE

    assert "relationship_memory.extract_and_persist" in CHAT_SOURCE
    assert "    relationship_memory," in CHAT_SOURCE

    assert "goal_intelligence.extract_and_persist" in CHAT_SOURCE
    assert "    goal_intelligence," in CHAT_SOURCE


def test_chat_stream_keeps_calendar_and_proactive_background_wiring() -> None:
    assert "calendar_confirmation_actions.apply_calendar_confirmation_decision" in CHAT_SOURCE
    assert "calendar_draft_actions.create_google_calendar_event_from_chat" in CHAT_SOURCE
    assert "calendar_candidate_extractor.extract_and_persist" in CHAT_SOURCE

    assert "proactive_nudges.should_attempt_proactive_nudge" in CHAT_SOURCE
    assert "proactive_nudges.schedule_from_chat" in CHAT_SOURCE
    assert "    proactive_nudges," in CHAT_SOURCE


def test_chat_stream_keeps_summary_and_title_background_wiring() -> None:
    assert "conversation_summary.summarize_conversation" in CHAT_SOURCE
    assert "    conversation_summary," in CHAT_SOURCE

    assert "add_safe_background_task(background_tasks," in CHAT_SOURCE
    assert "_generate_title" in CHAT_SOURCE
    assert "async def _generate_title(" in CHAT_SOURCE
    assert "title generation failed" in CHAT_SOURCE
