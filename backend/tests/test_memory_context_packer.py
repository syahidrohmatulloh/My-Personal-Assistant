from app.services.memory_context_packer import pack_memory_context_for_prompt


def test_pack_memory_context_filters_dedupes_and_caps_memories() -> None:
    memories = [
        {
            "id": "archived",
            "content": "Archived memory should not appear",
            "status": "archived",
            "similarity": 0.99,
        },
        {
            "id": "a",
            "content": "User wants gentle reminders when overthinking",
            "category": "preferences",
            "similarity": 0.91,
            "confidence": 0.9,
        },
        {
            "id": "dup",
            "content": "User wants gentle reminders when overthinking",
            "category": "preferences",
            "similarity": 0.88,
        },
        {
            "id": "b",
            "content": "User prefers concise responses",
            "category": "preferences",
            "similarity": 0.87,
        },
        {
            "id": "c",
            "content": "User often works late at night",
            "category": "routines",
            "similarity": 0.86,
        },
    ]

    packed = pack_memory_context_for_prompt(
        legacy_memories=memories,
        related_summaries=[],
        max_memory_items=3,
    )

    assert packed.memory_count == 3
    assert packed.dropped_memory_count == 2
    assert "Archived memory should not appear" not in packed.text
    assert packed.text.count("User wants gentle reminders when overthinking") == 1
    assert "## Relevant memory context" in packed.text
    assert "Use this silently for continuity" in packed.text


def test_pack_memory_context_caps_noisy_category() -> None:
    memories = [
        {
            "id": str(i),
            "content": f"Preference memory {i}",
            "category": "preferences",
            "similarity": 1.0 - i * 0.01,
        }
        for i in range(6)
    ]

    packed = pack_memory_context_for_prompt(
        legacy_memories=memories,
        related_summaries=[],
        max_memory_items=5,
        max_memory_items_per_category=4,
    )

    assert packed.memory_count == 4
    assert "Preference memory 0" in packed.text
    assert "Preference memory 4" not in packed.text


def test_pack_memory_context_caps_related_summaries() -> None:
    summaries = [
        {
            "title": f"Conversation {i}",
            "summary": f"Summary {i}",
            "updated_at": f"2026-08-2{i}T00:00:00",
        }
        for i in range(4)
    ]

    packed = pack_memory_context_for_prompt(
        legacy_memories=[],
        related_summaries=summaries,
        max_related_summary_items=2,
    )

    assert packed.memory_count == 0
    assert packed.summary_count == 2
    assert packed.dropped_summary_count == 2
    assert "Conversation 0" in packed.text
    assert "Conversation 1" in packed.text
    assert "Conversation 2" not in packed.text


def test_pack_memory_context_returns_empty_text_when_no_context() -> None:
    packed = pack_memory_context_for_prompt(
        legacy_memories=[],
        related_summaries=[],
    )

    assert packed.text == ""
    assert packed.memory_count == 0
    assert packed.summary_count == 0
