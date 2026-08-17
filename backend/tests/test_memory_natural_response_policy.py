from pathlib import Path


CHAT_SOURCE = Path("app/routers/chat.py").read_text(encoding="utf-8")


def test_chat_has_natural_memory_response_policy() -> None:
    assert "Memory response style policy:" in CHAT_SOURCE
    assert "acknowledge it naturally" in CHAT_SOURCE
    assert "Do not say you saved, added, stored, or recorded something in Memories" in CHAT_SOURCE
    assert "Do not ask the user to open Memory Review" in CHAT_SOURCE


def test_memory_policy_prefers_invisible_language() -> None:
    assert "Noted" in CHAT_SOURCE
    assert "Aku inget" in CHAT_SOURCE
    assert "Ke depan aku akan" in CHAT_SOURCE
