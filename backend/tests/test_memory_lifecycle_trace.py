import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.services import memory


def test_retrieve_relevant_logs_safe_lifecycle_trace_without_content(monkeypatch, caplog) -> None:
    old = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()

    async def fake_embed_query(_text: str):
        return [0.1, 0.2]

    class FakeRpc:
        def execute(self):
            return type(
                "Result",
                (),
                {
                    "data": [
                        {
                            "id": "active-old",
                            "content": "SECRET active memory content",
                            "similarity": 0.92,
                            "confidence": 0.90,
                            "created_at": old,
                            "category": "preferences",
                        },
                        {
                            "id": "archived",
                            "content": "SECRET archived memory content",
                            "similarity": 0.99,
                            "confidence": 0.99,
                            "archived": True,
                            "category": "preferences",
                        },
                    ]
                },
            )()

    class FakeSupabase:
        def rpc(self, *_args, **_kwargs):
            return FakeRpc()

    monkeypatch.setattr(memory, "embed_query", fake_embed_query)
    monkeypatch.setattr(memory, "get_supabase", lambda: FakeSupabase())

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        result = asyncio.run(
            memory.retrieve_relevant(
                "user-123456",
                "ingatkan aku istirahat",
                limit=12,
            )
        )

    assert len(result) == 1
    logs = caplog.text

    assert "memory lifecycle trace:" in logs
    assert "memory_lifecycle:" in logs
    assert "total=2" in logs
    assert "active=1" in logs
    assert "hidden=1" in logs
    assert "stale=1" in logs
    assert "returned=1" in logs

    assert "SECRET" not in logs
    assert "ingatkan aku istirahat" not in logs


def test_active_memory_filter_delegates_to_lifecycle_governance() -> None:
    import inspect

    source = inspect.getsource(memory._mi_is_active_memory)

    assert "is_retrievable_memory" in source
