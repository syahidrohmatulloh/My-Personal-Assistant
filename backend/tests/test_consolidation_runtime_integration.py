import asyncio
from pathlib import Path

from app.services import cognitive_runtime
from app.services import memory_consolidation


def test_runtime_delegates_m33_consolidation(monkeypatch):
    calls = []

    async def fake_consolidate(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "version": "M33-v1",
            "merged": 1,
        }

    monkeypatch.setattr(
        memory_consolidation,
        "consolidate_and_persist",
        fake_consolidate,
    )

    runtime = (
        cognitive_runtime
        .create_cognitive_runtime()
    )

    result = asyncio.run(
        runtime.consolidate_memories(
            user_id="user-1",
            days=30,
        )
    )

    assert result["version"] == "M33-v1"
    assert calls == [
        {
            "user_id": "user-1",
            "days": 30,
        }
    ]


def test_m33_services_do_not_depend_on_runtime_or_trace():
    for path_text in (
        "app/services/memory_consolidation.py",
        "app/services/memory_consolidation_scheduler.py",
    ):
        source = Path(
            path_text
        ).read_text(
            encoding="utf-8"
        )

        assert "cognitive_runtime" not in source
        assert "cognitive_trace" not in source


def test_main_owns_scheduler_lifecycle_wiring():
    source = Path(
        "app/main.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "memory_consolidation_scheduler"
        in source
    )

    assert (
        "await memory_consolidation_scheduler."
        "start_memory_consolidation_scheduler()"
        in source
    )

    assert (
        "await memory_consolidation_scheduler."
        "stop_memory_consolidation_scheduler()"
        in source
    )


def test_runtime_version_remains_m31d_contract():
    source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        'COGNITIVE_RUNTIME_VERSION = "M31D-v1"'
        in source
    )
