from pathlib import Path

from app.services import background_extraction_gate
from app.services import calendar_candidate_extractor


CHAT_SOURCE = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_self_regulation_preference_is_not_calendar_candidate() -> None:
    message = "Aliyya, ke depan kalau aku tiba tiba marah, kamu ingetin aku aja ya supaya ga marah"

    assert calendar_candidate_extractor.looks_like_self_regulation_memory_preference(message) is True
    assert calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(message) is False


def test_self_regulation_preference_routes_to_memory_not_calendar_background() -> None:
    message = "Aliyya, ke depan kalau aku tiba tiba marah, kamu ingetin aku aja ya supaya ga marah"

    decision = background_extraction_gate.decide(
        user_message=message,
        assistant_response="",
        recent_messages=[],
        is_first_message=False,
    )

    assert decision.run_memory_intelligence is True
    assert decision.run_calendar_candidate_extraction is False


def test_chat_hard_gate_has_self_regulation_guard() -> None:
    assert "looks_like_self_regulation_memory_preference(user_message)" in CHAT_SOURCE


def test_real_calendar_reminder_is_not_blocked_by_self_regulation_guard() -> None:
    message = "Tolong ingetin aku besok jam 9 untuk meeting dengan Andi"

    assert calendar_candidate_extractor.looks_like_self_regulation_memory_preference(message) is False
