import asyncio
from types import SimpleNamespace

from app.services import chat_calendar_helpers


def test_hard_gate_calendar_candidate_detects_event_with_time() -> None:
    assert chat_calendar_helpers.should_hard_gate_calendar_candidate(
        "meeting sama tim marketing besok pagi"
    ) is True


def test_hard_gate_calendar_candidate_rejects_self_regulation_memory_preference() -> None:
    assert chat_calendar_helpers.should_hard_gate_calendar_candidate(
        "kalau aku overthinking tolong ingetin aku istirahat"
    ) is False


def test_render_calendar_hard_gate_clarification_uses_clean_address_term() -> None:
    text = chat_calendar_helpers.render_calendar_hard_gate_clarification(
        address_term=" beb "
    )

    assert text.startswith(
        "beb, aku belum mau menganggap ini jadwal dulu"
    )
    assert (
        "Kamu sedang cerita/rencana saja"
        in text
    )


def test_clean_calendar_address_term_rejects_unsafe_or_long_values() -> None:
    assert chat_calendar_helpers.clean_calendar_address_term("jangan panggil aku beb") == ""
    assert chat_calendar_helpers.clean_calendar_address_term("x" * 41) == ""
    assert chat_calendar_helpers.clean_calendar_address_term(" Syahid! ") == "Syahid"


def test_load_calendar_address_term_returns_empty_in_chief_of_staff_mode() -> None:
    result = asyncio.run(
        chat_calendar_helpers.load_calendar_address_term(
            user_id="user-123456",
            assistant_mode="chief_of_staff",
        )
    )

    assert result == ""


def test_load_calendar_address_term_reads_latest_safe_memory(monkeypatch) -> None:
    def fake_safe_execute(fn):
        return SimpleNamespace(
            data=[
                {"structured_value": " beb "},
                {"structured_value": "Syahid"},
            ]
        )

    monkeypatch.setattr(chat_calendar_helpers, "safe_execute", fake_safe_execute)

    result = asyncio.run(
        chat_calendar_helpers.load_calendar_address_term(
            user_id="user-123456",
            assistant_mode="life_companion",
        )
    )

    assert result == "beb"
