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

from app.services.claude import get_claude
from app.services.embeddings import embed_document
from app.services.supabase_client import safe_execute
from app.services import calendar_intent
from app.routers.calendar_oauth import get_active_google_calendar_access_token

log = logging.getLogger(__name__)

MODEL_NAME = "claude-haiku-4-5"

_UPDATE_TERMS = (
    "ubah",
    "ganti",
    "edit",
    "update",
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

SYSTEM_PROMPT = """You perform local Calendar draft actions for a personal assistant app.

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
  "confidence": number,
  "reason": string
}

Rules:
- You are acting on local Calendar drafts shown in Memories → Calendar.
- Pick exactly one target from the provided calendar_records.
- action="update" when the user asks to change time/date/title/location, or asks to make an event more detailed/specific/jelas/detil.
- action="delete" when the user asks to remove, cancel, hapus, batalin, delete, or archive an agenda/event.
- Return action="none" and confidence below 0.6 if the target is ambiguous.
- Preserve any field not changed by the user by returning null for that field. If the user asks for a more detailed event title/description, improve title/location using recent context and the target record.
- If changing start_at but end_at is not specified, infer a 1-hour duration unless the original record has a duration.
- Use browser local time context and recent chat context for relative times like "jam 3", "besok", "nanti", "yang tadi".
- Never claim to update or delete Google Calendar. This system only updates local Calendar drafts.
"""


def is_calendar_draft_action_request(text: str | None) -> bool:
    normalized = _norm(text)
    if not normalized:
        return False

    has_update = any(term in normalized for term in _UPDATE_TERMS)
    has_delete = any(term in normalized for term in _DELETE_TERMS)
    has_soft_update = any(term in normalized for term in _SOFT_UPDATE_TERMS)
    if not (has_update or has_delete or has_soft_update):
        return False

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

    access_token = await get_active_google_calendar_access_token(user_id=user_id)

    created = await _create_google_calendar_event(
        access_token=access_token,
        title=title,
        event_date=event_date,
        description=_google_event_description_from_draft(draft),
        start_at=str(start_at) if start_at else None,
        end_at=str(end_at) if end_at else None,
    )

    google_event_id = created.get("id")
    google_event_link = created.get("htmlLink")

    if not google_event_id:
        return {"attempted": True, "created": False, "reason": "google_missing_event_id"}

    structured_value = _structured_value(
        title=title,
        event_date=event_date,
        start_at=str(start_at) if start_at else None,
        end_at=str(end_at) if end_at else None,
        location=draft.get("location"),
    )
    content = f"User has a scheduled event: {title} on {event_date}"
    if draft.get("location"):
        content += f" at {draft['location']}"

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
        "calendar_event_start_at": str(start_at) if start_at else None,
        "calendar_event_end_at": str(end_at) if end_at else None,
        "calendar_event_all_day": all_day or not bool(start_at),
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

    result = safe_execute(lambda sb: sb.table("memories").insert(row).execute())

    return {
        "attempted": True,
        "created": True,
        "google_event_id": google_event_id,
        "google_event_link": google_event_link,
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

    records = await _load_recent_calendar_records(user_id=user_id)
    if not records:
        return {"attempted": True, "updated": False, "deleted": False, "reason": "no_calendar_records"}

    raw_action = await _extract_action(
        user_message=user_message,
        recent_messages=recent_messages,
        client_context=client_context,
        calendar_records=records,
    )
    action = _normalise_action(raw_action, records)
    if not action:
        return {"attempted": True, "updated": False, "deleted": False, "reason": "no_confident_action"}

    target = next((row for row in records if str(row.get("id")) == action["target_memory_id"]), None)
    if not target:
        return {"attempted": True, "updated": False, "deleted": False, "reason": "target_not_found"}

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
            "data": result.data,
        }

    return {"attempted": True, "updated": False, "deleted": False, "reason": "unsupported_action"}



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
    calendar_id: str = "primary",
) -> dict[str, Any]:
    import httpx
    from urllib.parse import quote

    event: dict[str, Any] = {
        "summary": title,
        "description": description,
    }

    if start_at and end_at:
        event["start"] = {"dateTime": start_at}
        event["end"] = {"dateTime": end_at}
    else:
        event["start"] = {"date": event_date}
        event["end"] = {"date": event_date}

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
) -> dict[str, Any]:
    import httpx
    from urllib.parse import quote

    event: dict[str, Any] = {
        "summary": title,
        "description": description,
    }

    if start_at and end_at:
        event["start"] = {"dateTime": start_at}
        event["end"] = {"dateTime": end_at}
    else:
        event["start"] = {"date": event_date}
        event["end"] = {"date": event_date}

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
                "calendar_candidate, calendar_event_status, calendar_event_title, "
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

    location = action.get("location")
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
        "content": row.get("content"),
        "structured_value": row.get("structured_value"),
        "event_date": row.get("calendar_event_date") or row.get("due_date"),
        "start_at": row.get("calendar_event_start_at"),
        "end_at": row.get("calendar_event_end_at"),
        "all_day": row.get("calendar_event_all_day"),
        "status": row.get("calendar_event_status"),
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
