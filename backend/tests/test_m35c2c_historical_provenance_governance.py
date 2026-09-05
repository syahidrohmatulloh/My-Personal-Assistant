from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

from app.services import memory
from app.services import memory_epistemic_governance as epistemics
from app.services import memory_intelligence
from app.services import memory_lifecycle_governance
from app.services import metacognitive_policy


MIGRATION = Path(
    "schema_phase423_m35c2c_historical_provenance_governance.sql"
)


def _row(**overrides):
    row = {
        "id": "m1",
        "content": "Historical memory",
        "kind": "preference",
        "category": "other",
        "source": "auto",
        "source_priority": "legacy_unknown",
        "confidence": 0.95,
        "similarity": 0.90,
        "created_at": "2026-09-01T00:00:00+00:00",
        "last_confirmed_at": None,
        "last_user_confirmed_at": None,
        "status": "active",
        "archived": False,
        "superseded": False,
        "deleted_at": None,
    }
    row.update(overrides)
    return row


def test_legacy_unknown_is_storage_only_not_writer_assignable():
    assert (
        epistemics.LEGACY_UNKNOWN_PRIORITY
        in epistemics.CANONICAL_STORED_PRIORITIES
    )

    assert (
        epistemics.LEGACY_UNKNOWN_PRIORITY
        not in get_args(memory_intelligence.SourcePriority)
    )

    assert (
        '"legacy_unknown"'
        not in memory_intelligence._EXTRACTION_SYSTEM_PROMPT
    )


def test_high_confidence_legacy_unknown_is_unverified():
    assessment = (
        memory_lifecycle_governance
        .assess_memory_lifecycle(_row())
    )

    assert assessment.needs_confirmation is True
    assert assessment.confirmed is False
    assert assessment.reason == "provenance_unverified"


def test_legacy_confirmation_timestamp_cannot_override_weak_origin():
    row = _row(
        last_confirmed_at="2026-09-03T00:00:00+00:00"
    )

    assessment = (
        memory_lifecycle_governance
        .assess_memory_lifecycle(row)
    )

    assert assessment.confirmed is False
    assert assessment.needs_confirmation is True


def test_real_user_confirmation_can_override_weak_origin_on_full_row():
    row = _row(
        last_confirmed_at="2026-09-03T00:00:00+00:00",
        last_user_confirmed_at="2026-09-04T00:00:00+00:00",
    )

    assessment = (
        memory_lifecycle_governance
        .assess_memory_lifecycle(row)
    )

    assert assessment.confirmed is True
    assert assessment.needs_confirmation is False


def test_missing_provenance_from_auto_writer_is_unverified():
    row = _row(
        source_priority=None,
        confidence=0.99,
    )

    assert epistemics.provenance_requires_confirmation(row) is True

    assessment = (
        memory_lifecycle_governance
        .assess_memory_lifecycle(row)
    )

    assert assessment.needs_confirmation is True


def test_effective_confidence_caps_unverified_provenance():
    for priority in (
        "legacy_unknown",
        "system_inference",
        "assistant_confirmation",
    ):
        row = _row(
            source_priority=priority,
            confidence=0.99,
        )
        assert (
            epistemics.effective_confidence(row)
            == epistemics.MAX_UNVERIFIED_CONFIDENCE
        )

    explicit = _row(
        source_priority="explicit_user_statement",
        confidence=0.93,
    )

    assert epistemics.effective_confidence(explicit) == 0.93


def test_metacognitive_policy_sees_legacy_unknown_as_unverified():
    trust, refs = metacognitive_policy._assess_evidence(
        [_row(id="legacy-1")],
        now=datetime.now(timezone.utc),
    )

    assert trust == "unverified"
    assert refs == ("legacy-1",)


def test_repaired_source_priority_ranking_is_enabled_and_conservative():
    assert memory.SOURCE_PRIORITY_RANKING_ENABLED is True

    base = _row(
        category="other",
        source_priority="explicit_user_statement",
        confidence=0.95,
    )

    explicit = {
        **base,
        "id": "explicit",
    }
    repeated = {
        **base,
        "id": "repeated",
        "source_priority": "repeated_pattern",
    }
    legacy = {
        **base,
        "id": "legacy",
        "source_priority": "legacy_unknown",
    }

    assert (
        memory.memory_retrieval_score(explicit)
        > memory.memory_retrieval_score(repeated)
        > memory.memory_retrieval_score(legacy)
    )


def test_prompt_marks_unverified_memory_without_exposing_provenance():
    label = memory._mi_prompt_label(
        _row(
            source_priority="legacy_unknown",
        )
    )

    assert "verification=unverified" in label
    assert "legacy_unknown" not in label


def test_phase423_has_frozen_distribution_and_storage_taxonomy():
    sql = MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    for value in (
        "2026-09-02 17:40:14+00",
        "expected 83",
        "expected 42",
        "expected 40",
        "legacy_unknown",
        "system_inference",
        "expected 29",
        "expected 10",
    ):
        assert value in sql

    assert "'legacy_unknown'" in sql
    assert "'system_inference'" in sql


def test_phase423_uses_exact_known_system_inference_fingerprints():
    sql = MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    for field in (
        "aliyya_coding_support_style",
        "ui_design_taste",
        "aliyya_relationship_style",
        "debugging_support_style_under_frustration",
    ):
        assert field in sql

    assert "0.54" in sql


def test_phase423_has_one_memory_update_and_narrow_columns():
    sql = MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    assert sql.count(
        "update public.memories"
    ) == 1

    assert "set source_priority =" in sql
    assert "confidence = case" in sql

    assert "set last_confirmed_at" not in sql
    assert "set content" not in sql
    assert "set evidence" not in sql
    assert "set structured_field" not in sql
    assert "set structured_value" not in sql
    assert "set status" not in sql
    assert "set archived" not in sql
    assert "set superseded" not in sql
    assert "set deleted_at" not in sql


def test_phase423_preserves_m35c2b_confirmation_distribution():
    sql = MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    assert "106/21" in sql
    assert "confirmation distribution changed" in sql
    assert "raise exception" in sql
    assert "\nbegin;" in sql
    assert "commit;" in sql


def test_phase423_confidence_boundary_is_postgres_real_safe():
    sql = MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    assert "coalesce(m.confidence, 0.54::real)" in sql
    assert "confidence <= 0.54::real;" in sql

    # Two assignment literals + one verification literal.
    assert sql.count("0.54::real") == 3

    # No operational legacy boundary remains.
    operational = [
        line.strip()
        for line in sql.splitlines()
        if "0.54" in line
        and not line.strip().startswith("--")
    ]

    assert operational
    assert all("0.54::real" in line for line in operational)
