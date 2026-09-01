from __future__ import annotations

from datetime import datetime, timezone

from app.services import habit_learning


def _row(day: int, text: str) -> dict:
    return {
        "content": text,
        "created_at": (
            datetime(
                2026,
                8,
                day,
                7,
                0,
                tzinfo=timezone.utc,
            ).isoformat()
        ),
    }


def test_no_signal_does_not_attempt_habit_learning() -> None:
    assert (
        habit_learning.classify_habit_signal(
            "tolong jelaskan laporan ini"
        )
        == "none"
    )
    assert (
        habit_learning.should_attempt_habit_learning(
            "tolong jelaskan laporan ini"
        )
        is False
    )


def test_explicit_routine_is_delegated_to_memory_intelligence() -> None:
    samples = (
        "Saya biasanya lari pagi setiap Senin.",
        "Aku rutin gym 3 kali seminggu.",
        "I usually read before bed.",
        "I exercise 4 times a week.",
    )

    for sample in samples:
        assert (
            habit_learning.classify_habit_signal(
                sample
            )
            == "explicit_routine"
        )
        assert (
            habit_learning.should_attempt_habit_learning(
                sample
            )
            is False
        )


def test_indonesian_occurrence_is_parsed_generically() -> None:
    observation = habit_learning.parse_occurrence(
        "Aku baru selesai lari pagi"
    )

    assert observation is not None
    assert observation.activity == "lari pagi"
    assert observation.signature == "lari pagi"


def test_english_occurrence_is_parsed_generically() -> None:
    observation = habit_learning.parse_occurrence(
        "I just finished yoga"
    )

    assert observation is not None
    assert observation.activity == "yoga"


def test_minor_occurrence_filler_keeps_signature_stable() -> None:
    first = habit_learning.parse_occurrence(
        "Aku baru selesai lari pagi"
    )
    second = habit_learning.parse_occurrence(
        "Aku habis lari pagi tadi"
    )

    assert first is not None
    assert second is not None
    assert first.signature == second.signature


def test_single_occurrence_is_not_a_habit() -> None:
    candidate, reasons = (
        habit_learning.derive_habit_candidate(
            current_user_message=(
                "Aku baru selesai lari pagi"
            ),
            history_rows=[
                _row(
                    1,
                    "Aku baru selesai lari pagi",
                )
            ],
        )
    )

    assert candidate is None
    assert (
        "habit.pattern.insufficient_occurrences"
        in reasons
    )


def test_four_occurrences_require_three_distinct_days() -> None:
    rows = [
        _row(1, "Aku baru selesai lari pagi"),
        _row(1, "Aku habis lari pagi"),
        _row(1, "Aku habis lari pagi tadi"),
        _row(10, "Aku baru selesai lari pagi"),
    ]

    candidate, reasons = (
        habit_learning.derive_habit_candidate(
            current_user_message=(
                "Aku baru selesai lari pagi"
            ),
            history_rows=rows,
        )
    )

    assert candidate is None
    assert (
        "habit.pattern.insufficient_distinct_days"
        in reasons
    )


def test_four_occurrences_require_minimum_span() -> None:
    rows = [
        _row(1, "Aku baru selesai lari pagi"),
        _row(2, "Aku habis lari pagi"),
        _row(3, "Aku habis lari pagi tadi"),
        _row(4, "Aku baru selesai lari pagi"),
    ]

    candidate, reasons = (
        habit_learning.derive_habit_candidate(
            current_user_message=(
                "Aku baru selesai lari pagi"
            ),
            history_rows=rows,
        )
    )

    assert candidate is None
    assert (
        "habit.pattern.insufficient_span"
        in reasons
    )


def test_qualified_pattern_is_conservative_inferred_routine() -> None:
    rows = [
        _row(1, "Aku baru selesai lari pagi"),
        _row(4, "Aku habis lari pagi"),
        _row(8, "Aku habis lari pagi tadi"),
        _row(12, "Aku baru selesai lari pagi"),
    ]

    candidate, reasons = (
        habit_learning.derive_habit_candidate(
            current_user_message=(
                "Aku baru selesai lari pagi"
            ),
            history_rows=rows,
        )
    )

    assert candidate is not None
    assert candidate.observation_count == 4
    assert candidate.distinct_days == 4
    assert candidate.span_days == 11
    assert candidate.confidence < 0.55
    assert candidate.structured_field.startswith(
        "habit_pattern_"
    )
    assert "appears to have" in candidate.content
    assert (
        "habit.pattern.qualified"
        in reasons
    )


def test_confidence_never_crosses_existing_unverified_threshold() -> None:
    assert (
        habit_learning._inferred_confidence(4)
        < 0.55
    )
    assert (
        habit_learning._inferred_confidence(100)
        == habit_learning.MAX_INFERRED_CONFIDENCE
    )
    assert (
        habit_learning.MAX_INFERRED_CONFIDENCE
        < 0.55
    )


def test_sensitive_activity_is_never_inferred() -> None:
    samples = (
        "Aku baru selesai minum obat",
        "Aku habis sholat",
        "I just finished prayer",
        "I just finished smoking",
        "I just finished political campaigning",
    )

    for sample in samples:
        assert (
            habit_learning.parse_occurrence(
                sample
            )
            is None
        )


def test_emotional_or_physical_state_is_not_habit_activity() -> None:
    samples = (
        "Aku habis capek",
        "Aku baru selesai sedih",
        "I just finished tired",
    )

    for sample in samples:
        assert (
            habit_learning.parse_occurrence(
                sample
            )
            is None
        )


def test_explicit_correction_is_detected() -> None:
    samples = (
        "Aku sudah tidak lari pagi lagi",
        "Saya berhenti lari pagi",
        "I no longer run",
        "I stopped yoga",
    )

    for sample in samples:
        assert (
            habit_learning.classify_habit_signal(
                sample
            )
            == "explicit_correction"
        )
        assert (
            habit_learning.should_attempt_habit_learning(
                sample
            )
            is True
        )


def test_pattern_ref_is_stable_and_content_free() -> None:
    first = habit_learning._pattern_ref(
        "lari pagi"
    )
    second = habit_learning._pattern_ref(
        "lari pagi"
    )

    assert first == second
    assert first.startswith(
        "habit_pattern_"
    )
    assert "lari" not in first


def test_m32_inferred_confidence_is_unverified_under_m31f_governance() -> None:
    from app.services import memory_lifecycle_governance

    assessment = (
        memory_lifecycle_governance
        .assess_memory_lifecycle(
            {
                "status": "active",
                "confidence": (
                    habit_learning
                    .MAX_INFERRED_CONFIDENCE
                ),
                "source_priority": (
                    "repeated_pattern"
                ),
            }
        )
    )

    assert assessment.needs_confirmation is True
