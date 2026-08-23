import asyncio
import logging

from app.services import conversation_summary


def test_retrieve_related_summaries_returns_empty_on_rpc_failure_without_leaking_content(monkeypatch, caplog) -> None:
    async def fake_embed_query(_text: str):
        return [0.1, 0.2]

    def fake_safe_execute(_fn):
        raise RuntimeError("SECRET summary text should not leak")

    monkeypatch.setattr(conversation_summary, "embed_query", fake_embed_query)
    monkeypatch.setattr(conversation_summary, "safe_execute", fake_safe_execute)

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        result = asyncio.run(
            conversation_summary.retrieve_related_summaries(
                user_id="user-123456",
                query_text="siapa nama anakku?",
                exclude_conversation_id="convo-1",
                limit=6,
            )
        )

    assert result == []
    logs = caplog.text
    assert "summary retrieval rpc failed:" in logs
    assert "RuntimeError" in logs
    assert "SECRET" not in logs
    assert "siapa nama anakku" not in logs
