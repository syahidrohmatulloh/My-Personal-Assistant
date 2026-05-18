from app.services.memory_health_scheduler import build_user_memory_health_summaries


def test_build_user_memory_health_summaries_groups_by_user():
    result = build_user_memory_health_summaries(
        [
            {
                "id": "m1",
                "user_id": "u1",
                "content": "User timezone is Asia/Jakarta.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
            {
                "id": "m2",
                "user_id": "u1",
                "content": "User uses Asia/Jakarta timezone.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
            {
                "id": "m3",
                "user_id": "u2",
                "content": "User prefers concise answers.",
                "category": "preferences",
                "structured_field": "communication_preference",
                "structured_value": "concise answers",
            },
        ]
    )

    assert set(result) == {"u1", "u2"}
    assert result["u1"]["duplicate_groups"] == 1
    assert "stale_memories" in result["u1"]
    assert result["u1"]["needs_review"] >= 1
    assert result["u2"]["active_memories"] == 1


def test_build_user_memory_health_summaries_ignores_rows_without_user_id():
    result = build_user_memory_health_summaries(
        [
            {
                "id": "m1",
                "content": "No user id row.",
                "category": "other",
                "structured_field": "manual_memory",
                "structured_value": "No user id row.",
            }
        ]
    )

    assert result == {}
