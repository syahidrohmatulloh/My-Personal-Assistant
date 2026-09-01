from datetime import date

import pytest

from app.services import (
    calendar_candidate_extractor,
    chat_calendar_helpers,
)


NEGATED_EVENT_MESSAGES = (
    "engga ada meeting sama direksi besok",
    "enggak ada meeting sama direksi besok",
    "nggak ada meeting besok",
    "ngga ada rapat besok",
    "gak ada jadwal besok",
    "ga ada agenda besok",
    "tidak ada appointment besok",
    "belum ada meeting besok",
    "aku tidak punya meeting besok",
    "saya ga punya jadwal besok",
    "meeting sama direksi besok nggak jadi",
    "rapat direksi besok dibatalkan",
    "jadwal aku besok kosong",
    "agenda besok kosong",
    "no meeting tomorrow",
    "there is no meeting tomorrow",
    "there's no meeting tomorrow",
    "i don't have a meeting tomorrow",
    "i have no meeting tomorrow",
    "meeting tomorrow is cancelled",
)


@pytest.mark.parametrize(
    "message",
    NEGATED_EVENT_MESSAGES,
)
def test_negated_event_is_not_calendar_candidate(
    message: str,
) -> None:
    assert (
        calendar_candidate_extractor
        .is_calendar_absence_statement(
            message
        )
        is True
    )

    assert (
        calendar_candidate_extractor
        .has_calendar_signal(
            message
        )
        is False
    )

    assert (
        calendar_candidate_extractor
        .should_attempt_calendar_candidate_extraction(
            message
        )
        is False
    )

    assert (
        chat_calendar_helpers
        .should_hard_gate_calendar_candidate(
            message
        )
        is False
    )

    candidate = (
        calendar_candidate_extractor
        .extract_candidate(
            text=message,
            base_date=date(
                2026,
                9,
                1,
            ),
            timezone_offset_minutes=420,
        )
    )

    assert candidate is None


def test_reported_screenshot_phrase_is_blocked() -> None:
    message = (
        "engga ada meeting sama direksi besok"
    )

    assert (
        calendar_candidate_extractor
        .is_calendar_absence_statement(
            message
        )
        is True
    )

    assert (
        chat_calendar_helpers
        .should_hard_gate_calendar_candidate(
            message
        )
        is False
    )


@pytest.mark.parametrize(
    "message",
    (
        "ada meeting sama direksi besok",
        "meeting sama direksi besok jam 10",
        "jangan lupa meeting sama direksi besok jam 10",
        "masukin ke kalender meeting direksi besok jam 10",
        (
            "nggak ada masalah, meeting sama direksi "
            "besok jam 10 tetap jadi"
        ),
        (
            "aku nggak mau telat meeting sama direksi "
            "besok jam 10"
        ),
    ),
)
def test_positive_calendar_messages_remain_schedulable(
    message: str,
) -> None:
    assert (
        calendar_candidate_extractor
        .is_calendar_absence_statement(
            message
        )
        is False
    )

    assert (
        calendar_candidate_extractor
        .has_calendar_signal(
            message
        )
        is True
    )

    assert (
        chat_calendar_helpers
        .should_hard_gate_calendar_candidate(
            message
        )
        is True
    )


@pytest.mark.asyncio
async def test_negation_guard_stops_llm_fallback_and_persistence(
    monkeypatch,
) -> None:
    async def forbidden_intent_fallback(
        **kwargs,
    ):
        raise AssertionError(
            "LLM Calendar intent fallback "
            "must not run for absence statements"
        )

    monkeypatch.setattr(
        calendar_candidate_extractor
        .calendar_intent,
        "extract_calendar_intent_draft",
        forbidden_intent_fallback,
    )

    result = await (
        calendar_candidate_extractor
        .extract_and_persist(
            user_id="user-1",
            conversation_id="conv-1",
            user_message=(
                "engga ada meeting sama direksi besok"
            ),
            client_context={
                "local_date": "2026-09-01",
                "timezone_offset_minutes": 420,
            },
            recent_messages=[],
        )
    )

    assert result == {
        "candidate": False,
        "saved": False,
        "reason": "calendar_absence_statement",
    }
