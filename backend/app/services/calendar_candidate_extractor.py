"""Deterministic calendar candidate extraction from chat.

This extractor turns natural language event mentions into memory-backed calendar
candidates. It never creates Google Calendar events directly.

Examples:
- "besok jam 3 sore meeting sama GH Risk bahas Indosat"
- "tomorrow 3 PM call with John"
- "lusa presentasi ke direktur"

The resulting memory appears in Memories → Calendar and still requires explicit
approval + Memory PIN before syncing to Google Calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import logging
import re
from typing import Any

from app.services.embeddings import embed_document
from app.services.supabase_client import safe_execute
from app.services import calendar_intent
from app.services.memory_user_facing_safety import human_calendar_structured_value

log = logging.getLogger(__name__)


_EVENT_KEYWORDS = (
    "meeting",
    "meet",
    "call",
    "zoom",
    "gmeet",
    "google meet",
    "presentasi",
    "presentation",
    "rapat",
    "ketemu",
    "diskusi",
    "briefing",
    "review",
    "deadline",
    "appointment",
    "janji",
    "agenda",
    "interview",
    "acara",
    "sharing session",
    "session",
    "seminar",
    "workshop",
)

_REMINDER_KEYWORDS = (
    "ingatkan aku",
    "ingetin aku",
    "tolong ingatkan",
    "tolong ingetin",
    "remind me",
    "reminder",
    "set reminder",
    "buat reminder",
    "bikin reminder",
    "kasih reminder",
    "jangan lupa ingatkan",
)

_EXPLICIT_CALENDAR_COMMANDS = (
    "masukin ke kalender",
    "masukkan ke kalender",
    "tambahin ke kalender",
    "tambahkan ke kalender",
    "catat ke kalender",
    "masukin kalender",
    "masukkan kalender",
    "tambahin kalender",
    "tambahkan kalender",
    "catat kalender",
    "add to calendar",
    "put on calendar",
    "schedule",
    "jadwalkan",
)

_DATE_SIGNALS = (
    "hari ini",
    "pagi ini",
    "siang ini",
    "sore ini",
    "malam ini",
    "nanti",
    "today",
    "besok",
    "tomorrow",
    "lusa",
    "minggu depan",
    "next week",
    "senin",
    "selasa",
    "rabu",
    "kamis",
    "jumat",
    "jum'at",
    "sabtu",
    "minggu",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

_TIME_SIGNAL_RE = re.compile(
    r"\b(?:jam|pukul|at)?\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|pagi|siang|sore|malam)?\b",
    re.IGNORECASE,
)

_TIME_RANGE_RE = re.compile(
    r"\b(?:jam|pukul|at)?\s*(\d{1,2})(?:[:.](\d{2}))?\s*(?:-|–|—|sampai|sd|s/d|to)\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|pagi|siang|sore|malam)?\b",
    re.IGNORECASE,
)

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
class CalendarCandidate:
    title: str
    event_date: str
    start_at: str | None
    end_at: str | None
    all_day: bool
    structured_value: str
    content: str
    evidence: list[str]
    confidence: float
    reason: str
    location: str | None = None


def has_calendar_signal(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    has_event_keyword = any(keyword in normalized for keyword in _EVENT_KEYWORDS)
    has_date_signal = any(signal in normalized for signal in _DATE_SIGNALS)
    has_time_signal = _looks_like_time_mention(normalized)
    has_explicit_calendar_command = any(
        command in normalized for command in _EXPLICIT_CALENDAR_COMMANDS
    )
    has_reminder_keyword = any(keyword in normalized for keyword in _REMINDER_KEYWORDS)

    # Reminder language + date/time is enough, even without a meeting/event noun.
    if has_reminder_keyword and (has_date_signal or has_time_signal):
        return True

    # Explicit calendar command + date/time is enough, even when the event noun is unusual.
    if has_explicit_calendar_command and (has_date_signal or has_time_signal):
        return True

    # Meeting/call/session/event + date or time is strong enough.
    if has_event_keyword and (has_date_signal or has_time_signal):
        return True

    # Explicit deadline/schedule language with date is enough.
    if any(word in normalized for word in ("deadline", "jadwal", "agenda", "acara")) and has_date_signal:
        return True

    return False


def should_attempt_calendar_candidate_extraction(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    if has_calendar_signal(normalized):
        return True

    if any(command in normalized for command in _EXPLICIT_CALENDAR_COMMANDS):
        return True

    if any(keyword in normalized for keyword in _REMINDER_KEYWORDS):
        return True

    contextual_terms = (
        "calendar candidate",
        "calender candidate",
        "kalendar candidate",
        "kalender candidate",
        "kandidat kalender",
        "kandidat calendar",
        "candidate kalender",
        "candidate calendar",
    )

    return any(term in normalized for term in contextual_terms)


def _is_reminder_request(normalized: str) -> bool:
    return any(keyword in normalized for keyword in _REMINDER_KEYWORDS)


def _clean_reminder_title(text: str) -> str:
    title = _build_title(text).strip()

    cleanup_patterns = [
        r"^(tolong\s+)?ingatkan\s+aku\s+(untuk\s+)?",
        r"^(tolong\s+)?ingetin\s+aku\s+(untuk\s+)?",
        r"^remind\s+me\s+(to\s+)?",
        r"^set\s+reminder\s+(to\s+)?",
        r"^buat\s+reminder\s+(untuk\s+)?",
        r"^bikin\s+reminder\s+(untuk\s+)?",
        r"^kasih\s+reminder\s+(untuk\s+)?",
    ]

    cleaned = title
    for pattern in cleanup_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned[:120] or title[:120] or "Reminder"


def extract_candidate(
    *,
    text: str,
    base_date: date | None = None,
    timezone_offset_minutes: int | None = None,
) -> CalendarCandidate | None:
    normalized = _normalize(text)
    if not has_calendar_signal(normalized):
        return None

    base = base_date or date.today()
    event_date = _resolve_event_date(normalized, base)
    if not event_date:
        return None

    time_range = _extract_time_range(normalized)
    local_time = time_range[0] if time_range else _extract_time(normalized)
    start_at = None
    end_at = None
    all_day = True

    if local_time:
        all_day = False
        offset = timezone_offset_minutes if timezone_offset_minutes is not None else 420
        tz = timezone(timedelta(minutes=offset))
        start_dt = datetime.combine(event_date, local_time, tzinfo=tz)
        if time_range:
            end_dt = datetime.combine(event_date, time_range[1], tzinfo=tz)
            if end_dt <= start_dt:
                end_dt = end_dt + timedelta(days=1)
        else:
            end_dt = start_dt + timedelta(hours=1)
        start_at = start_dt.isoformat()
        end_at = end_dt.isoformat()

    is_reminder = _is_reminder_request(normalized)
    title = _clean_reminder_title(text) if is_reminder else _build_title(text)
    event_date_iso = event_date.isoformat()
    location = None if is_reminder else _extract_location_hint(text)

    value_parts = [
        title,
        f"due_date={event_date_iso}",
    ]
    if start_at:
        value_parts.append(f"start_at={start_at}")
    if end_at:
        value_parts.append(f"end_at={end_at}")
    if location:
        value_parts.append(f"location={location}")

    content = (
        f"User wants a reminder: {title} on {event_date_iso}"
        if is_reminder
        else f"User has a scheduled event: {title} on {event_date_iso}"
    )
    if location:
        content += f" at {location}"

    return CalendarCandidate(
        title=title,
        event_date=event_date_iso,
        start_at=start_at,
        end_at=end_at,
        all_day=all_day,
        structured_value=human_calendar_structured_value(title=title, event_date=event_date_iso, start_at=start_at, end_at=end_at, location=location),
        content=content,
        evidence=[text[:220]],
        confidence=0.9 if is_reminder and local_time else 0.86 if local_time else 0.78,
        reason="deterministic_reminder_candidate" if is_reminder else "deterministic_calendar_candidate",
        location=location,
    )


async def extract_and_persist(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    client_context: dict[str, Any] | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base_date = _base_date_from_client_context(client_context)
    tz_offset = _timezone_offset_from_client_context(client_context)

    candidate = extract_candidate(
        text=user_message,
        base_date=base_date,
        timezone_offset_minutes=tz_offset,
    )
    if not candidate:
        try:
            intent_draft = await calendar_intent.extract_calendar_intent_draft(
                user_message=user_message,
                recent_messages=recent_messages,
                client_context=client_context,
            )
            if intent_draft:
                candidate = _candidate_from_intent_draft(intent_draft, user_message)
        except Exception as exc:  # noqa: BLE001
            log.warning("calendar_candidate_extractor: haiku intent fallback failed: %s", exc)

    if not candidate:
        return {"candidate": False, "saved": False}

    # Avoid duplicate candidate from repeated sends.
    existing = await _find_existing_calendar_item(
        user_id=user_id,
        title=candidate.title,
        event_date=candidate.event_date,
        start_at=candidate.start_at,
        end_at=candidate.end_at,
    )
    if existing:
        return {"candidate": True, "saved": False, "duplicate": True, "id": existing}

    try:
        embedding = await embed_document(candidate.content)
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_candidate_extractor: embedding failed: %s", exc)
        return {"candidate": True, "saved": False, "error": "embedding_failed"}

    row = {
        "user_id": user_id,
        "content": candidate.content,
        "kind": "plan",
        "category": "goals",
        "structured_field": "scheduled_event",
        "structured_value": candidate.structured_value,
        "source_priority": "explicit_user_statement",
        "confidence": candidate.confidence,
        "evidence": candidate.evidence,
        "source": "auto",
        "source_conversation_id": conversation_id,
        "embedding": embedding,
        "due_date": candidate.event_date,
        "expires_at": _expiry_for_event_date(candidate.event_date),
        "calendar_candidate": True,
        "calendar_event_title": candidate.title,
        "calendar_event_date": candidate.event_date,
        "calendar_event_start_at": candidate.start_at,
        "calendar_event_end_at": candidate.end_at,
        "calendar_event_all_day": candidate.all_day,
        "calendar_event_location": candidate.location,
        "lifecycle_type": "time_bound",
    }

    try:
        result = safe_execute(lambda sb: sb.table("memories").insert(row).execute())
        inserted = (result.data or [{}])[0]
        return {"candidate": True, "saved": True, "id": inserted.get("id")}
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_candidate_extractor: insert failed: %s", exc)
        return {"candidate": True, "saved": False, "error": str(exc)[:200]}


def _candidate_from_intent_draft(draft: dict[str, Any], source_text: str) -> CalendarCandidate | None:
    title = _clean_calendar_event_title(draft.get("title"))
    event_date = str(draft.get("event_date") or "").strip()
    start_at = draft.get("start_at")
    end_at = draft.get("end_at")
    all_day = bool(draft.get("all_day"))
    raw_location = str(draft.get("location") or "").strip()
    location = raw_location[:180] if raw_location else _extract_location_hint(source_text)
    confidence = float(draft.get("confidence") or 0.72)
    reason = str(draft.get("reason") or "haiku_calendar_intent").strip()

    if not title or not event_date:
        return None

    value_parts = [
        title,
        f"due_date={event_date}",
    ]

    if start_at:
        value_parts.append(f"start_at={start_at}")
    if end_at:
        value_parts.append(f"end_at={end_at}")
    if location:
        value_parts.append(f"location={location}")

    content = f"User has a scheduled event: {title} on {event_date}"
    if location:
        content += f" at {location}"

    return CalendarCandidate(
        title=title,
        event_date=event_date,
        start_at=str(start_at) if start_at else None,
        end_at=str(end_at) if end_at else None,
        all_day=all_day,
        structured_value=human_calendar_structured_value(title=title, event_date=event_date, start_at=str(start_at) if start_at else None, end_at=str(end_at) if end_at else None, location=str(location) if location else None),
        content=content,
        evidence=[source_text[:220]],
        confidence=max(0.62, min(confidence, 0.94)),
        reason=reason or "haiku_calendar_intent",
        location=str(location) if location else None,
    )



async def _find_existing_calendar_item(
    *,
    user_id: str,
    title: str,
    event_date: str,
    start_at: str | None = None,
    end_at: str | None = None,
) -> str | None:
    """Avoid duplicate hidden suggestions/events from repeated chat sends.

    We check pending suggestions, confirmed local events, and synced Google events
    for the same date/title/time before inserting a new hidden suggestion.
    """
    normalized_title = _normalise_title_for_dedupe(title)
    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id, calendar_event_title, calendar_event_location, structured_value, content, due_date, "
                "calendar_event_date, calendar_event_start_at, calendar_event_end_at, "
                "calendar_candidate, calendar_event_status, archived, superseded"
            )
            .eq("user_id", user_id)
            .eq("archived", False)
            .eq("superseded", False)
            .or_("calendar_candidate.eq.true,calendar_event_status.in.(confirmed_local,synced_google)")
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_candidate_extractor: broad duplicate check failed: %s", exc)
        return None

    for row in result.data or []:
        row_date = str(row.get("calendar_event_date") or row.get("due_date") or "").strip()
        if row_date != event_date:
            continue

        row_title = _normalise_title_for_dedupe(
            str(row.get("calendar_event_title") or row.get("structured_value") or row.get("content") or "")
        )
        if not row_title:
            continue

        same_title = normalized_title == row_title or normalized_title in row_title or row_title in normalized_title
        same_time = _same_calendar_time_for_dedupe(
            row_start=row.get("calendar_event_start_at"),
            row_end=row.get("calendar_event_end_at"),
            start_at=start_at,
            end_at=end_at,
        )

        # If exact date/time matches, treat it as the same calendar item even
        # when Haiku/deterministic extraction produced a slightly different title.
        if same_time and (same_title or bool(start_at)):
            return str(row.get("id"))

    return None



def _same_calendar_time_for_dedupe(
    *,
    row_start: object,
    row_end: object,
    start_at: str | None,
    end_at: str | None,
) -> bool:
    row_start_text = str(row_start or "").strip()
    row_end_text = str(row_end or "").strip()
    start_text = str(start_at or "").strip()
    end_text = str(end_at or "").strip()

    if start_text and row_start_text and start_text != row_start_text:
        return False
    if end_text and row_end_text and end_text != row_end_text:
        return False
    return True




_LOCATION_STOPWORDS = {
    "hari",
    "tanggal",
    "tgl",
    "jam",
    "pukul",
    "bulan",
    "tahun",
    "minggu",
    "senin",
    "selasa",
    "rabu",
    "kamis",
    "jumat",
    "sabtu",
    "sana",
    "sini",
    "situ",
    "mana",
}


def _extract_location_hint(value: str | None) -> str | None:
    """Conservatively extract an event location from free text.

    Matches `di/at <Proper Noun Phrase>` and stops before companions/times
    (`dengan`, `sama`, `with`, `jam`, `tee off`, ...). Requires the location
    to start with an uppercase letter so people-free generic words ("di
    rumah", "di sana") and day names ("di hari Minggu") are never captured.
    Returns None when nothing matches confidently.
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return None

    pattern = re.compile(
        r"\b(?:di|at)\s+"
        r"(?P<location>[^,;()\n]{2,80}?)"
        r"(?=\s+(?:dengan|sama|bersama|with|jam|pukul|tee\s*off|mulai|start\w*|sekitar|on|pada)\b"
        r"|[,;()\n]|[.!?]\s|$)",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        location = match.group("location").strip().rstrip(".!?")
        if not location or len(location) > 80:
            continue
        if not location[0].isupper():
            continue
        first_token = location.split()[0].lower()
        if first_token in _LOCATION_STOPWORDS:
            continue
        return location

    return None


def _extract_canonical_calendar_title_hint(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text

    human_structured = re.match(
        r"^Calendar event:\s*(.+?)(?:;\s*(?:date|starts|ends|location)\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if human_structured:
        text = human_structured.group(1).strip()

    text = re.sub(
        r"^User has a scheduled event:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s+on\s+\d{4}-\d{2}-\d{2}.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*\|\s*due_date=.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"^.*?\b(?:agenda|acara|jadwal)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"[,;]\s*(?:tee\s*off|mulai|starts?|starting|pukul|jam)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+tee\s*off(?:\s+nya)?\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    location_between = re.match(
        r"^(?P<activity>[^,;]{1,60}?)\s+"
        r"(?P<location_connector>di|at)\s+"
        r"(?P<location>[^,;]{1,100}?)\s+"
        r"(?P<party_connector>dengan|sama|with)\s+"
        r"(?P<party>[^,;]{1,80})$",
        text,
        flags=re.IGNORECASE,
    )

    if location_between:
        activity = location_between.group("activity").strip()
        connector = location_between.group("party_connector").lower()
        party = location_between.group("party").strip()

        if connector == "with":
            text = f"{activity} with {party}"
        elif connector == "sama":
            text = f"{activity} sama {party}"
        else:
            text = f"{activity} dengan {party}"

    return re.sub(r"\s+", " ", text).strip()


def _clean_calendar_event_title(value: str | None) -> str:
    """Clean user-message fragments into agenda-like event titles.

    Examples:
    - "sekarang padel di Parta Kuningan" -> "Padel di Parta Kuningan"
    - "nanti mau ke Epiwalk Mall" -> "Epiwalk Mall"
    - "ini mau Bowling sama Mandiri Club" -> "Bowling sama Mandiri Club"
    - "Ke FX Sudirman" -> "FX Sudirman"
    """
    import re

    text = _extract_canonical_calendar_title_hint(
        str(value or "").strip()
    )
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*\|\s*due_date=.*$", "", text, flags=re.I)
    text = re.sub(r"^user has a scheduled event:\s*", "", text, flags=re.I)
    text = re.sub(r"\s+on\s+\d{4}-\d{2}-\d{2}.*$", "", text, flags=re.I)

    # Remove common conversational lead-ins.
    text = re.sub(
        r"^(?:beb|sayang|yang|aku|saya|gue|gw|gua)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^(?:sekarang|nanti|besok|lusa|hari ini|pagi ini|siang ini|sore ini|malam ini)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^(?:ini\s+)?(?:mau|akan|bakal|hendak)\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^(?:ada\s+)?(?:acara|agenda|jadwal)\s+",
        "",
        text,
        flags=re.I,
    )

    # "ke FX", "ke dentist", "ke Epiwalk" is usually a destination title.
    text = re.sub(r"^ke\s+", "", text, flags=re.I)

    # Remove casual trailing filler.
    text = re.sub(r"\s+(?:ya|yah|dong|deh|nih|sih|ah|hehe|beb)$", "", text, flags=re.I)

    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")
    if not text:
        return "Calendar event"

    # Preserve acronyms like FX/SCBD reasonably by only uppercasing first char.
    return text[:1].upper() + text[1:]

def _normalise_title_for_dedupe(value: str) -> str:
    import re

    text = str(value or "").casefold()
    text = re.sub(r"\s*\|\s*due_date=.*$", "", text)
    text = re.sub(r"^user has a scheduled event:\s*", "", text)
    text = re.sub(r"\s+on\s+\d{4}-\d{2}-\d{2}.*$", "", text)
    text = re.sub(r"[^a-z0-9À-ÖØ-öø-ÿ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _find_existing_candidate(*, user_id: str, title: str, event_date: str) -> str | None:
    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .select("id")
            .eq("user_id", user_id)
            .eq("structured_field", "scheduled_event")
            .eq("calendar_event_date", event_date)
            .eq("calendar_event_title", title)
            .eq("archived", False)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0].get("id") if rows else None
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_candidate_extractor: duplicate check failed: %s", exc)
        return None


def _resolve_event_date(text: str, base: date) -> date | None:
    if any(
        phrase in text
        for phrase in (
            "hari ini",
            "pagi ini",
            "siang ini",
            "sore ini",
            "malam ini",
            "nanti",
            "today",
        )
    ):
        return base
    if "besok" in text or "tomorrow" in text:
        return base + timedelta(days=1)
    if "lusa" in text:
        return base + timedelta(days=2)

    # YYYY-MM-DD explicit date.
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # dd/mm or dd-mm with current year.
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", text)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else base.year
        try:
            parsed = date(year, month, day)
            if parsed < base and not m.group(3):
                parsed = date(year + 1, month, day)
            return parsed
        except ValueError:
            return None

    for name, target_idx in _WEEKDAY_INDEX.items():
        if name in text:
            days_ahead = (target_idx - base.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return base + timedelta(days=days_ahead)

    return None


def _extract_time(text: str) -> time | None:
    for match in _TIME_SIGNAL_RE.finditer(text):
        raw_hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        suffix = (match.group(3) or "").casefold()

        if raw_hour > 23 or minute > 59:
            continue

        # Avoid treating dates like 2026 or "21" without time marker as time.
        prefix = text[max(0, match.start() - 8): match.start()].strip()
        has_time_marker = any(marker in prefix for marker in ("jam", "pukul", "at"))

        raw_hour = _apply_period(raw_hour, suffix)

        if not has_time_marker and not suffix and match.group(2) is None:
            continue

        try:
            return time(raw_hour, minute)
        except ValueError:
            continue

    return None


def _extract_time_range(text: str) -> tuple[time, time] | None:
    match = _TIME_RANGE_RE.search(text)
    if not match:
        return None

    start_hour = int(match.group(1))
    start_minute = int(match.group(2) or 0)
    end_hour = int(match.group(3))
    end_minute = int(match.group(4) or 0)
    suffix = (match.group(5) or "").casefold()
    if not suffix:
        prefix = text[max(0, match.start() - 24):match.start()].casefold()
        for period in ("pagi", "siang", "sore", "malam"):
            if period in prefix:
                suffix = period
                break

    start_hour = _apply_period(start_hour, suffix)
    end_hour = _apply_period(end_hour, suffix)

    try:
        return time(start_hour, start_minute), time(end_hour, end_minute)
    except ValueError:
        return None


def _apply_period(hour: int, suffix: str) -> int:
    if suffix == "pm" and hour < 12:
        return hour + 12
    if suffix == "am" and hour == 12:
        return 0
    if suffix in {"sore", "malam"} and 1 <= hour <= 11:
        return hour + 12
    if suffix == "siang" and 1 <= hour <= 10:
        return hour + 12
    return hour


def _looks_like_time_mention(text: str) -> bool:
    return _extract_time(text) is not None


def _build_title(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    cleaned = re.sub(r"(?i)\b(beb|tolong|please|ya)\b", " ", cleaned)
    cleaned = re.sub(
        r"(?i)\b(masukin|masukkan|tambahin|tambahkan|input|catat|buat|bikin)\b.{0,35}\b(kalender|calendar|jadwal)\b[:,]?",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\b(jadwalkan|schedule|add to calendar|put on calendar)\b[:,]?", " ", cleaned)
    cleaned = re.sub(
        r"(?i)\b(hari ini|today|besok|tomorrow|lusa|jam|pukul|at|aku|saya|gue|gw|ada|acara)\b",
        " ",
        cleaned,
    )
    cleaned = _TIME_RANGE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}([:.]\d{2})?\s*(am|pm|pagi|siang|sore|malam)?\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")

    if not cleaned:
        return "Scheduled event"

    # Prefer concise but useful title.
    if len(cleaned) > 120:
        cleaned = cleaned[:117].rstrip() + "..."

    return _clean_calendar_event_title(cleaned)


def _base_date_from_client_context(client_context: dict[str, Any] | None) -> date | None:
    if not isinstance(client_context, dict):
        return None

    for key in ("local_date", "date"):
        value = client_context.get(key)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                pass

    local_time = client_context.get("local_time") or client_context.get("timestamp")
    if isinstance(local_time, str):
        try:
            return datetime.fromisoformat(local_time.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    return None


def _timezone_offset_from_client_context(client_context: dict[str, Any] | None) -> int | None:
    if not isinstance(client_context, dict):
        return None

    value = client_context.get("timezone_offset_minutes")
    if isinstance(value, int):
        return value

    value = client_context.get("utc_offset_minutes")
    if isinstance(value, int):
        return value

    # JS Date.getTimezoneOffset() is inverse sign; support it if passed.
    value = client_context.get("js_timezone_offset_minutes")
    if isinstance(value, int):
        return -value

    return None


def _expiry_for_event_date(event_date: str) -> str:
    parsed = date.fromisoformat(event_date)
    expires = datetime.combine(parsed + timedelta(days=1), time(23, 59, 59), tzinfo=timezone.utc)
    return expires.isoformat()


def _normalize(text: str | None) -> str:
    value = (text or "").casefold()
    value = re.sub(r"\s+", " ", value).strip()
    return value
