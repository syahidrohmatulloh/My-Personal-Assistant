import asyncio
from types import SimpleNamespace

import pytest

from app.services import briefing


def test_get_or_generate_briefing_returns_existing_without_generation(monkeypatch) -> None:
    existing = {
        "id": "briefing-1",
        "content": "Existing briefing",
        "generated_at": "2026-08-22T00:00:00Z",
        "conversation_id": None,
        "opened_at": None,
    }

    def fake_safe_execute(_fn):
        return SimpleNamespace(data=existing)

    async def fail_generate(_user_id: str):
        raise AssertionError("should not generate when briefing already exists")

    monkeypatch.setattr(briefing, "safe_execute", fake_safe_execute)
    monkeypatch.setattr(briefing, "_generate_briefing_content", fail_generate)

    row = asyncio.run(
        briefing.get_or_generate_briefing(
            user_id="user-123",
            local_date="2026-08-22",
        )
    )

    assert row == existing


def test_get_or_generate_briefing_recovers_duplicate_insert_race(monkeypatch) -> None:
    existing_after_race = {
        "id": "briefing-existing",
        "content": "Existing after race",
        "generated_at": "2026-08-22T00:00:00Z",
        "conversation_id": None,
        "opened_at": None,
    }

    calls = []

    def fake_safe_execute(_fn):
        calls.append(len(calls) + 1)

        if len(calls) == 1:
            return SimpleNamespace(data=None)

        if len(calls) == 2:
            raise Exception(
                "{'message': 'duplicate key value violates unique constraint "
                "\"daily_briefings_user_id_briefing_date_key\"', 'code': '23505'}"
            )

        if len(calls) == 3:
            return SimpleNamespace(data=existing_after_race)

        raise AssertionError("unexpected safe_execute call")

    async def fake_generate(_user_id: str):
        return "Generated briefing"

    monkeypatch.setattr(briefing, "safe_execute", fake_safe_execute)
    monkeypatch.setattr(briefing, "_generate_briefing_content", fake_generate)

    row = asyncio.run(
        briefing.get_or_generate_briefing(
            user_id="user-123",
            local_date="2026-08-22",
        )
    )

    assert row == existing_after_race
    assert calls == [1, 2, 3]


def test_get_or_generate_briefing_reraises_non_duplicate_insert_error(monkeypatch) -> None:
    def fake_safe_execute(_fn):
        fake_safe_execute.calls += 1
        if fake_safe_execute.calls == 1:
            return SimpleNamespace(data=None)
        raise RuntimeError("network exploded")

    fake_safe_execute.calls = 0

    async def fake_generate(_user_id: str):
        return "Generated briefing"

    monkeypatch.setattr(briefing, "safe_execute", fake_safe_execute)
    monkeypatch.setattr(briefing, "_generate_briefing_content", fake_generate)

    with pytest.raises(RuntimeError, match="network exploded"):
        asyncio.run(
            briefing.get_or_generate_briefing(
                user_id="user-123",
                local_date="2026-08-22",
            )
        )
