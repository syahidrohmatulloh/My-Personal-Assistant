import asyncio
from types import SimpleNamespace

from app.services import conversation_summary


def test_retrieve_related_summaries_blocks_public_current_before_embedding(monkeypatch) -> None:
    async def fail_embed_query(_text: str):
        raise AssertionError("embed_query should not run for gated public/current query")

    monkeypatch.setattr(conversation_summary, "embed_query", fail_embed_query)

    result = asyncio.run(
        conversation_summary.retrieve_related_summaries(
            user_id="user-123456",
            query_text="cuaca besok di jakarta",
            exclude_conversation_id="convo-1",
            limit=6,
        )
    )

    assert result == []


def test_retrieve_related_summaries_allows_personal_query(monkeypatch) -> None:
    async def fake_embed_query(_text: str):
        return [0.1, 0.2]

    def fake_safe_execute(_fn):
        return SimpleNamespace(
            data=[
                {
                    "id": "summary-1",
                    "title": "Family",
                    "summary": "The user discussed Zahra.",
                    "similarity": 0.9,
                }
            ]
        )

    monkeypatch.setattr(conversation_summary, "embed_query", fake_embed_query)
    monkeypatch.setattr(conversation_summary, "safe_execute", fake_safe_execute)

    result = asyncio.run(
        conversation_summary.retrieve_related_summaries(
            user_id="user-123456",
            query_text="siapa nama anakku?",
            exclude_conversation_id="convo-1",
            limit=6,
        )
    )

    assert len(result) == 1
    assert result[0]["id"] == "summary-1"
