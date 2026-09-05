import inspect
from pathlib import Path
from typing import get_type_hints

from app.routers import memory_review
from app.services import memory
from app.services import memory_epistemic_governance as epistemics


MIGRATION = Path(
    "schema_phase424_m35c3_memory_confirmation_governance.sql"
)


def test_legacy_confirmation_is_not_canonical_confirmation():
    row = {
        "last_confirmed_at": "2026-09-01T00:00:00+00:00",
        "last_user_confirmed_at": None,
    }

    assert epistemics.has_confirmation(row) is False


def test_genuine_user_confirmation_is_canonical_confirmation():
    row = {
        "last_confirmed_at": "2025-01-01T00:00:00+00:00",
        "last_user_confirmed_at": "2026-09-05T00:00:00+00:00",
    }

    assert epistemics.has_confirmation(row) is True


def test_retrieval_trust_bonus_is_counted_once():
    scoring_source = inspect.getsource(
        memory.memory_retrieval_score
    )
    metadata_source = inspect.getsource(
        memory._mi_metadata_priority
    )

    assert (
        scoring_source.count(
            "_mi_memory_governance_trust_bonus(row)"
        )
        == 0
    )

    assert (
        metadata_source.count(
            "_mi_memory_governance_trust_bonus(row)"
        )
        == 1
    )


def test_confirm_route_requires_memory_pin_body():
    signature = inspect.signature(
        memory_review.confirm_memory
    )
    type_hints = get_type_hints(
        memory_review.confirm_memory
    )

    assert "body" in signature.parameters
    assert type_hints["body"] is memory_review.MemoryPinIn


def test_manual_add_is_not_confirmation():
    source = inspect.getsource(
        memory_review.add_manual_memory
    )

    assert '"last_user_confirmed_at": None' in source
    assert (
        '"source_priority": "explicit_user_statement"'
        in source
    )


def test_edit_is_correction_not_confirmation():
    source = inspect.getsource(
        memory_review.edit_memory
    )

    assert '"source_priority": "user_correction"' in source
    assert '"last_user_confirmed_at": None' in source


def test_forget_archives_instead_of_superseding():
    source = inspect.getsource(
        memory_review.forget_memory
    )

    assert '"archived": True' in source
    assert '"status": "archived"' in source
    assert '"superseded": True' not in source


def test_restore_does_not_confirm_memory():
    source = inspect.getsource(
        memory_review.restore_memory
    )

    assert '"archived": False' in source
    assert '"status": "active"' in source
    assert "last_user_confirmed_at" not in source


def test_archived_review_group_does_not_include_superseded_history():
    payload = memory_review._build_review_payload(
        [
            {
                "id": "active",
                "content": "Active memory",
                "category": "other",
                "superseded": False,
                "archived": False,
                "status": "active",
            },
            {
                "id": "archive",
                "content": "Archived memory",
                "category": "other",
                "superseded": False,
                "archived": True,
                "status": "archived",
            },
            {
                "id": "old",
                "content": "Correction history",
                "category": "other",
                "superseded": True,
                "archived": False,
                "status": "superseded",
            },
        ]
    )

    assert payload["counts"] == {
        "active": 1,
        "archived": 1,
        "total": 2,
    }


def test_phase424_never_backfills_legacy_confirmation():
    sql = MIGRATION.read_text(
        encoding="utf-8"
    ).lower()

    assert (
        "add column if not exists last_user_confirmed_at"
        in sql
    )

    assert (
        "last_user_confirmation_source text"
        in sql
    )

    assert (
        "last_user_confirmation_evidence jsonb"
        in sql
    )

    # Schema DDL/projection is allowed; historical authority mutation is not.
    assert "update public.memories" not in sql
    assert "set last_user_confirmed_at" not in sql

    assert "m.last_user_confirmed_at" in sql
    assert "m.last_user_confirmation_source" in sql
    assert "m.last_user_confirmation_evidence" in sql
