from datetime import datetime, timedelta, timezone

from app.services.memory_lifecycle_governance import (
    assess_memory_lifecycle,
    build_lifecycle_aggregate,
    is_retrievable_memory,
    safe_lifecycle_diagnostics,
)


NOW = datetime(2026, 8, 23, tzinfo=timezone.utc)


def test_hidden_memory_states_are_not_retrievable() -> None:
    assert not is_retrievable_memory({"status": "archived"})
    assert not is_retrievable_memory({"status": "superseded"})
    assert not is_retrievable_memory({"status": "deleted"})
    assert not is_retrievable_memory({"deleted_at": "2026-01-01T00:00:00+00:00"})
    assert not is_retrievable_memory({"archived": True})
    assert not is_retrievable_memory({"superseded": True})
    assert is_retrievable_memory({"status": "active"})
    assert is_retrievable_memory({"archived": False, "superseded": False})


def test_lifecycle_assessment_marks_stale_without_auto_hiding() -> None:
    old = (NOW - timedelta(days=500)).isoformat()
    row = {
        "status": "active",
        "created_at": old,
        "confidence": 0.90,
        "content": "SECRET should never appear in diagnostics",
    }

    assessed = assess_memory_lifecycle(row, now=NOW)

    assert assessed.state == "active"
    assert assessed.hidden is False
    assert assessed.stale is True
    assert assessed.needs_confirmation is True
    assert assessed.reason == "stale"


def test_confirmed_memory_is_not_stale_even_when_old() -> None:
    old = (NOW - timedelta(days=700)).isoformat()
    row = {
        "status": "active",
        "created_at": old,
        "last_user_confirmed_at": old,
        "confidence": 0.95,
    }

    assessed = assess_memory_lifecycle(row, now=NOW)

    assert assessed.confirmed is True
    assert assessed.stale is False
    assert assessed.needs_confirmation is False
    assert assessed.reason == "confirmed"


def test_legacy_last_confirmed_at_does_not_create_authority() -> None:
    row = {
        "status": "active",
        "created_at": NOW.isoformat(),
        "last_confirmed_at": NOW.isoformat(),
        "last_user_confirmed_at": None,
        "confidence": 0.95,
        "source": "auto",
        "source_priority": "legacy_unknown",
    }

    assessed = assess_memory_lifecycle(row, now=NOW)

    assert assessed.confirmed is False
    assert assessed.needs_confirmation is True
    assert assessed.reason == "provenance_unverified"


def test_low_confidence_active_memory_needs_confirmation() -> None:
    row = {
        "status": "active",
        "created_at": NOW.isoformat(),
        "confidence": 0.20,
    }

    assessed = assess_memory_lifecycle(row, now=NOW)

    assert assessed.hidden is False
    assert assessed.needs_confirmation is True
    assert assessed.reason == "needs_confirmation"


def test_lifecycle_aggregate_and_diagnostics_are_content_free() -> None:
    rows = [
        {
            "status": "active",
            "created_at": (NOW - timedelta(days=500)).isoformat(),
            "content": "SECRET stale memory content",
        },
        {"status": "archived", "content": "SECRET hidden memory content"},
        {
            "status": "active",
            "last_user_confirmed_at": NOW.isoformat(),
            "content": "SECRET confirmed memory content",
        },
    ]

    aggregate = build_lifecycle_aggregate(rows, now=NOW)
    diagnostics = safe_lifecycle_diagnostics(rows)

    assert aggregate.total == 3
    assert aggregate.active == 2
    assert aggregate.hidden == 1
    assert aggregate.stale == 1
    assert aggregate.needs_confirmation == 1
    assert aggregate.confirmed == 1

    assert "memory_lifecycle:" in diagnostics
    assert "total=3" in diagnostics
    assert "active=2" in diagnostics
    assert "hidden=1" in diagnostics
    assert "stale=1" in diagnostics
    assert "needs_confirmation=1" in diagnostics
    assert "confirmed=1" in diagnostics
    assert "SECRET" not in diagnostics
