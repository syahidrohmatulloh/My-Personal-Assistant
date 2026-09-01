import asyncio

from app.services import calendar_confirmation_actions
from app.services import temporal_calendar_policy


def test_pending_relevance_is_conversation_safe():
    assert temporal_calendar_policy.should_check_pending_confirmation("iya")
    assert not temporal_calendar_policy.allows_cross_conversation_pending_reference("iya")
    assert not temporal_calendar_policy.should_check_pending_confirmation(
        "restoran Jepang yang kemarin apa?"
    )
    assert temporal_calendar_policy.allows_cross_conversation_pending_reference(
        "agenda yang tadi masukin aja"
    )
    assert temporal_calendar_policy.should_check_pending_confirmation("jam 3 aja")
    assert not temporal_calendar_policy.should_check_pending_confirmation(
        "besok katanya hujan jam 4"
    )


def test_unrelated_turn_does_not_load_pending_context(monkeypatch):
    calls = []

    async def fake_load(**kwargs):
        calls.append(kwargs)
        return [{"content": "pending"}]

    monkeypatch.setattr(
        calendar_confirmation_actions,
        "load_pending_calendar_suggestions",
        fake_load,
    )

    result = asyncio.run(
        calendar_confirmation_actions.render_pending_calendar_confirmation_context(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message="restoran Jepang yang kemarin apa?",
        )
    )

    assert result is None
    assert calls == []


def test_plain_confirmation_uses_same_conversation_only(monkeypatch):
    calls = []

    async def fake_load(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(
        calendar_confirmation_actions,
        "load_pending_calendar_suggestions",
        fake_load,
    )

    result = asyncio.run(
        calendar_confirmation_actions.render_pending_calendar_confirmation_context(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message="iya",
        )
    )

    assert result is None
    assert calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conversation-1",
            "limit": 1,
        }
    ]


def test_explicit_reference_can_use_cross_conversation_fallback(monkeypatch):
    calls = []

    async def fake_load(**kwargs):
        calls.append(kwargs)
        if kwargs.get("conversation_id"):
            return []
        return [
            {
                "content": "Calendar reminder",
                "calendar_event_title": "Review",
                "calendar_event_date": "2026-09-02",
                "calendar_event_start_at": None,
                "calendar_event_end_at": None,
            }
        ]

    monkeypatch.setattr(
        calendar_confirmation_actions,
        "load_pending_calendar_suggestions",
        fake_load,
    )

    result = asyncio.run(
        calendar_confirmation_actions.render_pending_calendar_confirmation_context(
            user_id="user-1",
            conversation_id="conversation-2",
            user_message="agenda yang tadi masukin aja",
        )
    )

    assert result
    assert calls == [
        {
            "user_id": "user-1",
            "conversation_id": "conversation-2",
            "limit": 1,
        },
        {"user_id": "user-1", "limit": 1},
    ]
