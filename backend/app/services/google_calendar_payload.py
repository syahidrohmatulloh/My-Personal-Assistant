"""Shared Google Calendar event payload builder.

A single, pure helper so create/patch payloads stay consistent across
calendar_draft_actions, calendar_confirmation_actions, and memory_review,
and so payload shape can be unit-tested without HTTP.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def next_iso_date(value: str) -> str:
    """Return the day after an ISO date; falls back to the input on bad data.

    Google Calendar's all-day `end.date` is exclusive, so a one-day event on
    2026-06-14 must end on 2026-06-15.
    """
    try:
        return (date.fromisoformat(str(value)) + timedelta(days=1)).isoformat()
    except Exception:
        return value


def build_google_event_body(
    *,
    title: str,
    event_date: str,
    description: str,
    start_at: str | None = None,
    end_at: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "summary": title,
        "description": description,
    }

    if start_at and end_at:
        event["start"] = {"dateTime": start_at}
        event["end"] = {"dateTime": end_at}
    else:
        # All-day: Google Calendar end.date is exclusive.
        event["start"] = {"date": event_date}
        event["end"] = {"date": next_iso_date(event_date)}

    cleaned_location = str(location or "").strip()
    if cleaned_location:
        event["location"] = cleaned_location[:180]

    return event
