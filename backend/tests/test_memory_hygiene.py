from app.services.memory_hygiene import evaluate_memory_candidate, sanitize_memory_row


def test_rejects_simple_greeting():
    result = evaluate_memory_candidate(content="hai")
    assert result.should_store is False


def test_rejects_short_acknowledgement():
    result = evaluate_memory_candidate(content="oke")
    assert result.should_store is False


def test_accepts_structured_preference():
    row = sanitize_memory_row(
        {
            "content": "User prefers concise answers",
            "structured_field": "communication_style",
            "structured_value": "prefers concise answers",
            "category": "preferences",
            "confidence": 0.82,
        }
    )
    assert row is not None
    assert row["structured_field"] == "communication_style"
    assert row["structured_value"] == "prefers concise answers"


def test_infers_key_value_from_explicit_memory_command():
    result = evaluate_memory_candidate(content="ingat bahwa timezone saya GMT+7")
    assert result.should_store is True
    assert result.structured_field is not None
    assert result.structured_value is not None


def test_rejects_missing_key_value_for_ambiguous_short_text():
    result = evaluate_memory_candidate(content="ini bagus")
    assert result.should_store is False
