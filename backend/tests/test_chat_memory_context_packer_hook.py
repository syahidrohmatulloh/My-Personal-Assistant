from pathlib import Path


def test_chat_runtime_delegates_memory_assembly_and_packing() -> None:
    source = Path("app/routers/chat.py").read_text(encoding="utf-8")

    assert "chat_memory_assembly.retrieve_chat_memory_assembly(" in source
    assert "chat_memory_assembly.pack_chat_memory_context(" in source
    assert "query_text=body.message" in source
    assert "## Additional notes (unstructured)" not in source
    assert "for m in legacy_memories[:5]" not in source


def test_chat_memory_assembly_preserves_retrieval_fan_in_contract() -> None:
    source = Path("app/services/chat_memory_assembly.py").read_text(encoding="utf-8")

    assert "memory_limit: int = 12" in source
    assert "summary_limit: int = 6" in source
    assert "memory.retrieve_relevant(user_id, query_text, limit=memory_limit)" in source
    assert "retrieve_related_summaries(" in source
    assert "limit=summary_limit" in source


def test_chat_memory_assembly_owns_packer_telemetry_contract() -> None:
    source = Path("app/services/chat_memory_assembly.py").read_text(encoding="utf-8")

    assert "pack_memory_context_for_prompt(" in source
    assert "query_text=query_text" in source
    assert "memory_context_packer: memories_in=%d memories_out=%d" in source
    assert "packed_chars=%d intent=%s" in source
