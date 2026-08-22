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


def test_episode_query_uses_relaxed_summary_threshold(monkeypatch) -> None:
    captured = {}

    async def fake_embed_query(_text: str):
        return [0.1, 0.2]

    class FakeRpc:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            return SimpleNamespace(data=[])

    class FakeSupabase:
        def rpc(self, name, payload):
            captured["name"] = name
            captured["payload"] = payload
            return FakeRpc(payload)

    def fake_safe_execute(fn):
        return fn(FakeSupabase())

    monkeypatch.setattr(conversation_summary, "embed_query", fake_embed_query)
    monkeypatch.setattr(conversation_summary, "safe_execute", fake_safe_execute)

    result = asyncio.run(
        conversation_summary.retrieve_related_summaries(
            user_id="user-123456",
            query_text="tolong lanjutkan pembahasan project Aliyya backend memory retrieval",
            exclude_conversation_id="convo-1",
            limit=6,
        )
    )

    assert result == []
    assert captured["name"] == "match_conversation_summaries"
    assert captured["payload"]["p_min_similarity"] == 0.40
    assert captured["payload"]["p_match_count"] == 6


def test_generic_query_keeps_default_summary_threshold(monkeypatch) -> None:
    captured = {}

    async def fake_embed_query(_text: str):
        return [0.1, 0.2]

    class FakeRpc:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            return SimpleNamespace(data=[])

    class FakeSupabase:
        def rpc(self, name, payload):
            captured["payload"] = payload
            return FakeRpc(payload)

    def fake_safe_execute(fn):
        return fn(FakeSupabase())

    monkeypatch.setattr(conversation_summary, "embed_query", fake_embed_query)
    monkeypatch.setattr(conversation_summary, "safe_execute", fake_safe_execute)

    result = asyncio.run(
        conversation_summary.retrieve_related_summaries(
            user_id="user-123456",
            query_text="tolong bantu analisa ini",
            exclude_conversation_id="convo-1",
            limit=6,
        )
    )

    assert result == []
    assert captured["payload"]["p_min_similarity"] == 0.55
