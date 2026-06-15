from datetime import datetime, timezone
from pathlib import Path

from app.services import calendar_confirmation_actions as actions


CONFIRMATION_SRC = Path("app/services/calendar_confirmation_actions.py").read_text(encoding="utf-8")
EXTRACTOR_SRC = Path("app/services/calendar_candidate_extractor.py").read_text(encoding="utf-8")
DRAFT_SRC = Path("app/services/calendar_draft_actions.py").read_text(encoding="utf-8")


def test_pending_loader_selects_and_filters_expires_at():
    assert "expires_at" in CONFIRMATION_SRC
    assert "_partition_active_pending_calendar_suggestions" in CONFIRMATION_SRC
    assert "_archive_expired_pending_calendar_suggestions" in CONFIRMATION_SRC
    assert '"archived_by": "calendar_pending_expired"' in CONFIRMATION_SRC


def test_expired_pending_suggestion_is_detected_by_expires_at():
    row = {
        "id": "pending-1",
        "expires_at": "2020-01-01T00:00:00+00:00",
        "calendar_event_date": "2099-01-01",
    }

    assert actions._pending_calendar_suggestion_is_expired(
        row,
        now=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )


def test_past_event_pending_suggestion_is_expired_without_expires_at():
    row = {
        "id": "pending-1",
        "expires_at": None,
        "calendar_event_date": "2020-01-01",
    }

    assert actions._pending_calendar_suggestion_is_expired(
        row,
        now=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )


def test_future_pending_suggestion_stays_active():
    row = {
        "id": "pending-1",
        "expires_at": "2099-01-02T00:00:00+00:00",
        "calendar_event_date": "2099-01-01",
    }

    assert not actions._pending_calendar_suggestion_is_expired(
        row,
        now=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )


def test_partition_pending_suggestions_separates_expired_rows():
    active, expired = actions._partition_active_pending_calendar_suggestions(
        [
            {
                "id": "old",
                "expires_at": "2020-01-01T00:00:00+00:00",
                "calendar_event_date": "2099-01-01",
            },
            {
                "id": "new",
                "expires_at": "2099-01-02T00:00:00+00:00",
                "calendar_event_date": "2099-01-01",
            },
        ]
    )

    assert [row["id"] for row in active] == ["new"]
    assert [row["id"] for row in expired] == ["old"]


def test_multiple_pending_receipt_lists_options():
    receipt = actions.render_calendar_confirmation_user_receipt(
        {
            "attempted": True,
            "executed": False,
            "action": "clarify",
            "reason": "multiple_pending_suggestions",
            "pending_suggestions": [
                {
                    "title": "Bowling sama Aghnia",
                    "date": "2026-06-16",
                    "start_at": "2026-06-16T15:00:00+07:00",
                    "end_at": "2026-06-16T16:00:00+07:00",
                    "location": "Spin City Agora",
                },
                {
                    "title": "Lunch di Pacific Place",
                    "date": "2026-06-17",
                    "start_at": "2026-06-17T12:00:00+07:00",
                    "end_at": "2026-06-17T13:00:00+07:00",
                    "location": "Pacific Place",
                },
            ],
        },
        address_term="beb",
    )

    assert receipt.startswith("Aku menemukan beberapa agenda yang belum dikonfirmasi, beb.")
    assert "1. Bowling sama Aghnia — 16 Juni 2026, 15.00–16.00, Spin City Agora" in receipt
    assert "2. Lunch di Pacific Place — 17 Juni 2026, 12.00–13.00, Pacific Place" in receipt
    assert "masukin yang 1" in receipt
    assert "**Acara:**" not in receipt


def test_small_duplicate_artifacts_are_removed():
    assert EXTRACTOR_SRC.count('.or_("calendar_candidate.eq.true,calendar_event_status.in.(confirmed_local,synced_google)")') == 1
    assert "end_at: str | None,\n    end_at: str | None," not in DRAFT_SRC
    assert 'google_calendar_event_link, archived, superseded, "\n                "google_calendar_event_link' not in DRAFT_SRC
