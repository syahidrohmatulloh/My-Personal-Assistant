from pathlib import Path


CONTEXT_SOURCE = Path("app/services/cognitive_turn_context.py").read_text(encoding="utf-8")


def test_chat_has_natural_memory_response_policy() -> None:
    assert "Memory response style policy:" in CONTEXT_SOURCE
    assert "acknowledge it naturally" in CONTEXT_SOURCE
    assert "Do not say you saved, added, stored, or recorded something in Memories" in CONTEXT_SOURCE
    assert "Do not ask the user to open Memory Review" in CONTEXT_SOURCE


def test_memory_policy_prefers_invisible_language() -> None:
    assert "Noted" in CONTEXT_SOURCE
    assert "Aku inget" in CONTEXT_SOURCE
    assert "Ke depan aku akan" in CONTEXT_SOURCE
