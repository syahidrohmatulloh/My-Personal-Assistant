from datetime import datetime, timezone

from app.routers.memories import CreateMemoryIn, MemoryOut


def test_memory_response_accepts_calendar_plan_kind():
    memory = MemoryOut(
        id="memory-1",
        content="User has a scheduled event",
        kind="plan",
        source="auto",
        created_at=datetime.now(timezone.utc),
    )

    assert memory.kind == "plan"


def test_manual_memory_input_accepts_plan_kind():
    memory = CreateMemoryIn(
        content="Prepare materials for Monday meeting",
        kind="plan",
    )

    assert memory.kind == "plan"
