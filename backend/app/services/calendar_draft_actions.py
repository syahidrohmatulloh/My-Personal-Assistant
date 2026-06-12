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
    has_recurring_scope = any(
        term in normalized
        for term in _RECURRING_SCOPE_TERMS
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
        location=_clean_optional_text(draft.get("location")),
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
        "calendar_event_location": _clean_optional_text(draft.get("location")),
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
            "data": result.data,
        }

    return {"attempted": True, "updated": False, "deleted": False, "reason": "unsupported_action"}



async def _apply_direct_google_action_with_pending_scope(
    *,
    user_id: str,
    conversation_id: str,
    target: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    result = await _apply_direct_google_calendar_action(
        user_id=user_id,
        target=target,
        action=action,
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

    result = await _apply_direct_google_calendar_action(
        user_id=user_id,
        target=target,
        action=resumed_action,
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

        merged = _build_update_payload(target, action)

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

    lines = [
        "Calendar action result — authoritative:",
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
