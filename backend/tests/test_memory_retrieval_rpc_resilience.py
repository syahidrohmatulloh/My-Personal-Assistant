import asyncio
import logging

from app.services import memory


def test_retrieve_relevant_returns_empty_on_rpc_failure_without_leaking_content(monkeypatch, caplog) -> None:
    async def fake_embed_query(_text: str):
        return [0.1, 0.2]

    class FakeSupabase:
        def rpc(self, *_args, **_kwargs):
            raise RuntimeError("SECRET user query and memory content should not leak")

    monkeypatch.setattr(memory, "embed_query", fake_embed_query)
    monkeypatch.setattr(memory, "get_supabase", lambda: FakeSupabase())

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        result = asyncio.run(
            memory.retrieve_relevant(
                "user-123456",
                "ingatkan aku istirahat",
                limit=12,
            )
        )

    assert result == []
    logs = caplog.text
    assert "memory retrieval rpc failed:" in logs
    assert "RuntimeError" in logs
    assert "SECRET" not in logs
    assert "ingatkan aku istirahat" not in logs


def test_retrieve_relevant_does_not_call_rpc_when_gate_blocks(monkeypatch) -> None:
    async def fail_embed_query(_text: str):
        raise AssertionError("embed_query should not run for gated public/current query")

    monkeypatch.setattr(memory, "embed_query", fail_embed_query)

    result = asyncio.run(
        memory.retrieve_relevant(
            "user-123456",
            "cuaca besok di jakarta",
            limit=12,
        )
    )

    assert result == []
