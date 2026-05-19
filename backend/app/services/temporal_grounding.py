"""Deterministic temporal grounding for relative-date phrases.

No specific dates are hardcoded. Dates are computed from user's local datetime.
Weekday vocabulary is calendar/language support.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo


_WEEKDAY_MAP = {
    "senin": 0,
    "monday": 0,
    "selasa": 1,
    "tuesday": 1,
    "rabu": 2,
    "wednesday": 2,
    "kamis": 3,
    "thursday": 3,
    "jumat": 4,
    "jum'at": 4,
    "friday": 4,
    "sabtu": 5,
    "saturday": 5,
    "minggu": 6,
    "sunday": 6,
}

_LAST_WEEKDAY_RE = re.compile(
    r"\b(?:minggu\s+lalu|last\s+week)\s+(?:hari\s+)?"
    r"(senin|selasa|rabu|kamis|jumat|jum'at|sabtu|minggu|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


def _get_context_value(client_context: Any, key: str) -> str | None:
    if client_context is None:
        return None
    if isinstance(client_context, dict):
        value = client_context.get(key)
    else:
        value = getattr(client_context, key, None)
    return str(value) if value else None


def _parse_local_datetime(client_context: Any) -> tuple[str, datetime]:
    timezone = (
        _get_context_value(client_context, "timezone")
        or _get_context_value(client_context, "time_zone")
        or "UTC"
    )

    try:
        tz = ZoneInfo(timezone)
    except Exception:
        timezone = "UTC"
        tz = ZoneInfo(timezone)

    local_time = (
        _get_context_value(client_context, "local_time")
        or _get_context_value(client_context, "local_datetime")
        or _get_context_value(client_context, "now")
    )

    if local_time:
        try:
            now = datetime.fromisoformat(local_time.replace("Z", "+00:00"))
            if now.tzinfo is None:
                now = now.replace(tzinfo=tz)
            else:
                now = now.astimezone(tz)
            return timezone, now
        except Exception:
            pass

    return timezone, datetime.now(tz)


def render_temporal_grounding_block(
    *,
    user_message: str,
    client_context: Any = None,
) -> str:
    text = str(user_message or "")
    timezone, now = _parse_local_datetime(client_context)

    lines = [
        "Temporal grounding — authoritative:",
        f"- User local timezone: {timezone}",
        f"- User local datetime: {now.isoformat()}",
    ]

    match = _LAST_WEEKDAY_RE.search(text)
    if match:
        weekday_name = match.group(1).lower()
        target_weekday = _WEEKDAY_MAP[weekday_name]

        start_this_week = now.date() - timedelta(days=now.weekday())
        start_last_week = start_this_week - timedelta(days=7)
        resolved = start_last_week + timedelta(days=target_weekday)

        lines.append(
            f'- Resolved "{match.group(0)}" as {resolved.isoformat()} '
            f"using Monday-start calendar week."
        )

    return "\n".join(lines)
