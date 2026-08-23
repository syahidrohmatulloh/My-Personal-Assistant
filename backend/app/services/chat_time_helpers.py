from __future__ import annotations

import re
from datetime import datetime, timedelta


def parse_client_local_time(raw_client_context: dict | None) -> tuple[datetime | None, str | None]:
    if not isinstance(raw_client_context, dict):
        return None, None

    local_time = str(raw_client_context.get("local_time") or "").strip()
    timezone = str(raw_client_context.get("timezone") or "").strip() or None

    if not local_time:
        return None, timezone

    # Frontend sends stable browser-local format: YYYY-MM-DD HH:mm:ss.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(local_time[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"), timezone
        except ValueError:
            continue

    return None, timezone


def interpret_hour_with_period(hour: int, period: str | None, now: datetime) -> int:
    period = (period or "").lower().strip()

    if period in {"pagi", "morning"}:
        if hour == 12:
            return 0
        return hour

    if period in {"siang", "afternoon"}:
        if hour == 12:
            return 12
        return hour + 12 if 1 <= hour <= 4 else hour

    if period in {"sore", "evening"}:
        if hour == 12:
            return 12
        return hour + 12 if 1 <= hour <= 7 else hour

    if period in {"malam", "night"}:
        if hour == 12:
            return 0
        return hour + 12 if 1 <= hour <= 11 else hour

    # No explicit period: choose the nearest plausible upcoming time today.
    # This handles Indonesian shorthand like "jam 5" when current time is 15:00
    # by interpreting it as 17:00, not 05:00 tomorrow.
    if 1 <= hour <= 11:
        am_candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        pm_candidate = now.replace(hour=hour + 12, minute=0, second=0, microsecond=0)

        if am_candidate >= now:
            return hour
        if pm_candidate >= now:
            return hour + 12

    return hour


def extract_mentioned_times(message: str | None, now: datetime) -> list[dict]:
    if not message:
        return []

    text = message.lower()
    results: list[dict] = []

    # Examples:
    # - jam 5 sore
    # - jam 1 siang
    # - jam 12.30
    # - pukul 17:00
    pattern = re.compile(
        r"\b(?:jam|pukul)\s*([0-2]?\d)(?:[:.]([0-5]\d))?\s*(pagi|siang|sore|malam|morning|afternoon|evening|night)?\b",
        re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)

        if hour > 23 or minute > 59:
            continue

        interpreted_hour = interpret_hour_with_period(hour, period, now)
        if interpreted_hour > 23:
            continue

        target = now.replace(
            hour=interpreted_hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        # If already passed by more than 30 minutes, assume next day.
        if target < now - timedelta(minutes=30):
            target = target + timedelta(days=1)

        delta = target - now
        total_minutes = round(delta.total_seconds() / 60)

        if total_minutes >= 0:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if hours and minutes:
                remaining = f"{hours} jam {minutes} menit"
            elif hours:
                remaining = f"{hours} jam"
            else:
                remaining = f"{minutes} menit"
        else:
            remaining = f"sudah lewat sekitar {abs(total_minutes)} menit"

        results.append(
            {
                "phrase": match.group(0),
                "interpreted_time": target.strftime("%Y-%m-%d %H:%M"),
                "remaining": remaining,
                "minutes_remaining": total_minutes,
            }
        )

    return results[:3]


def is_time_sensitive_message(message: str | None) -> bool:
    if not message:
        return False

    lower = message.lower()
    keywords = (
        "jam",
        "pukul",
        "meeting",
        "rapat",
        "jadwal",
        "deadline",
        "nanti",
        "sore",
        "siang",
        "malam",
        "pagi",
        "berapa lama",
        "berapa jam",
        "berapa menit",
        "sebentar lagi",
        "otw",
    )
    return any(keyword in lower for keyword in keywords)


def render_time_sensitive_calculation_block(
    user_message: str | None,
    raw_client_context: dict | None,
) -> str | None:
    if not is_time_sensitive_message(user_message):
        return None

    now, timezone = parse_client_local_time(raw_client_context)
    if not now:
        return None

    mentioned_times = extract_mentioned_times(user_message, now)

    lines = [
        "## Deterministic local-time calculation — highest priority",
        f"- Browser local time now: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        + (f" ({timezone})" if timezone else ""),
        "- Use this calculated local time for any schedule/deadline/meeting reasoning in this turn.",
        "- Do not override this with memory, chat history, server time, or model guess.",
    ]

    if mentioned_times:
        lines.append("- Mentioned time calculations:")
        for item in mentioned_times:
            lines.append(
                f"  - User phrase '{item['phrase']}' => {item['interpreted_time']}"
                f"; remaining from browser local time: {item['remaining']}."
            )

    lines.append(
        "- When replying, if timing matters, state the calculation naturally and briefly."
    )

    return "\n".join(lines)
