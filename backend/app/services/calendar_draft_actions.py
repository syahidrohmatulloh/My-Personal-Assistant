"""Chat-driven actions for local Calendar drafts.

Supported v1:
- update local draft/candidate from chat
- archive/delete local draft/candidate from chat

Safety:
- Never syncs or deletes Google Calendar events directly from chat.
- If the matching record is synced_google, it returns a no-op that requires UI confirmation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from app.services.claude import get_claude
from app.services.embeddings import embed_document
from app.services.supabase_client import safe_execute
from app.services import calendar_conflicts
from app.services import calendar_intent
from app.services import calendar_pending_actions
from app.services.google_calendar_payload import build_google_event_body
from app.routers.calendar_oauth import (
    get_active_google_calendar_access_token,
    list_google_calendar_events_for_action,
)

log = logging.getLogger(__name__)

MODEL_NAME = "claude-haiku-4-5"

_UPDATE_TERMS = (
    "ubah",
    "ganti",
    "edit",
    "update",
    "revisi",
    "koreksi",
    "reschedule",
    "jadwal ulang",
    "mundurin",
    "majuin",
    "geser",
    "pindahin",
    "pindahkan",
)

_SOFT_UPDATE_TERMS = (
    "lebih detail",
    "lebih detil",
    "lebih spesifik",
    "dibuat lebih detail",
    "dibuat lebih detil",
    "dibikin lebih detail",
    "dibikin lebih detil",
    "buat lebih detail",
    "buat lebih detil",
    "bikin lebih detail",
    "bikin lebih detil",
    "perjelas",
    "perinci",
    "detailin",
    "detilin",
    "lebih jelas",
)


_DELETE_TERMS = (
    "hapus",
    "delete",
    "remove",
    "batalin",
    "batalkan",
    "cancel",
    "cancelled",
    "archive",
    "arsipkan",
)

_RECURRING_SCOPE_TERMS = (
    "yang ini saja",
    "hari ini saja",
    "kejadian ini saja",
    "jadwal ini saja",
    "ini dan seterusnya",
    "mulai ini ke depan",
    "semua jadwal",
    "semua rangkaian",
    "seluruh rangkaian",
    "entire series",
    "this instance",
    "this and following",
)


_CALENDAR_TERMS = (
    "calendar",
    "kalender",
    "jadwal",
    "event",
    "acara",
    "agenda",
)

_TARGET_HINTS = (
    "yang ",
    "event",
    "acara",
    "agenda",
    "jadwal",
    "jemput",
    "meeting",
    "padel",
    "bowling",
    "golf",
    "gym",
    "lomba",
    "dance",
)

SYSTEM_PROMPT = """You perform Calendar actions for a personal assistant app.

Return ONLY one JSON object. No markdown. No prose.

Schema:
{
  "is_calendar_action": true/false,
  "action": "update"|"delete"|"none",
  "target_memory_id": string|null,
  "title": string|null,
  "event_date": "YYYY-MM-DD"|null,
  "start_at": "YYYY-MM-DDTHH:MM:SS+07:00"|null,
  "end_at": "YYYY-MM-DDTHH:MM:SS+07:00"|null,
  "all_day": true/false|null,
  "location": string|null,
  "recurring_scope": "this_instance"|"this_and_following"|"entire_series"|null,
  "confidence": number,
  "reason": string
}

Rules:
- You are acting on local Calendar records and direct Google Calendar events supplied in calendar_records.
- Pick exactly one target from the provided calendar_records. Treat target_memory_id as an opaque record id; it may represent a local memory or a direct Google event.
- A record with source="google" is the authoritative direct Google Calendar event.
- If local and Google records describe the same title, date, start, and end, always choose the Google record.
- action="update" when the user asks to change time/date/title/location, or asks to make an event more detailed/specific/jelas/detil.
- action="delete" when the user asks to remove, cancel, hapus, batalin, delete, or archive an agenda/event.
- Return action="none" and confidence below 0.6 if the target is ambiguous.
- Preserve any field not changed by the user by returning null for that field. If the user asks for a more detailed event title/description, improve title/location using recent context and the target record.
- If changing start_at but end_at is not specified, infer a 1-hour duration unless the original record has a duration.
- Use browser local time context and recent chat context for relative times like "jam 3", "besok", "nanti", "yang tadi".
- For recurring events, set recurring_scope only when the user states it explicitly or is clearly replying to a recurring-scope question.
- "yang ini saja", "hari ini saja", or "kejadian ini saja" means this_instance.
- "ini dan seterusnya", "mulai ini ke depan", or equivalent means this_and_following.
- "semua", "seluruh rangkaian", or equivalent means entire_series.
- Never guess a recurring scope from an ordinary update/delete request.
- The caller executes the selected action. Return the intended action and exact target only; do not invent success.
"""


def is_calendar_draft_action_request(text: str | None) -> bool:
    normalized = _norm(text)
    if not normalized:
        return False

    has_update = any(term in normalized for term in _UPDATE_TERMS)
    has_delete = any(term in normalized for term in _DELETE_TERMS)
    has_soft_update = any(term in normalized for term in _SOFT_UPDATE_TERMS)
    has_recurring_scope = bool(
        calendar_pending_actions.parse_recurring_scope(
            normalized
        )
    )

    if not (
        has_update
        or has_delete
        or has_soft_update
        or has_recurring_scope
    ):
        return False

    if has_recurring_scope:
        return True

    has_calendar = any(term in normalized for term in _CALENDAR_TERMS)
    has_target_hint = any(term in normalized for term in _TARGET_HINTS)
    has_time_update = bool(re.search(r"\b(jam|pukul)\s*\d{1,2}", normalized))

    return has_calendar or has_target_hint or has_time_update or has_soft_update




def is_google_calendar_create_request(text: str | None) -> bool:
    normalized = _norm(text)
    if not normalized:
        return False

    create_terms = (
        "masukin",
        "masukkan",
        "tambahin",
        "tambahkan",
        "catat",
        "buat",
        "bikin",
        "add",
        "create",
        "sync",
    )

    google_calendar_terms = (
        "google calendar",
        "google kalender",
        "kalender google",
        "calendar google",
        "gcal",
        "google cal",
    )

    explicit_google_phrases = (
        "masukin ke google",
        "masukkan ke google",
        "tambahin ke google",
        "tambahkan ke google",
        "catat ke google",
        "buat ke google",
        "bikin ke google",
        "buat di google",
        "bikin di google",
        "add to google",
        "create in google",
        "sync ke google",
        "sync google",
    )

    has_calendar_word = any(term in normalized for term in ("calendar", "kalender", "agenda", "jadwal"))
    has_create = any(term in normalized for term in create_terms)
    has_google_calendar = any(term in normalized for term in google_calendar_terms)
    has_explicit_google_phrase = any(term in normalized for term in explicit_google_phrases)

    return (
        (has_create and has_google_calendar)
        or (has_calendar_word and has_explicit_google_phrase)
        or has_explicit_google_phrase
    )


def _calendar_create_fingerprint(
    *,
    title: str | None,
    event_date: str | None,
    start_at: str | None,
    end_at: str | None,
    location: str | None,
) -> tuple[str, str, str, str, str]:
    clean_title = " ".join(str(title or "").casefold().split())
    clean_location = " ".join(str(location or "").casefold().split())
    return (
        clean_title,
        str(event_date or "").strip(),
        _canonical_calendar_time(start_at),
        _canonical_calendar_time(end_at),
        clean_location,
    )


def _canonical_calendar_time(value: str | None) -> str:
    if not value:
        return ""

    raw = str(value).strip()
    try:
        return datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        ).isoformat()
    except Exception:
        return raw


def _calendar_memory_matches_draft(
    row: dict[str, Any],
    *,
    title: str,
    event_date: str,
    start_at: str | None,
    end_at: str | None,
    location: str | None,
) -> bool:
    return _calendar_create_fingerprint(
        title=row.get("calendar_event_title")
        or row.get("structured_value")
        or row.get("content"),
        event_date=row.get("calendar_event_date") or row.get("due_date"),
        start_at=row.get("calendar_event_start_at"),
        end_at=row.get("calendar_event_end_at"),
        location=row.get("calendar_event_location"),
    ) == _calendar_create_fingerprint(
        title=title,
        event_date=event_date,
        start_at=start_at,
        end_at=end_at,
        location=location,
    )


def _google_event_matches_draft(
    event: dict[str, Any],
    *,
    title: str,
    event_date: str,
    start_at: str | None,
    end_at: str | None,
    location: str | None,
) -> bool:
    return _calendar_create_fingerprint(
        title=event.get("title"),
        event_date=event.get("event_date"),
        start_at=event.get("start_at"),
        end_at=event.get("end_at"),
        location=event.get("location"),
    ) == _calendar_create_fingerprint(
        title=title,
        event_date=event_date,
        start_at=start_at,
        end_at=end_at,
        location=location,
    )


def _find_existing_calendar_memory_for_draft(
    *,
    user_id: str,
    title: str,
    event_date: str,
    start_at: str | None,
    end_at: str | None,
    location: str | None,
) -> dict[str, Any] | None:
    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id, content, structured_value, due_date, "
                "calendar_event_status, calendar_event_title, "
                "calendar_event_date, calendar_event_start_at, "
                "calendar_event_end_at, calendar_event_all_day, "
                "calendar_event_location, google_calendar_event_id, "
                "google_calendar_event_link, archived, superseded, "
                "created_at, updated_at"
            )
            .eq("user_id", user_id)
            .eq("archived", False)
            .eq("superseded", False)
            .or_("calendar_event_status.in.(confirmed_local,synced_google)")
            .eq("calendar_event_date", event_date)
            .order("updated_at", desc=True)
            .limit(20)
            .execute()
        )
    except Exception as exc:
        log.warning(
            "calendar_draft_actions: existing calendar memory lookup failed: %s",
            exc,
        )
        return None

    rows = [
        row for row in list(result.data or [])
        if _calendar_memory_matches_draft(
            row,
            title=title,
            event_date=event_date,
            start_at=start_at,
            end_at=end_at,
            location=location,
        )
    ]

    if not rows:
        return None

    synced = [
        row for row in rows
        if row.get("google_calendar_event_id")
        or row.get("calendar_event_status") == "synced_google"
    ]
    return (synced or rows)[0]


async def _find_existing_google_event_for_draft(
    *,
    user_id: str,
    title: str,
    event_date: str,
    start_at: str | None,
    end_at: str | None,
    location: str | None,
) -> dict[str, Any] | None:
    probe = start_at or f"{event_date}T00:00:00+07:00"

    try:
        parsed = datetime.fromisoformat(
            str(probe).replace("Z", "+00:00")
        )
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    start_dt = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=1)

    try:
        events = await list_google_calendar_events_for_action(
            user_id=user_id,
            start_dt=start_dt,
            end_dt=end_dt,
            time_zone="Asia/Jakarta",
        )
    except Exception as exc:
        log.warning(
            "calendar_draft_actions: existing google event lookup failed: %s",
            exc,
        )
        return None

    for event in events:
        if _google_event_matches_draft(
            event,
            title=title,
            event_date=event_date,
            start_at=start_at,
            end_at=end_at,
            location=location,
        ):
            return event

    return None


def _mark_memory_as_synced_google(
    *,
    user_id: str,
    memory_id: str,
    google_event_id: str,
    google_event_link: str | None,
    title: str,
    event_date: str,
    start_at: str | None,
    end_at: str | None,
    all_day: bool,
    location: str | None,
    source_reason: str,
) -> dict[str, Any]:
    now = _now_iso()
    structured_value = _structured_value(
        title=title,
        event_date=event_date,
        start_at=start_at,
        end_at=end_at,
        location=location,
    )

    result = safe_execute(
        lambda sb: sb.table("memories")
        .update(
            {
                "calendar_candidate": False,
                "calendar_event_status": "synced_google",
                "calendar_event_title": title,
                "calendar_event_date": event_date,
                "calendar_event_start_at": start_at,
                "calendar_event_end_at": end_at,
                "calendar_event_all_day": all_day,
                "calendar_event_location": location,
                "structured_field": "scheduled_event",
                "structured_value": structured_value,
                "due_date": event_date,
                "google_calendar_event_id": google_event_id,
                "google_calendar_event_link": google_event_link,
                "google_calendar_id": "primary",
                "calendar_synced_at": now,
                "calendar_sync_error": None,
                "updated_at": now,
            }
        )
        .eq("id", memory_id)
        .eq("user_id", user_id)
        .execute()
    )

    duplicate_cleanup = _archive_duplicate_calendar_memories_for_event(
        user_id=user_id,
        keep_memory_id=memory_id,
        title=title,
        event_date=event_date,
        start_at=start_at,
        end_at=end_at,
        location=location,
    )

    return {
        "attempted": True,
        "created": source_reason == "synced_existing_local_event",
        "reason": source_reason,
        "memory_id": memory_id,
        "title": title,
        "date": event_date,
        "start_at": start_at,
        "end_at": end_at,
        "location": location,
        "google_event_id": google_event_id,
        "google_event_link": google_event_link,
        "duplicate_cleanup": duplicate_cleanup,
        "data": result.data,
    }


def _insert_synced_memory_for_existing_google_event(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    draft: dict[str, Any],
    google_event: dict[str, Any],
    title: str,
    event_date: str,
    start_at: str | None,
    end_at: str | None,
    all_day: bool,
    location: str | None,
) -> dict[str, Any]:
    structured_value = _structured_value(
        title=title,
        event_date=event_date,
        start_at=start_at,
        end_at=end_at,
        location=location,
    )
    content = f"User has a scheduled event: {title} on {event_date}"
    if location:
        content += f" at {location}"

    now = _now_iso()
    row = {
        "user_id": user_id,
        "content": content,
        "kind": "plan",
        "category": "goals",
        "structured_field": "scheduled_event",
        "structured_value": structured_value,
        "source_priority": "explicit_user_statement",
        "confidence": float(draft.get("confidence") or 0.86),
        "evidence": [user_message[:220]],
        "source": "auto",
        "source_conversation_id": conversation_id,
        "due_date": event_date,
        "calendar_candidate": False,
        "calendar_event_status": "synced_google",
        "calendar_event_title": title,
        "calendar_event_date": event_date,
        "calendar_event_start_at": start_at,
        "calendar_event_end_at": end_at,
        "calendar_event_all_day": all_day,
        "calendar_event_location": location,
        "calendar_event_created_at": now,
        "google_calendar_event_id": google_event.get("id"),
        "google_calendar_event_link": google_event.get("html_link"),
        "google_calendar_id": "primary",
        "calendar_synced_at": now,
        "calendar_sync_error": None,
        "created_at": now,
        "updated_at": now,
    }

    result = safe_execute(lambda sb: sb.table("memories").insert(row).execute())

    return {
        "attempted": True,
        "created": False,
        "reason": "linked_existing_google_event",
        "title": title,
        "date": event_date,
        "start_at": start_at,
        "end_at": end_at,
        "location": location,
        "google_event_id": google_event.get("id"),
        "google_event_link": google_event.get("html_link"),
        "data": result.data,
    }


def _archive_duplicate_calendar_memories_for_event(
    *,
    user_id: str,
    keep_memory_id: str,
    title: str,
    event_date: str,
    start_at: str | None,
    end_at: str | None,
    location: str | None,
) -> dict[str, Any]:
    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id, content, structured_value, due_date, "
                "calendar_event_status, calendar_event_title, "
                "calendar_event_date, calendar_event_start_at, "
                "calendar_event_end_at, calendar_event_all_day, "
                "calendar_event_location, google_calendar_event_id, "
                "google_calendar_event_link, archived, superseded, "
                "created_at, updated_at"
            )
            .eq("user_id", user_id)
            .eq("archived", False)
            .eq("superseded", False)
            .eq("calendar_event_date", event_date)
            .or_("calendar_event_status.in.(confirmed_local,synced_google)")
            .limit(50)
            .execute()
        )
    except Exception as exc:
        log.warning(
            "calendar_draft_actions: duplicate cleanup lookup failed: %s",
            exc,
        )
        return {
            "attempted": True,
            "archived_count": 0,
            "reason": "lookup_failed",
        }

    duplicate_ids: list[str] = []
    for row in list(result.data or []):
        row_id = str(row.get("id") or "").strip()
        if not row_id or row_id == keep_memory_id:
            continue

        if _calendar_memory_matches_draft(
            row,
            title=title,
            event_date=event_date,
            start_at=start_at,
            end_at=end_at,
            location=location,
        ):
            duplicate_ids.append(row_id)

    if not duplicate_ids:
        return {
            "attempted": True,
            "archived_count": 0,
            "reason": "no_duplicates",
        }

    now = _now_iso()

    try:
        update_result = safe_execute(
            lambda sb: sb.table("memories")
            .update(
                {
                    "archived": True,
                    "superseded": True,
                    "updated_at": now,
                }
            )
            .in_("id", duplicate_ids)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        log.warning(
            "calendar_draft_actions: duplicate cleanup update failed: %s",
            exc,
        )
        return {
            "attempted": True,
            "archived_count": 0,
            "reason": "update_failed",
            "duplicate_ids": duplicate_ids,
        }

    return {
        "attempted": True,
        "archived_count": len(list(update_result.data or [])),
        "reason": "archived_duplicates",
        "duplicate_ids": duplicate_ids,
    }


async def create_google_calendar_event_from_chat(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    recent_messages: list[dict[str, Any]] | None = None,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not is_google_calendar_create_request(user_message):
        return {"attempted": False, "created": False, "reason": "not_google_calendar_create"}

    draft = await calendar_intent.extract_calendar_intent_draft(
        user_message=user_message,
        recent_messages=recent_messages,
        client_context=client_context,
    )
    if not draft:
        return {"attempted": True, "created": False, "reason": "no_confident_draft"}

    title = str(draft.get("title") or "").strip()
    event_date = str(draft.get("event_date") or "").strip()
    start_at = draft.get("start_at")
    end_at = draft.get("end_at")
    all_day = bool(draft.get("all_day"))

    if not title or not event_date:
        return {"attempted": True, "created": False, "reason": "missing_required_fields"}

    start_at_text = str(start_at) if start_at else None
    end_at_text = str(end_at) if end_at else None
    location_text = _clean_optional_text(draft.get("location"))

    existing_memory = _find_existing_calendar_memory_for_draft(
        user_id=user_id,
        title=title,
        event_date=event_date,
        start_at=start_at_text,
        end_at=end_at_text,
        location=location_text,
    )

    if existing_memory and existing_memory.get("google_calendar_event_id"):
        return {
            "attempted": True,
            "created": False,
            "reason": "calendar_event_already_synced",
            "memory_id": existing_memory.get("id"),
            "title": existing_memory.get("calendar_event_title") or title,
            "date": existing_memory.get("calendar_event_date") or event_date,
            "start_at": existing_memory.get("calendar_event_start_at") or start_at_text,
            "end_at": existing_memory.get("calendar_event_end_at") or end_at_text,
            "location": existing_memory.get("calendar_event_location") or location_text,
            "google_event_id": existing_memory.get("google_calendar_event_id"),
            "google_event_link": existing_memory.get("google_calendar_event_link"),
        }

    access_token = await get_active_google_calendar_access_token(user_id=user_id)

    existing_google = await _find_existing_google_event_for_draft(
        user_id=user_id,
        title=title,
        event_date=event_date,
        start_at=start_at_text,
        end_at=end_at_text,
        location=location_text,
    )

    if existing_memory and existing_google:
        return _mark_memory_as_synced_google(
            user_id=user_id,
            memory_id=str(existing_memory["id"]),
            google_event_id=str(existing_google.get("id") or ""),
            google_event_link=existing_google.get("html_link"),
            title=title,
            event_date=event_date,
            start_at=start_at_text,
            end_at=end_at_text,
            all_day=all_day or not bool(start_at_text),
            location=location_text,
            source_reason="linked_existing_google_event",
        )

    if existing_google:
        return _insert_synced_memory_for_existing_google_event(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            draft=draft,
            google_event=existing_google,
            title=title,
            event_date=event_date,
            start_at=start_at_text,
            end_at=end_at_text,
            all_day=all_day or not bool(start_at_text),
            location=location_text,
        )

    created = await _create_google_calendar_event(
        access_token=access_token,
        title=title,
        event_date=event_date,
        description=_google_event_description_from_draft(draft),
        start_at=start_at_text,
        end_at=end_at_text,
        location=location_text,
    )

    google_event_id = created.get("id")
    google_event_link = created.get("htmlLink")

    if not google_event_id:
        return {"attempted": True, "created": False, "reason": "google_missing_event_id"}

    structured_value = _structured_value(
        title=title,
        event_date=event_date,
        start_at=start_at_text,
        end_at=end_at_text,
        location=location_text,
    )
    content = f"User has a scheduled event: {title} on {event_date}"
    if location_text:
        content += f" at {location_text}"

    try:
        embedding = await embed_document(content)
    except Exception as exc:
        log.warning("calendar_draft_actions: embedding failed after google create: %s", exc)
        embedding = None

    now = _now_iso()
    row = {
        "user_id": user_id,
        "content": content,
        "kind": "plan",
        "category": "goals",
        "structured_field": "scheduled_event",
        "structured_value": structured_value,
        "source_priority": "explicit_user_statement",
        "confidence": float(draft.get("confidence") or 0.86),
        "evidence": [user_message[:220]],
        "source": "auto",
        "source_conversation_id": conversation_id,
        "due_date": event_date,
        "calendar_candidate": False,
        "calendar_event_status": "synced_google",
        "calendar_event_title": title,
        "calendar_event_date": event_date,
        "calendar_event_start_at": start_at_text,
        "calendar_event_end_at": end_at_text,
        "calendar_event_all_day": all_day or not bool(start_at_text),
        "calendar_event_location": location_text,
        "calendar_event_created_at": now,
        "google_calendar_event_id": google_event_id,
        "google_calendar_event_link": google_event_link,
        "google_calendar_id": "primary",
        "calendar_synced_at": now,
        "calendar_sync_error": None,
        "created_at": now,
        "updated_at": now,
    }
    if embedding is not None:
        row["embedding"] = embedding

    if existing_memory:
        return _mark_memory_as_synced_google(
            user_id=user_id,
            memory_id=str(existing_memory["id"]),
            google_event_id=str(google_event_id),
            google_event_link=google_event_link,
            title=title,
            event_date=event_date,
            start_at=start_at_text,
            end_at=end_at_text,
            all_day=all_day or not bool(start_at_text),
            location=location_text,
            source_reason="synced_existing_local_event",
        )

    result = safe_execute(lambda sb: sb.table("memories").insert(row).execute())
    inserted_rows = list(result.data or [])
    inserted_id = (
        str(inserted_rows[0].get("id"))
        if inserted_rows and inserted_rows[0].get("id")
        else ""
    )

    duplicate_cleanup = None
    if inserted_id:
        duplicate_cleanup = _archive_duplicate_calendar_memories_for_event(
            user_id=user_id,
            keep_memory_id=inserted_id,
            title=title,
            event_date=event_date,
            start_at=start_at_text,
            end_at=end_at_text,
            location=location_text,
        )

    return {
        "attempted": True,
        "created": True,
        "title": title,
        "date": event_date,
        "start_at": start_at_text,
        "end_at": end_at_text,
        "location": location_text,
        "google_event_id": google_event_id,
        "google_event_link": google_event_link,
        "duplicate_cleanup": duplicate_cleanup,
        "data": result.data,
    }


async def apply_chat_calendar_draft_action(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    recent_messages: list[dict[str, Any]] | None = None,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not is_calendar_draft_action_request(user_message):
        return {"attempted": False, "updated": False, "deleted": False, "reason": "not_calendar_action"}

    if calendar_pending_actions.is_recurring_scope_only_reply(
        user_message
    ):
        return await _resume_pending_recurring_action(
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
        )

    records, google_read_failed = await _load_calendar_action_records(
        user_id=user_id,
        client_context=client_context,
    )
    if not records:
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "reason": (
                "google_read_failed"
                if google_read_failed
                else "no_calendar_records"
            ),
        }

    raw_action = await _extract_action(
        user_message=user_message,
        recent_messages=recent_messages,
        client_context=client_context,
        calendar_records=records,
    )
    action = _normalise_action(raw_action, records)
    if not action:
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "reason": (
                "google_read_failed"
                if google_read_failed
                else "no_confident_action"
            ),
        }

    if _message_allows_calendar_conflict(user_message):
        action["allow_conflict"] = True

    target = next((row for row in records if str(row.get("id")) == action["target_memory_id"]), None)
    if not target:
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "reason": "target_not_found",
        }

    if target.get("_record_source") == "google":
        return await _apply_direct_google_action_with_pending_scope(
            user_id=user_id,
            conversation_id=conversation_id,
            target=target,
            action=action,
            calendar_records=records,
        )

    if _is_synced_google(target):
        return await _apply_synced_google_calendar_action(
            user_id=user_id,
            target=target,
            action=action,
        )

    if action["action"] == "delete":
        payload = _build_archive_payload()
        try:
            result = safe_execute(
                lambda sb: sb.table("memories")
                .update(payload)
                .eq("id", str(target["id"]))
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            log.warning("calendar_draft_actions: archive failed: %s", exc)
            return {"attempted": True, "updated": False, "deleted": False, "reason": "archive_failed"}

        return {
            "attempted": True,
            "updated": False,
            "deleted": True,
            "target_memory_id": target.get("id"),
            "title": _title_from_target(target),
            "data": result.data,
        }

    if action["action"] == "update":
        payload = _build_update_payload(target, action)
        if not payload:
            return {"attempted": True, "updated": False, "deleted": False, "reason": "empty_update"}

        try:
            result = safe_execute(
                lambda sb: sb.table("memories")
                .update(payload)
                .eq("id", str(target["id"]))
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            log.warning("calendar_draft_actions: update failed: %s", exc)
            return {"attempted": True, "updated": False, "deleted": False, "reason": "update_failed"}

        return {
            "attempted": True,
            "updated": True,
            "deleted": False,
            "target_memory_id": target.get("id"),
            "title": payload.get("calendar_event_title") or _title_from_target(target),
            "date": payload.get("calendar_event_date") or target.get("calendar_event_date") or target.get("due_date"),
            "start_at": payload.get("calendar_event_start_at") or target.get("calendar_event_start_at"),
            "end_at": payload.get("calendar_event_end_at") or target.get("calendar_event_end_at"),
            "location": payload.get("calendar_event_location") or target.get("calendar_event_location"),
            "data": result.data,
        }

    return {"attempted": True, "updated": False, "deleted": False, "reason": "unsupported_action"}



async def _apply_direct_google_action_with_pending_scope(
    *,
    user_id: str,
    conversation_id: str,
    target: dict[str, Any],
    action: dict[str, Any],
    calendar_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = await _apply_direct_google_calendar_action(
        user_id=user_id,
        target=target,
        action=action,
        calendar_records=calendar_records,
    )

    if result.get("reason") != "recurring_scope_required":
        return result

    try:
        pending = (
            calendar_pending_actions
            .create_pending_recurring_action(
                user_id=user_id,
                conversation_id=conversation_id,
                target=target,
                action=action,
            )
        )
    except Exception as exc:
        log.warning(
            "calendar_draft_actions: pending recurring action "
            "store failed error_type=%s",
            type(exc).__name__,
        )
        return {
            **result,
            "pending_action_saved": False,
        }

    return {
        **result,
        "pending_action_saved": True,
        "pending_action_id": pending.get("id"),
        "pending_action_expires_at": pending.get("expires_at"),
    }


async def _resume_pending_recurring_action(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
) -> dict[str, Any]:
    recurring_scope = (
        calendar_pending_actions.parse_recurring_scope(
            user_message
        )
    )

    if not recurring_scope:
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": "unknown",
            "source": "google",
            "reason": "invalid_recurring_scope_reply",
        }

    try:
        pending = (
            calendar_pending_actions
            .load_pending_recurring_action(
                user_id=user_id,
                conversation_id=conversation_id,
            )
        )
    except Exception as exc:
        log.warning(
            "calendar_draft_actions: pending recurring action "
            "load failed error_type=%s",
            type(exc).__name__,
        )
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": "unknown",
            "source": "google",
            "reason": "pending_recurring_action_load_failed",
        }

    if not pending:
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": "unknown",
            "source": "google",
            "reason": "no_pending_recurring_action",
            "recurring_scope": recurring_scope,
        }

    target = pending.get("target_snapshot")
    action = pending.get("requested_action")

    if not isinstance(target, dict) or not isinstance(
        action,
        dict,
    ):
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": str(
                pending.get("action_type") or "unknown"
            ),
            "source": "google",
            "reason": "invalid_pending_recurring_action",
            "pending_action_id": pending.get("id"),
        }

    resumed_action = {
        **action,
        "action": str(
            action.get("action")
            or pending.get("action_type")
            or ""
        ),
        "recurring_scope": recurring_scope,
    }

    calendar_records, _google_read_failed = (
        await _load_calendar_action_records(
            user_id=user_id,
            client_context=None,
        )
    )

    result = await _apply_direct_google_calendar_action(
        user_id=user_id,
        target=target,
        action=resumed_action,
        calendar_records=calendar_records,
    )

    result = {
        **result,
        "pending_action_id": pending.get("id"),
    }

    if calendar_action_succeeded(result):
        try:
            calendar_pending_actions                .mark_pending_recurring_action_completed(
                    pending_action_id=str(pending["id"]),
                    user_id=user_id,
                )
        except Exception as exc:
            log.warning(
                "calendar_draft_actions: pending recurring action "
                "completion failed error_type=%s",
                type(exc).__name__,
            )
            result["pending_completion_saved"] = False
        else:
            result["pending_completion_saved"] = True

    return result


async def _apply_direct_google_calendar_action(
    *,
    user_id: str,
    target: dict[str, Any],
    action: dict[str, Any],
    calendar_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    google_event_id = str(
        target.get("google_calendar_event_id") or ""
    ).strip()
    calendar_id = str(
        target.get("google_calendar_id") or "primary"
    ).strip() or "primary"

    if not google_event_id:
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": action.get("action"),
            "source": "google",
            "reason": "direct_google_missing_event_id",
        }

    is_recurring = bool(
        target.get("calendar_event_is_recurring")
        or target.get("google_recurring_event_id")
    )
    recurring_scope = str(
        action.get("recurring_scope") or ""
    ).strip() or None

    if is_recurring and not recurring_scope:
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": action.get("action"),
            "source": "google",
            "target_id": target.get("id"),
            "google_event_id": google_event_id,
            "title": _title_from_target(target),
            "reason": "recurring_scope_required",
            "recurring": True,
            "recurring_scope": None,
            "allowed_recurring_scopes": [
                "this_instance",
                "this_and_following",
                "entire_series",
            ],
        }

    if (
        is_recurring
        and recurring_scope != "this_instance"
    ):
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": action.get("action"),
            "source": "google",
            "target_id": target.get("id"),
            "google_event_id": google_event_id,
            "title": _title_from_target(target),
            "reason": "recurring_scope_not_supported_yet",
            "recurring": True,
            "recurring_scope": recurring_scope,
            "allowed_recurring_scopes": [
                "this_instance",
            ],
        }

    try:
        access_token = await get_active_google_calendar_access_token(
            user_id=user_id
        )
    except Exception as exc:
        log.warning(
            "calendar_draft_actions: direct google token failed error_type=%s",
            type(exc).__name__,
        )
        return {
            "attempted": True,
            "success": False,
            "updated": False,
            "deleted": False,
            "action": action.get("action"),
            "source": "google",
            "reason": "google_access_failed",
        }

    if action["action"] == "delete":
        try:
            await _delete_google_calendar_event(
                access_token=access_token,
                google_event_id=google_event_id,
                calendar_id=calendar_id,
            )
        except Exception as exc:
            log.warning(
                "calendar_draft_actions: direct google delete failed error_type=%s",
                type(exc).__name__,
            )
            return {
                "attempted": True,
                "success": False,
                "updated": False,
                "deleted": False,
                "action": "delete",
                "source": "google",
                "target_id": target.get("id"),
                "reason": "google_delete_failed",
            }

        return {
            "attempted": True,
            "success": True,
            "updated": False,
            "deleted": True,
            "action": "delete",
            "source": "google",
            "target_id": target.get("id"),
            "google_event_id": google_event_id,
            "title": _title_from_target(target),
            "reason": None,
            "recurring_scope": recurring_scope,
        }

    if action["action"] == "update":
        patch = _build_direct_google_patch(target, action)
        if not patch:
            return {
                "attempted": True,
                "success": False,
                "updated": False,
                "deleted": False,
                "action": "update",
                "source": "google",
                "target_id": target.get("id"),
                "reason": "empty_update",
            }

        merged = _build_update_payload(target, action)
        conflict_analysis = _detect_conflicts_for_calendar_payload(
            target=target,
            payload=merged,
            calendar_records=calendar_records or [],
        )

        if (
            conflict_analysis.get("has_conflicts")
            and not bool(action.get("allow_conflict"))
        ):
            return {
                "attempted": True,
                "success": False,
                "updated": False,
                "deleted": False,
                "action": "update",
                "source": "google",
                "target_id": target.get("id"),
                "google_event_id": google_event_id,
                "title": (
                    merged.get("calendar_event_title")
                    or _title_from_target(target)
                ),
                "date": merged.get("calendar_event_date"),
                "start_at": merged.get("calendar_event_start_at"),
                "end_at": merged.get("calendar_event_end_at"),
                "location": merged.get("calendar_event_location"),
                "reason": "calendar_conflict_requires_confirmation",
                "recurring_scope": recurring_scope,
                "conflict_analysis": conflict_analysis,
            }

        try:
            patched = await _patch_direct_google_calendar_event(
                access_token=access_token,
                google_event_id=google_event_id,
                calendar_id=calendar_id,
                patch=patch,
            )
        except Exception as exc:
            log.warning(
                "calendar_draft_actions: direct google patch failed error_type=%s",
                type(exc).__name__,
            )
            return {
                "attempted": True,
                "success": False,
                "updated": False,
                "deleted": False,
                "action": "update",
                "source": "google",
                "target_id": target.get("id"),
                "reason": "google_patch_failed",
            }

        return {
            "attempted": True,
            "success": True,
            "updated": True,
            "deleted": False,
            "action": "update",
            "source": "google",
            "target_id": target.get("id"),
            "google_event_id": google_event_id,
            "title": (
                patched.get("summary")
                or merged.get("calendar_event_title")
                or _title_from_target(target)
            ),
            "date": merged.get("calendar_event_date"),
            "start_at": merged.get("calendar_event_start_at"),
            "end_at": merged.get("calendar_event_end_at"),
            "location": merged.get("calendar_event_location"),
            "google_event_link": (
                patched.get("htmlLink")
                or target.get("google_calendar_event_link")
            ),
            "reason": None,
            "recurring_scope": recurring_scope,
            "conflict_analysis": conflict_analysis,
        }

    return {
        "attempted": True,
        "success": False,
        "updated": False,
        "deleted": False,
        "action": action.get("action"),
        "source": "google",
        "reason": "unsupported_direct_google_action",
    }


def _message_allows_calendar_conflict(
    user_message: str | None,
) -> bool:
    normalized = " ".join(
        str(user_message or "").casefold().split()
    )

    if not normalized:
        return False

    override_terms = (
        "tetap lanjut",
        "lanjut aja",
        "lanjut saja",
        "gas aja",
        "gapapa bentrok",
        "gak apa-apa bentrok",
        "tidak apa-apa bentrok",
        "override conflict",
        "ignore conflict",
    )

    return any(term in normalized for term in override_terms)


def _detect_conflicts_for_calendar_payload(
    *,
    target: dict[str, Any],
    payload: dict[str, Any],
    calendar_records: list[dict[str, Any]],
) -> dict[str, Any]:
    proposed_record = {
        **target,
        **payload,
        "id": target.get("id"),
        "google_calendar_event_id": target.get(
            "google_calendar_event_id"
        ),
        "_record_source": target.get("_record_source") or "google",
    }

    return calendar_conflicts.detect_calendar_conflicts(
        proposed_record=proposed_record,
        candidate_records=calendar_records,
        exclude_ids={
            str(target.get("id") or "").strip(),
        },
        exclude_google_event_ids={
            str(
                target.get("google_calendar_event_id") or ""
            ).strip(),
        },
    )


def _build_direct_google_patch(
    target: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    merged = _build_update_payload(target, action)
    if not merged:
        return {}

    patch: dict[str, Any] = {}

    if "title" in action:
        patch["summary"] = str(
            merged["calendar_event_title"]
        )[:250]

    changes_time = any(
        key in action
        for key in (
            "event_date",
            "start_at",
            "end_at",
            "all_day",
        )
    )

    if changes_time:
        event_body = build_google_event_body(
            title=str(merged["calendar_event_title"]),
            event_date=str(merged["calendar_event_date"]),
            description="",
            start_at=merged.get("calendar_event_start_at"),
            end_at=merged.get("calendar_event_end_at"),
            location=None,
        )
        patch["start"] = event_body["start"]
        patch["end"] = event_body["end"]

    if "location" in action:
        location = _clean_optional_text(action.get("location"))
        if location:
            patch["location"] = location[:180]

    return patch


async def _patch_direct_google_calendar_event(
    *,
    access_token: str,
    google_event_id: str,
    calendar_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    import httpx
    from urllib.parse import quote

    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{quote(calendar_id or 'primary', safe='')}/events/"
        f"{quote(google_event_id, safe='')}"
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.patch(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=patch,
        )

    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def calendar_action_succeeded(
    result: dict[str, Any] | None,
) -> bool:
    if not isinstance(result, dict):
        return False

    return bool(
        result.get("success")
        or result.get("updated")
        or result.get("deleted")
    )


_RECEIPT_TZ = ZoneInfo("Asia/Jakarta")
_RECEIPT_MONTHS_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


def _receipt_opener(message: str, address_term: str | None = None) -> str:
    term = _receipt_text(address_term)
    if term:
        return f"{message}, {term}."
    return f"{message}."


def _receipt_addressed_sentence(
    sentence: str,
    address_term: str | None = None,
) -> str:
    term = _receipt_text(address_term)
    if not term:
        return sentence

    clean_sentence = sentence.strip()
    if not clean_sentence:
        return term

    return f"{term}, {clean_sentence[:1].lower()}{clean_sentence[1:]}"


def render_google_calendar_create_user_receipt(
    result: dict[str, Any] | None,
    address_term: str | None = None,
) -> str | None:
    """Render deterministic receipt for direct Google Calendar sync/create."""
    if not isinstance(result, dict):
        return None

    if not result.get("attempted"):
        return None

    reason = str(result.get("reason") or "").strip()

    if result.get("google_event_id") and reason == "calendar_event_already_synced":
        return (
            _receipt_opener("Jadwal itu sudah tersync ke Google Calendar", address_term)
            + _receipt_details_block(result)
        )

    if result.get("google_event_id"):
        return (
            _receipt_opener("Sudah aku sync ke Google Calendar", address_term)
            + _receipt_details_block(result)
        )

    if reason == "no_confident_draft":
        return (
            _receipt_opener("Aku belum cukup yakin detail jadwalnya", address_term)
            + " Coba sebutkan nama acara, tanggal, jam, dan lokasinya."
        )

    if reason in {"missing_required_fields", "google_missing_event_id"}:
        return (
            _receipt_opener("Belum berhasil aku sync ke Google Calendar", address_term)
            + " Coba ulangi dengan detail acara, tanggal, dan jamnya ya."
        )

    return (
        _receipt_opener("Belum berhasil aku sync ke Google Calendar", address_term)
        + " Coba ulangi sebentar lagi."
    )


def render_calendar_action_user_receipt(
    result: dict[str, Any] | None,
    address_term: str | None = None,
) -> str | None:
    """Render deterministic user-facing receipt for Calendar actions.

    This is intentionally not LLM-written. It only uses facts returned by the
    backend Calendar action layer.
    """
    if not isinstance(result, dict):
        return None

    if not result.get("attempted"):
        return None

    reason = str(result.get("reason") or "").strip()
    action = str(result.get("action") or "").strip()
    success = calendar_action_succeeded(result)
    title = _receipt_text(result.get("title")) or "jadwal itu"

    if reason == "recurring_scope_required":
        return _receipt_addressed_sentence(
            "Ini jadwal berulang. Mau aku ubah untuk hari ini saja, "
            "hari ini dan seterusnya, atau seluruh rangkaian?",
            address_term,
        )

    if reason == "recurring_scope_not_supported_yet":
        return _receipt_addressed_sentence(
            "Untuk sekarang aku baru bisa ubah satu occurrence dengan aman. "
            "Mau aku ubah untuk hari ini saja?",
            address_term,
        )

    if reason == "calendar_conflict_requires_confirmation":
        conflict_text = _receipt_conflict_text(result)
        detail_lines = _receipt_detail_lines(result)
        details = (
            "\n" + "\n".join(detail_lines)
            if detail_lines
            else ""
        )

        return (
            _receipt_opener("Belum aku update", address_term)
            + f" {conflict_text}{details}\n\n"
            "Mau tetap lanjut atau pilih jam lain?"
        )

    if reason == "no_pending_recurring_action":
        return (
            _receipt_opener("Aku belum bisa lanjutkan", address_term)
            + " Request jadwal berulang sebelumnya sudah tidak ditemukan "
            "atau sudah kedaluwarsa. Coba ulangi request lengkapnya ya."
        )

    if success and bool(result.get("deleted")):
        details = _receipt_details_block(result)
        return (
            _receipt_opener("Sudah aku hapus", address_term)
            + details
        )

    if success and bool(result.get("updated")):
        details = _receipt_details_block(result)
        return (
            _receipt_opener("Sudah aku update", address_term)
            + details
        )

    if success:
        details = _receipt_details_block(result)
        return (
            _receipt_opener("Sudah beres", address_term)
            + details
        )

    verb = "hapus" if action == "delete" else "update"
    failure = _receipt_failure_text(reason, verb, address_term)
    return failure


def _receipt_failure_text(reason: str, verb: str, address_term: str | None = None) -> str:
    if reason in {"google_read_failed", "google_access_failed"}:
        return (
            _receipt_opener(f"Belum berhasil aku {verb}", address_term)
            + " Akses Google Calendar belum bisa dibaca. "
            "Coba reconnect Google Calendar dulu."
        )

    if reason in {"no_calendar_records", "target_not_found"}:
        return (
            _receipt_opener(f"Belum berhasil aku {verb}", address_term)
            + " Aku belum menemukan jadwal yang dimaksud."
        )

    if reason == "no_confident_action":
        return (
            _receipt_opener(f"Aku belum cukup yakin jadwal mana yang harus aku {verb}", address_term)
            + " Coba sebutkan nama jadwal dan jamnya lebih lengkap."
        )

    if reason == "google_patch_failed":
        return (
            _receipt_opener("Belum berhasil aku update di Google Calendar", address_term)
            + " Coba ulangi sebentar lagi."
        )

    if reason == "google_delete_failed":
        return (
            _receipt_opener("Belum berhasil aku hapus dari Google Calendar", address_term)
            + " Coba ulangi sebentar lagi."
        )

    return (
        _receipt_opener(f"Belum berhasil aku {verb}", address_term)
        + " Coba ulangi sebentar lagi."
    )


def _receipt_details_block(result: dict[str, Any]) -> str:
    lines = _receipt_detail_lines(result)
    if not lines:
        return ""

    return "\n\n" + "\n".join(lines)


def _receipt_detail_lines(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    title = _receipt_text(result.get("title"))
    if title:
        lines.append(f"Acara: {title}")

    date_text = _format_receipt_date(result.get("date"))
    if date_text:
        lines.append(f"Tanggal: {date_text}")

    time_text = _format_receipt_time_range(
        result.get("start_at"),
        result.get("end_at"),
    )
    if time_text:
        lines.append(f"Waktu: {time_text}")

    location = _receipt_text(result.get("location"))
    if location:
        lines.append(f"Lokasi: {location}")

    return lines


def _receipt_conflict_text(result: dict[str, Any]) -> str:
    conflict_analysis = result.get("conflict_analysis")
    if not isinstance(conflict_analysis, dict):
        return "Jadwal ini bentrok dengan jadwal lain."

    conflicts = [
        conflict
        for conflict in conflict_analysis.get("conflicts", [])
        if isinstance(conflict, dict)
    ]
    if not conflicts:
        return "Jadwal ini bentrok dengan jadwal lain."

    conflict = conflicts[0]
    title = _receipt_text(conflict.get("title")) or "jadwal lain"
    time_text = _format_receipt_time_range(
        conflict.get("start_at"),
        conflict.get("end_at"),
    )

    if time_text:
        return f"Jadwal ini bentrok dengan {title} pukul {time_text}."

    return f"Jadwal ini bentrok dengan {title}."


def _receipt_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _format_receipt_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    try:
        parsed = datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except Exception:
        try:
            parsed = datetime.fromisoformat(f"{raw}T00:00:00")
        except Exception:
            return raw

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_RECEIPT_TZ)

    month = _RECEIPT_MONTHS_ID.get(parsed.month, str(parsed.month))
    return f"{parsed.day} {month} {parsed.year}"


def _format_receipt_time_range(
    start_value: Any,
    end_value: Any,
) -> str:
    start_text = _format_receipt_time(start_value)
    end_text = _format_receipt_time(end_value)

    if start_text and end_text:
        return f"{start_text}–{end_text}"

    return start_text or end_text


def _format_receipt_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    try:
        parsed = datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except Exception:
        return raw

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_RECEIPT_TZ)

    return f"{parsed.hour:02d}.{parsed.minute:02d}"


def render_calendar_action_result_context(
    result: dict[str, Any] | None,
) -> str:
    result = result if isinstance(result, dict) else {}
    success = calendar_action_succeeded(result)
    action = str(result.get("action") or "").strip()

    if not action:
        if result.get("deleted"):
            action = "delete"
        elif result.get("updated"):
            action = "update"
        else:
            action = "unknown"

    source = str(result.get("source") or "local").strip()
    reason = str(result.get("reason") or "").strip() or "none"
    conflict_analysis = result.get("conflict_analysis")
    if not isinstance(conflict_analysis, dict):
        conflict_analysis = {}
    conflicts = [
        conflict
        for conflict in conflict_analysis.get("conflicts", [])
        if isinstance(conflict, dict)
    ]

    lines = [
        "Calendar action result — authoritative:",
        "- Grounded receipt rule: use only the Calendar action facts listed in this result.",
        "- Do not use conversation history, chronology, memories, or other Calendar items to add schedule commentary.",
        "- Do not mention or infer another meeting, agenda, reminder, free period, sequence, overlap, travel time, or schedule compatibility.",
        "- Do not say 'pas banget', 'setelah meeting', 'sebelum meeting', 'bentrok', 'masih sempat', or equivalent unless an explicit conflict-analysis result is included.",
        (
            "- Conflict-analysis result is included in this Calendar action receipt."
            if conflicts
            else "- No conflict-analysis result is included in this Calendar action receipt."
        ),
        f"- success: {'true' if success else 'false'}",
        f"- action: {action}",
        f"- source: {source}",
        f"- reason: {reason}",
    ]

    for key in (
        "title",
        "date",
        "start_at",
        "end_at",
        "location",
    ):
        value = result.get(key)
        if value:
            lines.append(f"- {key}: {value}")

    if conflicts:
        lines.append("- conflict_analysis: has_conflicts=true")
        for conflict in conflicts[:3]:
            title = str(conflict.get("title") or "Untitled event")
            start_at = str(conflict.get("start_at") or "")
            end_at = str(conflict.get("end_at") or "")
            source_value = str(conflict.get("source") or "calendar")
            lines.append(
                "- conflict: "
                f"{title} | start_at={start_at} | "
                f"end_at={end_at} | source={source_value}"
            )

    if reason == "recurring_scope_required":
        pending_saved = bool(result.get("pending_action_saved"))

        lines.extend(
            [
                "- This is a recurring Google Calendar event.",
                "- No update or deletion was performed.",
                "- Ask the user to choose: this occurrence only, this and following, or the entire series.",
            ]
        )

        if pending_saved:
            lines.append(
                "- The pending request was saved. A short reply such as 'hari ini saja' can continue it safely."
            )
        else:
            lines.append(
                "- The pending request could not be saved. Ask the user to repeat the full request together with the desired scope."
            )
    elif reason == "recurring_scope_not_supported_yet":
        lines.extend(
            [
                "- No update or deletion was performed.",
                "- Only changing or deleting this occurrence is currently supported safely.",
                "- Ask the user whether to apply it to this occurrence only.",
            ]
        )
    elif reason == "calendar_conflict_requires_confirmation":
        lines.extend(
            [
                "- No update or deletion was performed.",
                "- The proposed Calendar action conflicts with the listed Calendar item(s).",
                "- Tell the user the requested time is currently conflicting.",
                "- Ask whether to keep going anyway or choose another time.",
                "- Do not claim the Calendar was updated.",
                "- If the user wants to override the conflict, ask them to repeat the full request with 'tetap lanjut'.",
            ]
        )
    elif reason == "no_pending_recurring_action":
        lines.extend(
            [
                "- No Calendar action was performed.",
                "- The previous recurring request is missing or expired.",
                "- Ask the user to repeat the full update or delete request and include the desired recurring scope.",
            ]
        )
    elif reason == "pending_recurring_action_load_failed":
        lines.extend(
            [
                "- No Calendar action was performed.",
                "- The saved recurring request could not be loaded.",
                "- Ask the user to repeat the full request.",
            ]
        )
    elif success:
        lines.extend(
            [
                "- The Calendar action has completed successfully.",
                "- Keep the user-facing reply brief: one confirmation sentence plus the changed Calendar details.",
                "- Do not append observations, recommendations, encouragement, jokes, or commentary about the user's wider schedule.",
                "- You may clearly say it was updated or deleted.",
                "- Do not describe it as merely pending or still being processed.",
            ]
        )
    else:
        lines.extend(
            [
                "- The Calendar action did not complete successfully.",
                "- Do not claim it was updated or deleted.",
                "- State briefly that the change could not be completed.",
            ]
        )

    return "\n".join(lines)


async def _apply_synced_google_calendar_action(
    *,
    user_id: str,
    target: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    google_event_id = str(target.get("google_calendar_event_id") or "").strip()
    google_calendar_id = str(target.get("google_calendar_id") or "primary").strip() or "primary"

    if not google_event_id:
        return {
            "attempted": True,
            "updated": False,
            "deleted": False,
            "reason": "synced_google_missing_event_id",
            "target_memory_id": target.get("id"),
            "action": action.get("action"),
        }

    access_token = await get_active_google_calendar_access_token(user_id=user_id)

    if action["action"] == "delete":
        try:
            await _delete_google_calendar_event(
                access_token=access_token,
                google_event_id=google_event_id,
                calendar_id=google_calendar_id,
            )
        except Exception as exc:
            log.warning("calendar_draft_actions: google delete failed: %s", exc)
            return {
                "attempted": True,
                "updated": False,
                "deleted": False,
                "reason": "google_delete_failed",
                "target_memory_id": target.get("id"),
            }

        payload = _build_archive_payload()
        payload["archived_by"] = "chat_google_calendar_delete"
        payload["calendar_event_status"] = "deleted_google"
        payload["calendar_sync_error"] = None

        try:
            result = safe_execute(
                lambda sb: sb.table("memories")
                .update(payload)
                .eq("id", str(target["id"]))
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            log.warning("calendar_draft_actions: local archive after google delete failed: %s", exc)
            return {
                "attempted": True,
                "updated": False,
                "deleted": False,
                "reason": "local_archive_after_google_delete_failed",
                "target_memory_id": target.get("id"),
            }

        return {
            "attempted": True,
            "updated": False,
            "deleted": True,
            "target_memory_id": target.get("id"),
            "title": _title_from_target(target),
            "data": result.data,
        }

    if action["action"] == "update":
        payload = _build_update_payload(target, action)
        if not payload:
            return {"attempted": True, "updated": False, "deleted": False, "reason": "empty_update"}

        try:
            patched_event = await _patch_google_calendar_event(
                access_token=access_token,
                google_event_id=google_event_id,
                calendar_id=google_calendar_id,
                title=str(payload.get("calendar_event_title") or _title_from_target(target)),
                event_date=str(payload.get("calendar_event_date") or target.get("due_date")),
                description=_google_event_description_from_payload(payload),
                start_at=payload.get("calendar_event_start_at"),
                end_at=payload.get("calendar_event_end_at"),
                location=payload.get("calendar_event_location"),
            )
        except Exception as exc:
            log.warning("calendar_draft_actions: google patch failed: %s", exc)
            return {
                "attempted": True,
                "updated": False,
                "deleted": False,
                "reason": "google_patch_failed",
                "target_memory_id": target.get("id"),
            }

        payload["google_calendar_event_link"] = patched_event.get("htmlLink") or target.get("google_calendar_event_link")
        payload["calendar_event_status"] = "synced_google"
        payload["calendar_sync_error"] = None
        payload["calendar_synced_at"] = _now_iso()

        try:
            result = safe_execute(
                lambda sb: sb.table("memories")
                .update(payload)
                .eq("id", str(target["id"]))
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            log.warning("calendar_draft_actions: local update after google patch failed: %s", exc)
            return {
                "attempted": True,
                "updated": False,
                "deleted": False,
                "reason": "local_update_after_google_patch_failed",
                "target_memory_id": target.get("id"),
            }

        return {
            "attempted": True,
            "updated": True,
            "deleted": False,
            "target_memory_id": target.get("id"),
            "title": payload.get("calendar_event_title") or _title_from_target(target),
            "date": payload.get("calendar_event_date") or target.get("due_date"),
            "data": result.data,
        }

    return {
        "attempted": True,
        "updated": False,
        "deleted": False,
        "reason": "unsupported_synced_google_action",
    }


async def _create_google_calendar_event(
    *,
    access_token: str,
    title: str,
    event_date: str,
    description: str,
    start_at: str | None = None,
    end_at: str | None = None,
    location: str | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    import httpx
    from urllib.parse import quote

    event = build_google_event_body(
        title=title,
        event_date=event_date,
        description=description,
        start_at=start_at,
        end_at=end_at,
        location=location,
    )

    url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(calendar_id, safe='')}/events"

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=event,
        )

    response.raise_for_status()
    return response.json()


async def _patch_google_calendar_event(
    *,
    access_token: str,
    google_event_id: str,
    calendar_id: str,
    title: str,
    event_date: str,
    description: str,
    start_at: str | None = None,
    end_at: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    import httpx
    from urllib.parse import quote

    event = build_google_event_body(
        title=title,
        event_date=event_date,
        description=description,
        start_at=start_at,
        end_at=end_at,
        location=location,
    )

    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{quote(calendar_id or 'primary', safe='')}/events/{quote(google_event_id, safe='')}"
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.patch(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=event,
        )

    response.raise_for_status()
    return response.json()


async def _delete_google_calendar_event(
    *,
    access_token: str,
    google_event_id: str,
    calendar_id: str,
) -> None:
    import httpx
    from urllib.parse import quote

    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{quote(calendar_id or 'primary', safe='')}/events/{quote(google_event_id, safe='')}"
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.delete(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code in {200, 204, 404, 410}:
        return

    response.raise_for_status()


def _google_event_description_from_draft(draft: dict[str, Any]) -> str:
    parts = ["Created by Aliyya from chat."]
    if draft.get("location"):
        parts.append(f"Location: {draft['location']}")
    if draft.get("reason"):
        parts.append(f"Reason: {draft['reason']}")
    return "\n".join(parts)


def _google_event_description_from_payload(payload: dict[str, Any]) -> str:
    parts = ["Updated by Aliyya from chat."]
    if payload.get("structured_value"):
        parts.append(str(payload["structured_value"]))
    return "\n".join(parts)


async def _load_recent_calendar_records(*, user_id: str) -> list[dict[str, Any]]:
    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id, content, structured_value, due_date, updated_at, created_at, "
                "calendar_candidate, calendar_event_status, calendar_event_title, calendar_event_location, "
                "calendar_event_date, calendar_event_start_at, calendar_event_end_at, "
                "calendar_event_all_day, google_calendar_event_id, google_calendar_event_link, "
                "archived, superseded"
            )
            .eq("user_id", user_id)
            .eq("archived", False)
            .eq("superseded", False)
            .or_("calendar_candidate.eq.true,calendar_event_status.in.(confirmed_local,synced_google)")
            .order("updated_at", desc=True)
            .limit(12)
            .execute()
        )
    except Exception as exc:
        log.warning("calendar_draft_actions: load records failed: %s", exc)
        return []

    return list(result.data or [])


async def _load_calendar_action_records(
    *,
    user_id: str,
    client_context: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool]:
    local_records = await _load_recent_calendar_records(
        user_id=user_id
    )

    direct_records: list[dict[str, Any]] = []
    google_read_failed = False

    try:
        start_dt, end_dt, time_zone = _calendar_action_search_window(
            client_context
        )
        google_events = await list_google_calendar_events_for_action(
            user_id=user_id,
            start_dt=start_dt,
            end_dt=end_dt,
            time_zone=time_zone,
        )

        linked_google_ids = {
            str(row.get("google_calendar_event_id") or "").strip()
            for row in local_records
            if row.get("google_calendar_event_id")
        }

        direct_records = [
            _direct_google_event_to_action_record(event)
            for event in google_events
            if str(event.get("id") or "").strip()
            and str(event.get("id") or "").strip()
            not in linked_google_ids
        ]
    except Exception as exc:
        google_read_failed = True
        log.warning(
            "calendar_draft_actions: direct google read failed error_type=%s",
            type(exc).__name__,
        )

    local_records = (
        _drop_local_records_duplicated_by_direct_google(
            local_records,
            direct_records,
        )
    )

    return [*direct_records, *local_records], google_read_failed


def _canonical_action_datetime(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    try:
        parsed = datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except Exception:
        return raw

    if parsed.tzinfo is None:
        return parsed.isoformat()

    return parsed.astimezone(timezone.utc).isoformat()


def _calendar_action_fingerprint(
    row: dict[str, Any],
) -> tuple[str, str, bool, str, str] | None:
    title = _norm(_title_from_target(row))
    event_date = str(
        row.get("calendar_event_date")
        or row.get("due_date")
        or ""
    ).strip()

    if not title or not event_date:
        return None

    all_day = bool(row.get("calendar_event_all_day"))

    return (
        title,
        event_date,
        all_day,
        (
            ""
            if all_day
            else _canonical_action_datetime(
                row.get("calendar_event_start_at")
            )
        ),
        (
            ""
            if all_day
            else _canonical_action_datetime(
                row.get("calendar_event_end_at")
            )
        ),
    )


def _drop_local_records_duplicated_by_direct_google(
    local_records: list[dict[str, Any]],
    direct_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    direct_fingerprints = {
        fingerprint
        for row in direct_records
        for fingerprint in [
            _calendar_action_fingerprint(row)
        ]
        if fingerprint is not None
    }

    filtered: list[dict[str, Any]] = []

    for row in local_records:
        # A linked memory row represents a deliberately synced event and must
        # remain available to its existing Google + local update path.
        if row.get("google_calendar_event_id"):
            filtered.append(row)
            continue

        fingerprint = _calendar_action_fingerprint(row)

        # An unlinked local row that exactly mirrors a direct Google event
        # must not compete with Google during action target resolution.
        if (
            fingerprint is not None
            and fingerprint in direct_fingerprints
        ):
            continue

        filtered.append(row)

    return filtered


def _calendar_action_search_window(
    client_context: Any,
) -> tuple[datetime, datetime, str | None]:
    context = _client_context_dict(client_context)
    base = datetime.now(timezone.utc)

    raw_local_time = str(
        context.get("local_time") or ""
    ).strip()

    if raw_local_time:
        try:
            parsed = datetime.fromisoformat(
                raw_local_time.replace("Z", "+00:00")
            )
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            base = parsed.astimezone(timezone.utc)
        except Exception:
            pass

    time_zone_name = str(
        context.get("timezone") or ""
    ).strip() or None

    return (
        base - timedelta(days=7),
        base + timedelta(days=24),
        time_zone_name,
    )


def _direct_google_event_to_action_record(
    event: dict[str, Any],
) -> dict[str, Any]:
    google_event_id = str(event.get("id") or "").strip()

    return {
        "id": f"google:{google_event_id}",
        "_record_source": "google",
        "content": event.get("title"),
        "structured_value": event.get("title"),
        "due_date": event.get("event_date"),
        "calendar_candidate": False,
        "calendar_event_status": "direct_google",
        "calendar_event_title": event.get("title"),
        "calendar_event_date": event.get("event_date"),
        "calendar_event_start_at": event.get("start_at"),
        "calendar_event_end_at": event.get("end_at"),
        "calendar_event_all_day": bool(event.get("all_day")),
        "calendar_event_location": event.get("location"),
        "google_calendar_event_id": google_event_id,
        "google_calendar_event_link": event.get("html_link"),
        "google_calendar_id": "primary",
        "google_recurring_event_id": event.get(
            "recurring_event_id"
        ),
        "google_original_start_at": event.get(
            "original_start_at"
        ),
        "calendar_event_is_recurring": bool(
            event.get("is_recurring")
            or event.get("recurring_event_id")
        ),
        "archived": False,
        "superseded": False,
    }


async def _extract_action(
    *,
    user_message: str,
    recent_messages: list[dict[str, Any]] | None,
    client_context: dict[str, Any] | None,
    calendar_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    payload = {
        "client_context": _client_context_dict(client_context),
        "recent_messages": _compact_recent_messages(recent_messages),
        "current_user_message": user_message,
        "calendar_records": [_compact_record(row) for row in calendar_records],
    }

    prompt = "Extract a local Calendar draft action from this payload.\n\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )

    response = await get_claude().messages.create(
        model=MODEL_NAME,
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_object(_response_text(response))


def _normalise_action(raw: dict[str, Any] | None, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw.get("is_calendar_action"):
        return None

    action_name = str(raw.get("action") or "").strip().lower()
    if action_name not in {"update", "delete"}:
        return None

    target_id = str(raw.get("target_memory_id") or "").strip()
    valid_ids = {str(row.get("id")) for row in records}
    if target_id not in valid_ids:
        return None

    confidence = _normalise_confidence(raw.get("confidence"))
    if confidence < 0.68:
        return None

    action: dict[str, Any] = {
        "action": action_name,
        "target_memory_id": target_id,
        "confidence": confidence,
    }

    title = _clean_optional_text(raw.get("title"))
    if title:
        action["title"] = title[:160]

    event_date = _valid_iso_date(raw.get("event_date"))
    if event_date:
        action["event_date"] = event_date

    start_at = _valid_iso_datetime(raw.get("start_at"))
    if start_at:
        action["start_at"] = start_at

    end_at = _valid_iso_datetime(raw.get("end_at"))
    if end_at:
        action["end_at"] = end_at

    if "all_day" in raw and isinstance(raw.get("all_day"), bool):
        action["all_day"] = bool(raw.get("all_day"))

    location = _clean_optional_text(raw.get("location"))
    if location:
        action["location"] = location[:180]

    recurring_scope = str(
        raw.get("recurring_scope") or ""
    ).strip()

    if recurring_scope in {
        "this_instance",
        "this_and_following",
        "entire_series",
    }:
        action["recurring_scope"] = recurring_scope

    return action


def _build_update_payload(target: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    title = action.get("title") or target.get("calendar_event_title") or _title_from_target(target)
    event_date = action.get("event_date") or target.get("calendar_event_date") or target.get("due_date")
    start_at = action.get("start_at") if "start_at" in action else target.get("calendar_event_start_at")
    end_at = action.get("end_at") if "end_at" in action else target.get("calendar_event_end_at")
    all_day = action.get("all_day") if "all_day" in action else target.get("calendar_event_all_day")

    if start_at and not end_at:
        end_at = _default_end_at(start_at)

    if start_at:
        all_day = False

    if not title or not event_date:
        return {}

    # Location semantics (this phase): only a non-empty new location replaces
    # the existing one. Omitted, null, empty, or whitespace-only values all
    # preserve the stored location. Explicit clearing is intentionally not
    # supported yet, so local state can never go empty while Google still
    # holds the previous location.
    new_location = action.get("location")
    new_location = str(new_location).strip()[:180] if new_location else None
    existing_location = target.get("calendar_event_location")
    existing_location = str(existing_location).strip()[:180] if existing_location else None
    location = new_location or existing_location
    structured_value = _structured_value(
        title=str(title),
        event_date=str(event_date),
        start_at=str(start_at) if start_at else None,
        end_at=str(end_at) if end_at else None,
        location=location,
    )
    content = f"User has a scheduled event: {title} on {event_date}"
    if location:
        content += f" at {location}"

    now = _now_iso()

    return {
        "content": content,
        "structured_value": structured_value,
        "due_date": str(event_date),
        "calendar_candidate": False,
        "calendar_event_status": str(target.get("calendar_event_status") or "confirmed_local"),
        "calendar_event_title": str(title),
        "calendar_event_date": str(event_date),
        "calendar_event_start_at": str(start_at) if start_at else None,
        "calendar_event_end_at": str(end_at) if end_at else None,
        "calendar_event_all_day": bool(all_day) if all_day is not None else not bool(start_at),
        "calendar_event_location": location,
        "updated_at": now,
    }


def _build_archive_payload() -> dict[str, Any]:
    now = _now_iso()
    return {
        "archived": True,
        "archived_by": "chat_calendar_action",
        "archived_at": now,
        "calendar_candidate": False,
        "updated_at": now,
    }


def _compact_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("calendar_event_title") or _title_from_target(row),
        "location": row.get("calendar_event_location"),
        "content": row.get("content"),
        "structured_value": row.get("structured_value"),
        "event_date": row.get("calendar_event_date") or row.get("due_date"),
        "start_at": row.get("calendar_event_start_at"),
        "end_at": row.get("calendar_event_end_at"),
        "all_day": row.get("calendar_event_all_day"),
        "status": row.get("calendar_event_status"),
        "source": row.get("_record_source") or (
            "synced_google"
            if _is_synced_google(row)
            else "local"
        ),
        "google_event_id": row.get("google_calendar_event_id"),
        "is_recurring": bool(
            row.get("calendar_event_is_recurring")
            or row.get("google_recurring_event_id")
        ),
        "recurring_event_id": row.get(
            "google_recurring_event_id"
        ),
        "original_start_at": row.get(
            "google_original_start_at"
        ),
        "is_synced_google": _is_synced_google(row),
        "updated_at": row.get("updated_at"),
    }


def _compact_recent_messages(recent_messages: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []

    for message in (recent_messages or [])[-10:]:
        role = str(message.get("role") or "").strip()
        content = message.get("content")

        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            text = "\n".join(parts)
        else:
            text = str(content or "")

        text = re.sub(r"\s+", " ", text).strip()
        if role and text:
            compact.append({"role": role, "content": text[:700]})

    return compact


def _client_context_dict(client_context: Any) -> dict[str, Any]:
    if hasattr(client_context, "model_dump"):
        client_context = client_context.model_dump(exclude_none=True)
    elif hasattr(client_context, "dict"):
        client_context = client_context.dict(exclude_none=True)

    if not isinstance(client_context, dict):
        return {}

    return {
        key: value
        for key, value in client_context.items()
        if key in {"local_time", "timezone", "timezone_offset_minutes", "locale"}
    }


def _title_from_target(row: dict[str, Any]) -> str:
    raw = str(row.get("calendar_event_title") or row.get("structured_value") or row.get("content") or "Untitled event")
    raw = re.sub(r"\s*\|\s*due_date=.*$", "", raw)
    raw = re.sub(r"^User has a scheduled event:\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s+on\s+\d{4}-\d{2}-\d{2}.*$", "", raw)
    return re.sub(r"\s+", " ", raw).strip()[:160] or "Untitled event"


def _structured_value(
    *,
    title: str,
    event_date: str,
    start_at: str | None = None,
    end_at: str | None = None,
    location: str | None = None,
) -> str:
    parts = [title, f"due_date={event_date}"]
    if start_at:
        parts.append(f"start_at={start_at}")
    if end_at:
        parts.append(f"end_at={end_at}")
    if location:
        parts.append(f"location={location}")
    return " | ".join(parts)


def _response_text(response: Any) -> str:
    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(str(text))
    return "\n".join(chunks).strip() if chunks else str(response or "").strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-")
    return value or None


def _valid_iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        datetime.fromisoformat(value + "T00:00:00")
    except ValueError:
        return None
    return value


def _valid_iso_datetime(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _default_end_at(start_at: str) -> str:
    start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    return (start + timedelta(hours=1)).isoformat()


def _normalise_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, confidence))


def _is_synced_google(row: dict[str, Any]) -> bool:
    return bool(row.get("google_calendar_event_id") or row.get("calendar_event_status") == "synced_google")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold()).strip()
