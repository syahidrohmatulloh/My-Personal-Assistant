"""Time-bound memory lifecycle rules.

Scheduled events are useful, but they should not behave like permanent durable
memories forever. This module extracts lifecycle metadata from structured memory
values such as:

    name clearance presentation | due_date=2026-05-20 | relative=tomorrow

It does not create calendar events. It only marks memories as calendar
candidates so a later confirmed calendar pipeline can use them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any


@dataclass(frozen=True)
class TimeBoundMemoryMetadata:
    lifecycle_type: str
    due_date: str | None
    expires_at: str | None
    calendar_candidate: bool
    reason: str


def infer_time_bound_metadata(row: dict[str, Any]) -> TimeBoundMemoryMetadata | None:
    field = _norm(row.get("structured_field"))
    value = _clean(row.get("structured_value"))
    content = _clean(row.get("content"))

    if field not in {"scheduled_event", "upcoming_meeting"}:
        return None

    due_date = extract_due_date(value) or extract_due_date(content)
    if not due_date:
        return TimeBoundMemoryMetadata(
            lifecycle_type="time_bound",
            due_date=None,
            expires_at=None,
            calendar_candidate=True,
            reason="time_bound_without_due_date",
        )

    expires_at = expiry_for_due_date(due_date)
    return TimeBoundMemoryMetadata(
        lifecycle_type="time_bound",
        due_date=due_date,
        expires_at=expires_at,
        calendar_candidate=True,
        reason="scheduled_event_with_due_date",
    )


def extract_due_date(value: str | None) -> str | None:
    text = _clean(value)
    if not text:
        return None

    match = re.search(r"\bdue_date\s*=\s*(\d{4}-\d{2}-\d{2})\b", text)
    if match and _is_valid_date(match.group(1)):
        return match.group(1)

    match = re.search(r"\bdate\s*=\s*(\d{4}-\d{2}-\d{2})\b", text)
    if match and _is_valid_date(match.group(1)):
        return match.group(1)

    # Keep this deterministic. Do not guess "tomorrow" without created_at here;
    # earlier backfill already resolves relative dates into due_date=YYYY-MM-DD.
    return None


def expiry_for_due_date(due_date: str) -> str:
    parsed = date.fromisoformat(due_date)
    # Expire at the end of the next day UTC. This gives the assistant time to
    # still refer to "how did it go?" after the event date.
    expires = datetime.combine(parsed + timedelta(days=1), time(23, 59, 59), tzinfo=timezone.utc)
    return expires.isoformat()


def should_archive_time_bound_memory(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    lifecycle_type = _norm(row.get("lifecycle_type"))
    expires_at = _clean(row.get("expires_at"))

    if lifecycle_type != "time_bound" or not expires_at:
        return False

    now = now or datetime.now(timezone.utc)
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except Exception:
        return False

    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    return expires < now


def _is_valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except Exception:
        return False
    return True


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _norm(value: Any) -> str:
    return _clean(value).casefold()
