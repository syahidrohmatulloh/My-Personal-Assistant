from pathlib import Path

import pytest

from app.services import background_extraction_gate
from app.services import calendar_candidate_extractor


CHAT_SOURCE = Path("app/routers/chat.py").read_text(encoding="utf-8")
CALENDAR_HELPERS_SOURCE = Path("app/services/chat_calendar_helpers.py").read_text(encoding="utf-8")


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
    assert "looks_like_self_regulation_memory_preference(user_message)" in CALENDAR_HELPERS_SOURCE


@pytest.mark.parametrize(
    "message",
    [
        "ke depan kalau aku tiba-tiba marah, kamu ingetin aku aja buat tarik napas",
        "kalau aku lagi cemas, remind me to slow down",
        "mulai sekarang kalau aku overthinking tolong ingetin aku istirahat",
        "kalau aku insecure lagi, ingetin aku bahwa aku cukup",
        "when i feel down, remind me to reach out",
        "kalau aku burnout, ingetin aku ambil cuti",
        "going forward kalau aku galau, ingetin aku journaling",
        "from now on when i am overwhelmed remind me to pause",
        "kalau lagi feeling low, tolong ingetin aku tidur lebih cepat",
        "kalau mood lagi drop, ingetin aku jangan impulsif",
        "pas aku anxious, remind me to breathe first",
    ],
)
def test_broadened_self_regulation_preferences_route_to_memory(message: str) -> None:
    assert calendar_candidate_extractor.looks_like_self_regulation_memory_preference(message) is True
    assert calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(message) is False

    decision = background_extraction_gate.decide(
        user_message=message,
        assistant_response="",
        recent_messages=[],
        is_first_message=False,
    )
    assert decision.run_memory_intelligence is True
    assert decision.run_calendar_candidate_extraction is False


@pytest.mark.parametrize(
    "message",
    [
        "ingetin aku meeting jam 5 sore",
        "besok ingetin aku telepon dokter",
        "ingetin aku golf tanggal 14 juni jam 5",
        "ingetin aku bayar tagihan hari ini",
        "meeting sama tim marketing besok pagi",
    ],
)
def test_real_reminders_and_events_stay_calendar(message: str) -> None:
    assert calendar_candidate_extractor.looks_like_self_regulation_memory_preference(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "kalau server down, ingetin aku cek infra",
        "kalau saham drop, ingetin aku cek portfolio",
        "kalau battery low, remind me to charge",
    ],
)
def test_generic_down_drop_low_phrases_are_not_self_regulation(message: str) -> None:
    assert calendar_candidate_extractor.looks_like_self_regulation_memory_preference(message) is False
