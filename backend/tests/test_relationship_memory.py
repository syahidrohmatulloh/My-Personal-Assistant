from app.services.relationship_memory import build_relationship_memory_candidates


def test_no_candidate_for_general_chat():
    candidates = build_relationship_memory_candidates(
        user_message="hari ini cuaca bagus ya",
    )

    assert candidates == []


def test_candidate_for_careful_comprehensive_patch_preference():
    candidates = build_relationship_memory_candidates(
        user_message=(
            "perbaiki secara hati-hati dan menyeluruh, jangan incremental. "
            "tolong edit patch final karena build error."
        ),
        assistant_response="Here is the full patch.",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "relationships"
    assert candidate.kind == "preference"
    assert candidate.structured_field == "aliyya_coding_support_style"
    assert (
        candidate.structured_value
        == "careful_comprehensive_fixes_not_incremental_guessing"
    )
    assert candidate.source_priority == "explicit_user_statement"
    assert candidate.confidence >= 0.85


def test_candidate_for_ui_design_taste():
    candidates = build_relationship_memory_candidates(
        user_message=(
            "Saya apresiasi UI yang enak dilihat. Untuk menu lain vibes-nya "
            "dibuat serupa, theme-aware, dan mobile version smooth ya."
        ),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "preferences"
    assert candidate.structured_field == "ui_design_taste"
    assert "theme-aware" in candidate.content
    assert "mobile" in candidate.content


def test_candidate_for_personal_companion_style():
    candidates = build_relationship_memory_candidates(
        user_message=(
            "Saya ingin Aliyya terasa seperti personal companion, bukan generic assistant."
        ),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "relationships"
    assert candidate.structured_field == "aliyya_relationship_style"
    assert candidate.structured_value == (
        "consistent_personal_companion_not_generic_assistant"
    )
