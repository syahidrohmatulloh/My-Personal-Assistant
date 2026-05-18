from app.services.memory_quality import assess_memory_quality


def test_detects_duplicate_structured_memories():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "User timezone is Asia/Jakarta.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
            {
                "id": "m2",
                "content": "User uses Asia/Jakarta timezone.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
        ]
    )

    assert result["summary"]["duplicate_groups"] == 1
    assert result["review_items"][0]["issue_type"] == "duplicate"


def test_detects_conflicting_structured_memories():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "User prefers concise answers.",
                "category": "preferences",
                "structured_field": "communication_preference",
                "structured_value": "concise answers",
            },
            {
                "id": "m2",
                "content": "User prefers detailed step-by-step answers.",
                "category": "preferences",
                "structured_field": "communication_preference",
                "structured_value": "detailed step-by-step answers",
            },
        ]
    )

    assert result["summary"]["conflict_groups"] == 1
    assert any(item["issue_type"] == "conflict" for item in result["review_items"])


def test_ignores_archived_or_superseded_memories():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "Old timezone was UTC.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "UTC",
                "superseded": True,
            },
            {
                "id": "m2",
                "content": "User timezone is Asia/Jakarta.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
        ]
    )

    assert result["summary"]["active_memories"] == 1
    assert result["summary"]["conflict_groups"] == 0


def test_detects_low_quality_memory():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "ok",
                "category": "other",
                "structured_field": "manual_memory",
                "structured_value": "ok",
            }
        ]
    )

    assert result["summary"]["low_quality_memories"] == 1
    assert result["review_items"][0]["issue_type"] == "low_quality"


def test_similar_but_not_duplicate_memories_are_not_overflagged():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "User likes quiet afternoons near the window.",
                "category": "other",
                "structured_field": "manual_memory",
                "structured_value": "User likes quiet afternoons near the window.",
            },
            {
                "id": "m2",
                "content": "User wants to read books at night.",
                "category": "routines",
                "structured_field": "routine",
                "structured_value": "read books at night",
            },
        ]
    )

    assert result["summary"]["duplicate_groups"] == 0
    assert result["summary"]["conflict_groups"] == 0



def test_review_items_include_memory_contents_for_user_resolution():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "User timezone is Asia/Jakarta.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
            {
                "id": "m2",
                "content": "User uses Asia/Jakarta timezone.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
        ]
    )

    item = result["review_items"][0]
    assert item["issue_type"] == "duplicate"
    assert item["memories"][0]["id"] == "m1"
    assert item["memories"][0]["content"] == "User timezone is Asia/Jakarta."
    assert item["memories"][1]["id"] == "m2"
    assert item["memories"][1]["content"] == "User uses Asia/Jakarta timezone."


def test_duplicate_review_item_explains_reason():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "User timezone is Asia/Jakarta.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
            {
                "id": "m2",
                "content": "User uses Asia/Jakarta timezone.",
                "category": "identity",
                "structured_field": "timezone",
                "structured_value": "Asia/Jakarta",
            },
        ]
    )

    item = result["review_items"][0]
    assert item["issue_type"] == "duplicate"
    assert item["reason"]["field"] == "timezone"
    assert item["reason"]["values"] == ["Asia/Jakarta"]
    assert "same memory key" in item["reason"]["main"]


def test_conflict_review_item_explains_different_values():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "User prefers concise answers.",
                "category": "preferences",
                "structured_field": "communication_preference",
                "structured_value": "concise answers",
            },
            {
                "id": "m2",
                "content": "User prefers detailed step-by-step answers.",
                "category": "preferences",
                "structured_field": "communication_preference",
                "structured_value": "detailed step-by-step answers",
            },
        ]
    )

    item = result["review_items"][0]
    assert item["issue_type"] == "conflict"
    assert item["reason"]["field"] == "communication_preference"
    assert set(item["reason"]["values"]) == {
        "concise answers",
        "detailed step-by-step answers",
    }
    assert "different details" in item["reason"]["main"]


def test_low_quality_review_item_explains_reasons():
    result = assess_memory_quality(
        [
            {
                "id": "m1",
                "content": "ok",
                "category": "other",
                "structured_field": "manual_memory",
                "structured_value": "ok",
            }
        ]
    )

    item = result["review_items"][0]
    assert item["issue_type"] == "low_quality"
    assert item["reason"]["reasons"]
