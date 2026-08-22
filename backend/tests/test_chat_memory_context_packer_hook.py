from pathlib import Path


def test_chat_runtime_uses_memory_context_packer() -> None:
    source = Path("app/routers/chat.py").read_text(encoding="utf-8")

    assert "pack_memory_context_for_prompt(" in source
    assert "memory_context_packer: memories_in=%d memories_out=%d" in source
    assert "## Additional notes (unstructured)" not in source
    assert "for m in legacy_memories[:5]" not in source


def test_chat_retrieves_more_candidates_than_prompt_memory_cap() -> None:
    source = Path("app/routers/chat.py").read_text(encoding="utf-8")

    assert "memory.retrieve_relevant(user_id, body.message, limit=12)" in source
    assert "pack_memory_context_for_prompt(" in source
