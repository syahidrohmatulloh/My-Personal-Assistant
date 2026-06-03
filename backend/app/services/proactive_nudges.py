"""Proactive Aliyya messages.

v1 scope:
- Detect simple reminder/nudge requests from chat.
- Store a scheduled proactive nudge.
- Background scheduler inserts an assistant message into the target conversation
  when due.

This does not send push notifications yet. The proactive message appears in
Main Chat / the target chat when the user opens the app.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.supabase_client import safe_execute

log = logging.getLogger(__name__)

_SCHEDULER_TASK: asyncio.Task | None = None
_STOP_EVENT: asyncio.Event | None = None

POLL_INTERVAL_SECONDS = 60
DEFAULT_TIMEZONE_OFFSET_MINUTES = 420  # WIB / UTC+7
MAX_DUE_DAYS = 365

_REMINDER_KEYWORDS = (
    "ingetin aku",
    "ingatkan aku",
    "tolong ingetin",
    "tolong ingatkan",
    "remind me",
    "set reminder",
    "buat reminder",
    "bikin reminder",
    "kasih reminder",
)

_TIME_OF_DAY_DEFAULTS = {
    "pagi": (7, 0),
    "siang": (12, 0),
    "sore": (17, 0),
    "malam": (20, 0),
    "morning": (7, 0),
    "afternoon": (13, 0),
    "evening": (18, 0),
    "tonight": (20, 0),
}

_WEEKDAY_INDEX = {
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


@dataclass(frozen=True)
class ParsedNudge:
    due_at: datetime
    title: str
    message: str


def _normalize(text: str | None) -> str:
    return " ".join(str(text or "").strip().lower().split())


def should_attempt_proactive_nudge(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    return any(keyword in normalized for keyword in _REMINDER_KEYWORDS)


def _timezone_offset_minutes(client_context: dict[str, Any] | None) -> int:
    if not isinstance(client_context, dict):
        return DEFAULT_TIMEZONE_OFFSET_MINUTES

    candidates = [
        client_context.get("timezone_offset_minutes"),
        client_context.get("timezoneOffsetMinutes"),
        client_context.get("utc_offset_minutes"),
        client_context.get("utcOffsetMinutes"),
    ]

    for raw in candidates:
        try:
            value = int(raw)
        except Exception:
            continue

        # Browser Date.getTimezoneOffset() returns -420 for WIB.
        if value < 0:
            return -value

        return value

    return DEFAULT_TIMEZONE_OFFSET_MINUTES


def _client_now(client_context: dict[str, Any] | None) -> datetime:
    offset = _timezone_offset_minutes(client_context)
    tz = timezone(timedelta(minutes=offset))

    if isinstance(client_context, dict):
        for key in (
            "local_time",
            "localTime",
            "browser_local_time",
            "browserLocalTime",
            "now",
            "timestamp",
        ):
            raw = client_context.get(key)
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=tz)
                return parsed.astimezone(tz)
            except Exception:
                continue

    return datetime.now(tz)


def _extract_explicit_time(normalized: str) -> tuple[int, int] | None:
    match = re.search(
        r"\b(?:jam|pukul|at)?\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|pagi|siang|sore|malam)?\b",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = (match.group(3) or "").lower()

    if suffix in {"pm", "sore", "malam"} and hour < 12:
        hour += 12
    elif suffix in {"siang"} and hour < 11:
        hour += 12
    elif suffix == "pagi" and hour == 12:
        hour = 0
    elif suffix == "am" and hour == 12:
        hour = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    return hour, minute


def _extract_time_of_day_default(normalized: str) -> tuple[int, int] | None:
    for keyword, value in _TIME_OF_DAY_DEFAULTS.items():
        if keyword in normalized:
            return value
    return None


def _resolve_due_date(now: datetime, normalized: str) -> datetime:
    if "lusa" in normalized:
        return now + timedelta(days=2)

    if "besok" in normalized or "tomorrow" in normalized:
        return now + timedelta(days=1)

    if "minggu depan" in normalized or "next week" in normalized:
        return now + timedelta(days=7)

    for word, weekday in _WEEKDAY_INDEX.items():
        if word in normalized:
            days_ahead = (weekday - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return now + timedelta(days=days_ahead)

    return now


def _extract_relative_due(now: datetime, normalized: str) -> datetime | None:
    minute_match = re.search(r"\b(?:in\s+)?(\d{1,3})\s*(?:menit|minutes?|mins?)\s*(?:lagi)?\b", normalized)
    if minute_match:
        return now + timedelta(minutes=int(minute_match.group(1)))

    hour_match = re.search(r"\b(?:in\s+)?(\d{1,2})\s*(?:jam|hours?|hrs?)\s*(?:lagi)?\b", normalized)
    if hour_match:
        return now + timedelta(hours=int(hour_match.group(1)))

    return None


def _clean_title(text: str) -> str:
    title = str(text or "").strip()

    # Generic cleanup:
    # remove everything before and including the reminder intent.
    # This avoids hardcoding the user's nickname or the assistant's name.
    intent_patterns = [
        r"^.*?\b(?:tolong\s+)?ingetin\s+aku\s+(?:ya\s+)?(?:untuk\s+|buat\s+)?",
        r"^.*?\b(?:tolong\s+)?ingatkan\s+aku\s+(?:ya\s+)?(?:untuk\s+|buat\s+)?",
        r"^.*?\bremind\s+me\s+(?:to\s+)?",
        r"^.*?\bset\s+reminder\s+(?:to\s+)?",
        r"^.*?\b(?:buat|bikin|kasih)\s+reminder\s+(?:untuk\s+|buat\s+)?",
    ]

    for pattern in intent_patterns:
        next_title = re.sub(pattern, "", title, flags=re.IGNORECASE).strip()
        if next_title != title:
            title = next_title
            break

    cleanup_patterns = [
        r"\bbesok\b",
        r"\blusa\b",
        r"\btomorrow\b",
        r"\bminggu depan\b",
        r"\bnext week\b",
        r"\bpagi\b",
        r"\bsiang\b",
        r"\bsore\b",
        r"\bmalam\b",
        r"\bmorning\b",
        r"\bafternoon\b",
        r"\bevening\b",
        r"\btonight\b",
        r"\bjam\s*\d{1,2}(?:[:.]\d{2})?\s*(?:pagi|siang|sore|malam)?\b",
        r"\bpukul\s*\d{1,2}(?:[:.]\d{2})?\s*(?:pagi|siang|sore|malam)?\b",
        r"\bat\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?\b",
        r"\b\d{1,3}\s*(?:menit|minutes?|mins?)\s*(?:lagi)?\b",
        r"\b\d{1,2}\s*(?:jam|hours?|hrs?)\s*(?:lagi)?\b",
        r"\b(?:untuk|buat|to)\b",
        r"\bya\b",
    ]

    for pattern in cleanup_patterns:
        title = re.sub(pattern, " ", title, flags=re.IGNORECASE)

    title = " ".join(title.split()).strip(".,;:- ")
    return title[:120] or "reminder"


def _is_english_reminder_request(text: str) -> bool:
    normalized = _normalize(text)
    return any(keyword in normalized for keyword in ("remind me", "set reminder"))


def _build_nudge_message(*, title: str, user_message: str) -> str:
    if _is_english_reminder_request(user_message):
        return f"Time to {title}."

    return f"Waktunya kamu {title}."


_CONFIRMATION_KEYWORDS = (
    "oke",
    "ok",
    "okay",
    "yes",
    "ya",
    "iya",
    "boleh",
    "sip",
    "siap",
    "setuju",
    "sure",
)

_REMINDER_OFFER_WORDS = (
    "ingetin",
    "ingatkan",
    "remind",
    "reminder",
)

def _is_confirmation_message(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    return normalized in _CONFIRMATION_KEYWORDS or any(
        normalized.startswith(f"{keyword} ") for keyword in _CONFIRMATION_KEYWORDS
    )


def _assistant_response_looks_like_reminder_offer(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    has_reminder_word = any(word in normalized for word in _REMINDER_OFFER_WORDS)
    has_time = bool(_extract_explicit_time(normalized) or _extract_relative_due(_client_now(None), normalized))
    return has_reminder_word and has_time


def _title_from_confirmation_offer(text: str | None) -> str:
    normalized = _normalize(text)

    simple_candidates = (
        ("berangkat", "berangkat"),
        ("meeting", "meeting"),
        ("rapat", "rapat"),
        ("minum obat", "minum obat"),
        ("tidur", "tidur"),
        ("jemput", "jemput"),
        ("call", "call"),
    )

    for needle, title in simple_candidates:
        if needle in normalized:
            return title

    return "reminder ini"


def parse_nudge_from_chat(
    *,
    user_message: str,
    client_context: dict[str, Any] | None = None,
    assistant_response: str | None = None,
) -> ParsedNudge | None:
    parsed = parse_nudge_request(user_message=user_message, client_context=client_context)
    if parsed:
        return parsed

    if not _is_confirmation_message(user_message):
        return None

    if not _assistant_response_looks_like_reminder_offer(assistant_response):
        return None

    # Reuse the existing deterministic parser, but feed it an explicit reminder
    # request reconstructed from the assistant confirmation text.
    parsed_from_offer = parse_nudge_request(
        user_message=f"ingetin aku {assistant_response}",
        client_context=client_context,
    )
    if not parsed_from_offer:
        return None

    title = _title_from_confirmation_offer(assistant_response)
    return ParsedNudge(
        due_at=parsed_from_offer.due_at,
        title=title,
        message=_build_nudge_message(title=title, user_message="ingetin aku"),
    )


def parse_nudge_request(
    *,
    user_message: str,
    client_context: dict[str, Any] | None = None,
) -> ParsedNudge | None:
    normalized = _normalize(user_message)
    if not should_attempt_proactive_nudge(normalized):
        return None

    now = _client_now(client_context)
    relative_due = _extract_relative_due(now, normalized)

    if relative_due:
        due_local = relative_due
    else:
        base_day = _resolve_due_date(now, normalized)
        time_parts = _extract_explicit_time(normalized) or _extract_time_of_day_default(normalized)

        if not time_parts:
            # If user gives date but no time, choose a gentle default.
            if any(token in normalized for token in ("besok", "tomorrow", "lusa", "minggu depan", "next week")):
                time_parts = (9, 0)
            else:
                return None

        due_local = base_day.replace(
            hour=time_parts[0],
            minute=time_parts[1],
            second=0,
            microsecond=0,
        )

        # If user says "ingetin aku jam 8" and 8 already passed today, schedule tomorrow.
        if due_local <= now + timedelta(seconds=30):
            due_local += timedelta(days=1)

    if due_local > now + timedelta(days=MAX_DUE_DAYS):
        return None

    title = _clean_title(user_message)
    message = _build_nudge_message(title=title, user_message=user_message)

    return ParsedNudge(
        due_at=due_local.astimezone(timezone.utc),
        title=title,
        message=message,
    )


async def schedule_from_chat(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    client_context: dict[str, Any] | None = None,
    assistant_response: str | None = None,
) -> dict[str, Any]:
    parsed = parse_nudge_request(user_message=user_message, client_context=client_context)
    if not parsed:
        return {"scheduled": False, "reason": "not_a_nudge_or_missing_time"}

    payload = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "status": "scheduled",
        "due_at": parsed.due_at.isoformat(),
        "title": parsed.title,
        "message": parsed.message,
        "source_user_message": user_message[:1000],
    }

    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("proactive_nudges").insert(payload).execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("proactive_nudges: schedule failed: %s", exc)
        return {"scheduled": False, "reason": "insert_failed"}

    log.info(
        "proactive_nudges: scheduled user=%s convo=%s due_at=%s title=%s",
        user_id[:8],
        conversation_id[:8],
        parsed.due_at.isoformat(),
        parsed.title[:80],
    )

    return {"scheduled": True, "data": result.data}


async def deliver_due_nudges(limit: int = 20) -> int:
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("proactive_nudges")
                .select("id, user_id, conversation_id, message")
                .eq("status", "scheduled")
                .lte("due_at", now_iso)
                .order("due_at")
                .limit(limit)
                .execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("proactive_nudges: load due failed: %s", exc)
        return 0

    delivered = 0

    for row in list(result.data or []):
        nudge_id = str(row.get("id"))
        conversation_id = str(row.get("conversation_id"))
        message = str(row.get("message") or "").strip()
        if not nudge_id or not conversation_id or not message:
            continue

        try:
            # Claim first to avoid duplicate sends across multiple Fly machines.
            claim = await asyncio.to_thread(
                lambda: safe_execute(
                    lambda sb: sb.table("proactive_nudges")
                    .update({"status": "processing", "updated_at": now_iso})
                    .eq("id", nudge_id)
                    .eq("status", "scheduled")
                    .execute()
                )
            )

            if not claim.data:
                continue

            inserted = await asyncio.to_thread(
                lambda: safe_execute(
                    lambda sb: sb.table("messages")
                    .insert(
                        {
                            "conversation_id": conversation_id,
                            "role": "assistant",
                            "content": message,
                        }
                    )
                    .execute()
                )
            )

            delivered_message_id = None
            if inserted.data:
                delivered_message_id = inserted.data[0].get("id")

            finished_at = datetime.now(timezone.utc).isoformat()

            await asyncio.to_thread(
                lambda: safe_execute(
                    lambda sb: sb.table("proactive_nudges")
                    .update(
                        {
                            "status": "sent",
                            "delivered_message_id": delivered_message_id,
                            "delivered_at": finished_at,
                            "updated_at": finished_at,
                            "last_error": None,
                        }
                    )
                    .eq("id", nudge_id)
                    .execute()
                )
            )

            await asyncio.to_thread(
                lambda: safe_execute(
                    lambda sb: sb.table("conversations")
                    .update({"updated_at": finished_at})
                    .eq("id", conversation_id)
                    .execute()
                )
            )

            delivered += 1
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)[:500]
            log.warning("proactive_nudges: deliver failed id=%s err=%s", nudge_id, error_text)
            try:
                await asyncio.to_thread(
                    lambda: safe_execute(
                        lambda sb: sb.table("proactive_nudges")
                        .update(
                            {
                                "status": "failed",
                                "last_error": error_text,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        .eq("id", nudge_id)
                        .execute()
                    )
                )
            except Exception:
                pass

    if delivered:
        log.info("proactive_nudges: delivered=%d", delivered)

    return delivered


async def _scheduler_loop() -> None:
    global _STOP_EVENT

    if _STOP_EVENT is None:
        _STOP_EVENT = asyncio.Event()

    while not _STOP_EVENT.is_set():
        try:
            await deliver_due_nudges()
        except Exception as exc:  # noqa: BLE001
            log.warning("proactive_nudges: scheduler tick failed: %s", exc)

        try:
            await asyncio.wait_for(_STOP_EVENT.wait(), timeout=POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


async def start_proactive_nudge_scheduler() -> None:
    global _SCHEDULER_TASK, _STOP_EVENT

    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        return

    _STOP_EVENT = asyncio.Event()
    _SCHEDULER_TASK = asyncio.create_task(_scheduler_loop())
    log.info("proactive_nudges: scheduler started")


async def stop_proactive_nudge_scheduler() -> None:
    global _SCHEDULER_TASK, _STOP_EVENT

    if _STOP_EVENT:
        _STOP_EVENT.set()

    if _SCHEDULER_TASK:
        _SCHEDULER_TASK.cancel()
        try:
            await _SCHEDULER_TASK
        except asyncio.CancelledError:
            pass

    _SCHEDULER_TASK = None
    _STOP_EVENT = None
    log.info("proactive_nudges: scheduler stopped")
