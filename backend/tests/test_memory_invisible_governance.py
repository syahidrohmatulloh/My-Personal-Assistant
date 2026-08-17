from app.services import memory


def _row(**overrides):
    row = {
        "id": "mem",
        "content": "User prefers concise copy-paste commands",
        "category": "preferences",
        "structured_field": "assistant_name",
        "source": "auto",
        "source_priority": "explicit_user_statement",
        "confidence": 0.90,
        "similarity": 0.90,
        "archived": False,
        "superseded": False,
        "deleted_at": None,
        "status": None,
        "last_confirmed_at": None,
    }
    row.update(overrides)
    return row


def test_archived_memory_is_never_retrieved_even_if_high_score() -> None:
    ranked = memory.rank_memory_rows([
        _row(id="archived", similarity=0.99, confidence=0.99, archived=True),
        _row(id="active", similarity=0.70, confidence=0.70),
    ])

    assert [r["id"] for r in ranked] == ["active"]


def test_deleted_memory_is_never_retrieved_even_if_high_score() -> None:
    ranked = memory.rank_memory_rows([
        _row(id="deleted", similarity=0.99, confidence=0.99, deleted_at="2026-08-17T00:00:00+00:00"),
        _row(id="active", similarity=0.70, confidence=0.70),
    ])

    assert [r["id"] for r in ranked] == ["active"]


def test_status_archived_memory_is_never_retrieved() -> None:
    ranked = memory.rank_memory_rows([
        _row(id="status-archived", similarity=0.99, confidence=0.99, status="archived"),
        _row(id="active", similarity=0.70, confidence=0.70),
    ])

    assert [r["id"] for r in ranked] == ["active"]


def test_manual_review_memory_wins_close_tie_silently() -> None:
    ranked = memory.rank_memory_rows([
        _row(id="auto", source="auto", similarity=0.90, confidence=0.90),
        _row(
            id="manual",
            source="manual_review",
            similarity=0.90,
            confidence=0.90,
            last_confirmed_at="2026-08-17T00:00:00+00:00",
        ),
    ])

    # The manual_review row should win the close tie, then the duplicate auto
    # row is intentionally removed by lightweight dedupe.
    assert [r["id"] for r in ranked] == ["manual"]


def test_high_confidence_auto_memory_remains_usable_immediately() -> None:
    ranked = memory.rank_memory_rows([
        _row(id="auto-high-confidence", source="auto", confidence=0.95, similarity=0.92),
    ])

    assert [r["id"] for r in ranked] == ["auto-high-confidence"]
