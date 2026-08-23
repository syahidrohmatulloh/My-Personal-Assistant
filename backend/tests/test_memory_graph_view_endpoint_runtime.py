import pytest

from app.routers import memory_review


class FakeExecuteResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.operations = []

    def select(self, fields):
        self.operations.append(("select", fields))
        return self

    def eq(self, column, value):
        self.operations.append(("eq", column, value))
        return self

    def order(self, field, desc=False):
        self.operations.append(("order", field, desc))
        return self

    def range(self, start, end):
        self.operations.append(("range", start, end))
        return self

    def execute(self):
        self.operations.append(("execute",))
        return FakeExecuteResult(self.rows)


class FakeSupabase:
    def __init__(self, rows):
        self.table_name = None
        self.query = FakeQuery(rows)

    def table(self, name):
        self.table_name = name
        return self.query


def sample_rows():
    return [
        {
            "id": "mem-1",
            "content": "User child name is Zahra",
            "kind": "fact",
            "category": "relationships",
            "structured_field": "child_name",
            "structured_value": "Zahra",
            "source": "auto",
            "source_conversation_id": "conv-secret",
            "evidence": ["secret evidence text"],
            "status": "active",
            "archived": False,
            "superseded": False,
            "deleted_at": None,
        }
    ]


@pytest.mark.asyncio
async def test_graph_view_runtime_requires_pin_and_fetches_user_scoped_rows(monkeypatch):
    pin_calls = []
    fake_supabase = FakeSupabase(sample_rows())

    async def fake_require_valid_pin(*, user_id, pin):
        pin_calls.append((user_id, pin))

    monkeypatch.setattr(memory_review.memory_pin, "require_valid_pin", fake_require_valid_pin)
    monkeypatch.setattr(memory_review, "get_supabase", lambda: fake_supabase)

    result = await memory_review.memory_graph_view(
        body=memory_review.MemoryPinIn(pin="123456"),
        user_id="user-123",
    )

    assert pin_calls == [("user-123", "123456")]
    assert fake_supabase.table_name == "memories"
    assert ("eq", "user_id", "user-123") in fake_supabase.query.operations
    assert ("execute",) in fake_supabase.query.operations
    assert result["read_only"] is True
    assert result["runtime_retrieval_change"] is False
    assert result["schema_migration"] is False
    assert result["summary"]["visible_note_count"] == 1

    rendered = str(result)
    assert "conv-secret" not in rendered
    assert "secret evidence text" not in rendered


@pytest.mark.asyncio
async def test_graph_view_runtime_stops_before_db_when_pin_invalid(monkeypatch):
    async def fake_require_valid_pin(*, user_id, pin):
        raise memory_review.HTTPException(status_code=401, detail="bad pin")

    def fail_get_supabase():
        raise AssertionError("DB must not be touched when PIN is invalid")

    monkeypatch.setattr(memory_review.memory_pin, "require_valid_pin", fake_require_valid_pin)
    monkeypatch.setattr(memory_review, "get_supabase", fail_get_supabase)

    with pytest.raises(memory_review.HTTPException) as excinfo:
        await memory_review.memory_graph_view(
            body=memory_review.MemoryPinIn(pin="000000"),
            user_id="user-123",
        )

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_graph_view_runtime_maps_db_failure_to_500(monkeypatch):
    async def fake_require_valid_pin(*, user_id, pin):
        return None

    def broken_get_supabase():
        raise RuntimeError("boom")

    monkeypatch.setattr(memory_review.memory_pin, "require_valid_pin", fake_require_valid_pin)
    monkeypatch.setattr(memory_review, "get_supabase", broken_get_supabase)

    with pytest.raises(memory_review.HTTPException) as excinfo:
        await memory_review.memory_graph_view(
            body=memory_review.MemoryPinIn(pin="123456"),
            user_id="user-123",
        )

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "Failed to load memory graph view."
