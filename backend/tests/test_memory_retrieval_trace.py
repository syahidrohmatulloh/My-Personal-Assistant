import asyncio
import inspect
import logging
from types import SimpleNamespace

from app.services import memory


def test_retrieve_relevant_logs_safe_trace_without_query_or_content(monkeypatch, caplog) -> None:
    async def fake_embed_query(_query: str):
        return [0.1, 0.2, 0.3]

    class FakeRpc:
        def execute(self):
            return SimpleNamespace(
                data=[
                    {
                        "id": "mem-low",
                        "content": "User wants to be reminded to rest when overthinking",
                        "kind": "preference",
                        "category": "preferences",
                        "similarity": 0.4277,
                        "confidence": 0.9,
                        "status": "active",
                        "archived": False,
                        "superseded": False,
                    }
                ]
            )

    class FakeSupabase:
        def rpc(self, *_args, **_kwargs):
            return FakeRpc()

    monkeypatch.setattr(memory, "embed_query", fake_embed_query)
    monkeypatch.setattr(memory, "get_supabase", lambda: FakeSupabase())

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        rows = asyncio.run(
            memory.retrieve_relevant(
                "user-123456789",
                "jangan overthinking",
                limit=10,
            )
        )

    assert [row["id"] for row in rows] == ["mem-low"]

    trace_messages = [
        record.getMessage()
        for record in caplog.records
        if "memory retrieval trace:" in record.getMessage()
    ]

    assert trace_messages
    trace = trace_messages[-1]

    assert "user=user-123" in trace
    assert "gate=personal_cue:self_regulation" in trace
    assert "normalized=True" in trace
    assert "normalize_reason=self_regulation_sparse_query" in trace
    assert "min_similarity=0.40" in trace
    assert "returned=1" in trace

    assert "jangan overthinking" not in trace
    assert "User wants to be reminded" not in trace


def test_retrieve_relevant_does_not_log_trace_when_gate_blocks(monkeypatch, caplog) -> None:
    async def fail_embed_query(_query: str):
        raise AssertionError("embed_query should not run when gate blocks")

    monkeypatch.setattr(memory, "embed_query", fail_embed_query)

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        rows = asyncio.run(
            memory.retrieve_relevant(
                "user-123456789",
                "cuaca besok di jakarta",
                limit=10,
            )
        )

    assert rows == []
    assert "memory retrieval trace:" not in caplog.text



def test_trace_uses_production_visible_logger() -> None:
    source = inspect.getsource(memory.retrieve_relevant)
    assert 'logging.getLogger("uvicorn.error").info' in source



def test_retrieve_relevant_trace_includes_elapsed_ms() -> None:
    import inspect

    source = inspect.getsource(memory.retrieve_relevant)

    assert "elapsed_ms=%.1f" in source
    assert "time.perf_counter()" in source
    assert "memory retrieval rpc failed:" in source
