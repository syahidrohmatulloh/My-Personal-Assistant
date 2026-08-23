import asyncio
import logging

from app.services import chat_memory_assembly


def test_retrieve_chat_memory_assembly_uses_memory_and_summary_fan_in(monkeypatch) -> None:
    calls = {}

    async def fake_retrieve_relevant(user_id, query_text, *, limit):
        calls["memory"] = {
            "user_id": user_id,
            "query_text": query_text,
            "limit": limit,
        }
        return [{"id": "mem-1", "content": "Memory", "similarity": 0.9}]

    async def fake_retrieve_related_summaries(**kwargs):
        calls["summary"] = kwargs
        return [{"id": "sum-1", "summary": "Summary", "similarity": 0.8}]

    monkeypatch.setattr(
        chat_memory_assembly.memory,
        "retrieve_relevant",
        fake_retrieve_relevant,
    )
    monkeypatch.setattr(
        chat_memory_assembly.conversation_summary,
        "retrieve_related_summaries",
        fake_retrieve_related_summaries,
    )

    result = asyncio.run(
        chat_memory_assembly.retrieve_chat_memory_assembly(
            user_id="user-123456",
            query_text="siapa nama anakku?",
            conversation_id="convo-1",
        )
    )

    assert result.legacy_memories[0]["id"] == "mem-1"
    assert result.related_summaries[0]["id"] == "sum-1"
    assert calls["memory"] == {
        "user_id": "user-123456",
        "query_text": "siapa nama anakku?",
        "limit": 12,
    }
    assert calls["summary"] == {
        "user_id": "user-123456",
        "query_text": "siapa nama anakku?",
        "exclude_conversation_id": "convo-1",
        "limit": 6,
    }


def test_pack_chat_memory_context_logs_safe_counts_without_content(caplog) -> None:
    logger = logging.getLogger("uvicorn.error")

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        packed = chat_memory_assembly.pack_chat_memory_context(
            legacy_memories=[
                {
                    "id": "mem-1",
                    "content": "SECRET memory content should not be logged",
                    "similarity": 0.9,
                }
            ],
            related_summaries=[],
            query_text="SECRET query should not be logged",
            user_id="user-123456",
            logger=logger,
        )

    assert packed.memory_count == 1
    assert "memory_context_packer:" in caplog.text
    assert "memories_in=1" in caplog.text
    assert "SECRET" not in caplog.text
