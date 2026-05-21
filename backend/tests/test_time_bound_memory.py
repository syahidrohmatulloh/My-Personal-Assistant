from datetime import datetime, timezone

from app.services.time_bound_memory import (
    extract_due_date,
    infer_time_bound_metadata,
    should_archive_time_bound_memory,
)


def test_extracts_due_date_from_structured_value():
    assert (
        extract_due_date("presentation to director | due_date=2026-05-20 | relative=tomorrow")
        == "2026-05-20"
    )


def test_infers_scheduled_event_metadata():
    meta = infer_time_bound_metadata(
        {
            "structured_field": "scheduled_event",
            "structured_value": "presentation | due_date=2026-05-20 | relative=tomorrow",
            "content": "User has a presentation scheduled for tomorrow",
        }
    )

    assert meta is not None
    assert meta.lifecycle_type == "time_bound"
    assert meta.due_date == "2026-05-20"
    assert meta.expires_at is not None
    assert meta.calendar_candidate is True


def test_does_not_infer_regular_memory():
    assert infer_time_bound_metadata({"structured_field": "food_preference", "structured_value": "mango"}) is None


def test_archives_expired_time_bound_memory():
    row = {
        "lifecycle_type": "time_bound",
        "expires_at": "2026-05-21T23:59:59+00:00",
    }

    assert should_archive_time_bound_memory(
        row,
        now=datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc),
    ) is True


def test_does_not_archive_future_time_bound_memory():
    row = {
        "lifecycle_type": "time_bound",
        "expires_at": "2026-05-23T23:59:59+00:00",
    }

    assert should_archive_time_bound_memory(
        row,
        now=datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc),
    ) is False
