"""Small, backend-grounded Calendar conflict detection helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def detect_calendar_conflicts(
    *,
    proposed_record: dict[str, Any],
    candidate_records: list[dict[str, Any]],
    exclude_ids: set[str] | None = None,
    exclude_google_event_ids: set[str] | None = None,
    max_conflicts: int = 3,
) -> dict[str, Any]:
    proposed = normalize_timed_event(proposed_record)

    if not proposed:
        return {
            "has_conflicts": False,
            "conflicts": [],
        }

    excluded_ids = {
        str(value or "").strip()
        for value in (exclude_ids or set())
        if str(value or "").strip()
    }
    excluded_google_ids = {
        str(value or "").strip()
        for value in (exclude_google_event_ids or set())
        if str(value or "").strip()
    }

    conflicts: list[dict[str, Any]] = []

    for record in candidate_records:
        candidate = normalize_timed_event(record)
        if not candidate:
            continue

        if candidate["id"] and candidate["id"] in excluded_ids:
            continue

        if (
            candidate["google_event_id"]
            and candidate["google_event_id"] in excluded_google_ids
        ):
            continue

        if _overlaps(proposed, candidate):
            conflicts.append(_conflict_payload(candidate))

        if len(conflicts) >= max_conflicts:
            break

    return {
        "has_conflicts": bool(conflicts),
        "conflicts": conflicts,
    }


def normalize_timed_event(
    record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None

    if bool(record.get("calendar_event_all_day") or record.get("all_day")):
        return None

    start_raw = (
        record.get("calendar_event_start_at")
        or record.get("start_at")
    )
    end_raw = (
        record.get("calendar_event_end_at")
        or record.get("end_at")
    )

    start = _parse_datetime(start_raw)
    end = _parse_datetime(end_raw)

    if not start or not end or end <= start:
        return None

    event_id = str(record.get("id") or "").strip()
    google_event_id = str(
        record.get("google_calendar_event_id")
        or record.get("googleEventId")
        or ""
    ).strip()

    title = str(
        record.get("calendar_event_title")
        or record.get("title")
        or record.get("content")
        or "Untitled event"
    ).replace("\n", " ").strip()

    source = str(
        record.get("_record_source")
        or record.get("source")
        or record.get("calendar_event_status")
        or "calendar"
    ).strip()

    return {
        "id": event_id,
        "google_event_id": google_event_id,
        "title": title[:160] or "Untitled event",
        "source": source[:80] or "calendar",
        "start": start,
        "end": end,
        "start_at": str(start_raw),
        "end_at": str(end_raw),
    }


def _overlaps(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    return left["start"] < right["end"] and left["end"] > right["start"]


def _conflict_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event["id"],
        "google_event_id": event["google_event_id"] or None,
        "title": event["title"],
        "source": event["source"],
        "start_at": event["start_at"],
        "end_at": event["end_at"],
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed
