import asyncio

from app.services import memory_consolidation_scheduler


def test_scheduler_is_default_off(monkeypatch):
    monkeypatch.delenv(
        "MEMORY_CONSOLIDATION_SCHEDULER_ENABLED",
        raising=False,
    )

    assert (
        memory_consolidation_scheduler.scheduler_enabled()
        is False
    )


def test_scheduler_interval_has_safe_floor(monkeypatch):
    monkeypatch.setenv(
        "MEMORY_CONSOLIDATION_INTERVAL_MINUTES",
        "5",
    )

    assert (
        memory_consolidation_scheduler
        .scheduler_interval_minutes()
        == 60
    )


def test_cycle_isolates_user_failures(monkeypatch):
    async def fake_users(**_kwargs):
        return [
            "user-1",
            "user-2",
        ]

    calls = []

    async def fake_consolidate(**kwargs):
        calls.append(kwargs["user_id"])
        if kwargs["user_id"] == "user-1":
            raise RuntimeError("boom")

        return {
            "ok": True,
            "merged": 2,
            "candidates": 1,
        }

    monkeypatch.setattr(
        memory_consolidation_scheduler,
        "_load_candidate_user_ids",
        fake_users,
    )
    monkeypatch.setattr(
        memory_consolidation_scheduler
        .memory_consolidation,
        "consolidate_and_persist",
        fake_consolidate,
    )

    result = asyncio.run(
        memory_consolidation_scheduler
        .run_memory_consolidation_cycle_once()
    )

    assert calls == [
        "user-1",
        "user-2",
    ]
    assert result["users_checked"] == 2
    assert result["failed_users"] == 1
    assert result["merged"] == 2
    assert result["ok"] is False


def test_scheduler_status_is_structured():
    status = (
        memory_consolidation_scheduler
        .get_memory_consolidation_scheduler_status()
    )

    assert {
        "enabled",
        "running",
        "interval_minutes",
        "lookback_days",
        "last_started_at",
        "last_finished_at",
        "last_error",
        "last_summary",
    } <= set(status)
