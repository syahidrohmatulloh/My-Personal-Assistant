from pathlib import Path

from app.services.memory_consolidation import (
    build_consolidation_candidates,
)


def row(content, **extra):
    return {
        "id": extra.get(
            "id",
            f"mem-{abs(hash(content))}",
        ),
        "content": content,
        "kind": extra.get(
            "kind",
            "context",
        ),
        "category": extra.get(
            "category",
            "preferences",
        ),
        "structured_field": extra.get(
            "structured_field",
        ),
        "structured_value": extra.get(
            "structured_value",
        ),
        "confidence": extra.get(
            "confidence",
            0.90,
        ),
        "source": extra.get(
            "source",
            "auto",
        ),
        "source_priority": extra.get(
            "source_priority",
            "explicit_user_statement",
        ),
        "evidence": extra.get(
            "evidence",
            [],
        ),
        "archived": extra.get(
            "archived",
            False,
        ),
        "superseded": extra.get(
            "superseded",
            False,
        ),
        "status": extra.get(
            "status",
            "active",
        ),
        "deleted_at": extra.get(
            "deleted_at",
        ),
        "last_user_confirmed_at": extra.get(
            "last_user_confirmed_at",
        ),
        "created_at": extra.get(
            "created_at",
            "2026-08-01T00:00:00+00:00",
        ),
        "updated_at": extra.get(
            "updated_at",
            "2026-08-01T00:00:00+00:00",
        ),
    }


def test_no_consolidation_for_single_memory():
    candidates = build_consolidation_candidates(
        [
            row(
                "User prefers concise technical answers.",
                id="m1",
                structured_field="response_preference",
                structured_value="concise technical answers",
            ),
        ]
    )

    assert candidates == []


def test_structured_repetition_targets_existing_memory():
    candidates = build_consolidation_candidates(
        [
            row(
                "User prefers concise technical answers.",
                id="m1",
                structured_field="response_preference",
                structured_value="concise technical answers",
                source_priority="explicit_user_statement",
                confidence=0.94,
            ),
            row(
                "User prefers concise technical answers.",
                id="m2",
                structured_field="response_preference",
                structured_value="concise technical answers",
                source_priority="user_answer_in_context",
                confidence=0.86,
            ),
        ]
    )

    assert len(candidates) == 1
    candidate = candidates[0]

    assert candidate.target_memory_ref == "m1"
    assert (
        "consolidation.cluster.structured_repeat"
        in candidate.reason_codes
    )
    assert candidate.content == (
        "User prefers concise technical answers."
    )
    assert set(candidate.source_memory_refs) == {
        "m1",
        "m2",
    }


def test_near_duplicate_unstructured_requires_three_rows():
    candidates = build_consolidation_candidates(
        [
            row(
                "User prefers root cause debugging with complete patches.",
                id="m1",
            ),
            row(
                "User prefers complete root cause debugging patches.",
                id="m2",
            ),
            row(
                "User prefers root cause debugging and complete patches.",
                id="m3",
            ),
        ]
    )

    assert len(candidates) == 1
    assert (
        "consolidation.cluster.near_duplicate"
        in candidates[0].reason_codes
    )


def test_unverified_repeated_pattern_is_not_source_material():
    candidates = build_consolidation_candidates(
        [
            row(
                "User appears to have a recurring routine involving: golf.",
                id="m1",
                category="routines",
                structured_field="habit_pattern_123",
                structured_value="golf",
                source="auto",
                source_priority="repeated_pattern",
                confidence=0.54,
            ),
            row(
                "User appears to have a recurring routine involving: golf.",
                id="m2",
                category="routines",
                structured_field="habit_pattern_123",
                structured_value="golf",
                source="auto",
                source_priority="repeated_pattern",
                confidence=0.54,
            ),
        ]
    )

    assert candidates == []


def test_hidden_rows_do_not_form_cluster():
    candidates = build_consolidation_candidates(
        [
            row(
                "User prefers concise answers.",
                id="m1",
                structured_field="response_style",
                structured_value="concise",
            ),
            row(
                "User prefers concise answers.",
                id="m2",
                structured_field="response_style",
                structured_value="concise",
                superseded=True,
            ),
        ]
    )

    assert candidates == []


def test_identity_and_sensitive_patterns_are_not_consolidated():
    identity_rows = [
        row(
            "User's name is Example.",
            id="m1",
            category="identity",
            structured_field="name",
            structured_value="Example",
        ),
        row(
            "User's name is Example.",
            id="m2",
            category="identity",
            structured_field="name",
            structured_value="Example",
        ),
    ]

    sensitive_rows = [
        row(
            "User takes prescription medication every morning.",
            id="m3",
            category="routines",
            structured_field="morning_routine",
            structured_value="prescription medication",
        ),
        row(
            "User takes prescription medication every morning.",
            id="m4",
            category="routines",
            structured_field="morning_routine",
            structured_value="prescription medication",
        ),
    ]

    assert build_consolidation_candidates(
        identity_rows
    ) == []

    assert build_consolidation_candidates(
        sensitive_rows
    ) == []


def test_m33_core_has_no_project_specific_keyword_taxonomy():
    source = Path(
        "app/services/memory_consolidation.py"
    ).read_text(
        encoding="utf-8"
    )

    forbidden = [
        "DEVELOPMENT_TERMS",
        "UI_TERMS",
        "CAREFUL_SUPPORT_TERMS",
        "RELATIONSHIP_TERMS",
        "monthly_focus",
        "aliyya development",
    ]

    for token in forbidden:
        assert token not in source


def test_old_canonically_confirmed_rows_remain_eligible():
    old = "2024-01-01T00:00:00+00:00"

    candidates = build_consolidation_candidates(
        [
            row(
                "User prefers concise technical answers.",
                id="old-1",
                structured_field="response_preference",
                structured_value="concise technical answers",
                source_priority="explicit_user_statement",
                confidence=0.90,
                created_at=old,
                updated_at=old,
                last_user_confirmed_at=old,
            ),
            row(
                "User prefers concise technical answers.",
                id="old-2",
                structured_field="response_preference",
                structured_value="concise technical answers",
                source_priority="user_answer_in_context",
                confidence=0.90,
                created_at=old,
                updated_at=old,
                last_user_confirmed_at=old,
            ),
        ]
    )

    assert len(candidates) == 1


def test_consolidation_db_reads_use_canonical_confirmation_field():
    source = Path(
        "app/services/memory_consolidation.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "last_user_confirmed_at" in source
    assert "last_confirmed_at" not in source
