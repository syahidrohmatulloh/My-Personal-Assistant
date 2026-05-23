"""Execution layer for LLM-routed Calendar confirmations.

The LLM decides intent. This module validates ownership, confidence, allowed
actions, and performs the actual side effects.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any

from app.routers.calendar_oauth import get_active_google_calendar_access_token
from app.services import calendar_decision_router
from app.services.supabase_client import safe_execute

log = logging.getLogger(__name__)


async def render_pending_calendar_confirmation_context(
    *,
    user_id: str,
    conversation_id: str | None = None,
) -> str | None:
    suggestions = await load_pending_calendar_suggestions(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=1,
    )
    if not suggestions and conversation_id:
        suggestions = await load_pending_calendar_suggestions(user_id=user_id, limit=1)

    if not suggestions:
        return None

    row = suggestions[0]
    title = _event_title_from_row(row)
    date = _event_date_from_row(row) or "unknown date"
    start_at = row.get("calendar_event_start_at")
    end_at = row.get("calendar_event_end_at")
    time_text = _format_time_range(start_at, end_at)

    return (
        "Calendar pending suggestion context — internal:\\n"
        "- There is a hidden pending Calendar suggestion awaiting user confirmation.\\n"
        "- If the user confirms, you may say you will add it to Calendar.\\n"
        "- If the user asks for Google Calendar, you may say you will sync it to Google Calendar.\\n"
        "- If the user declines, you may say you will ignore/remove the suggestion.\\n"
        "- Do not use internal terms like candidate or event draft.\\n"
        f"- Pending suggestion id: {row.get('id')}\\n"
        f"- Event: {title}\\n"
        f"- Date: {date}\\n"
        f"- Time: {time_text}"
    )


async def load_pending_calendar_suggestions(
    *,
    user_id: str,
    conversation_id: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    try:
        def run_query(sb):
            query = (
                sb.table("memories")
                .select(
                    "id, content, structured_value, due_date, source_conversation_id, "
                    "calendar_candidate, calendar_event_status, calendar_event_title, "
                    "calendar_event_date, calendar_event_start_at, calendar_event_end_at, "
                    "calendar_event_all_day, archived, superseded, updated_at, created_at"
                )
                .eq("user_id", user_id)
                .eq("calendar_candidate", True)
                .eq("archived", False)
                .eq("superseded", False)
            )
            if conversation_id:
                query = query.eq("source_conversation_id", conversation_id)
            return query.order("updated_at", desc=True).limit(limit).execute()

        result = safe_execute(run_query)
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_confirmation_actions: load pending failed: %s", exc)
        return []

    return list(result.data or [])


async def apply_calendar_confirmation_decision(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    client_context: dict[str, Any] | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    suggestions = await load_pending_calendar_suggestions(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=3,
    )
    if not suggestions:
        suggestions = await load_pending_calendar_suggestions(user_id=user_id, limit=3)

    if not suggestions:
        return {"attempted": False, "executed": False, "reason": "no_pending_suggestions"}

    decision = await calendar_decision_router.classify_calendar_confirmation(
        user_message=user_message,
        pending_suggestions=suggestions,
        recent_messages=recent_messages,
        client_context=client_context,
    )

    if not calendar_decision_router.should_execute_decision(decision):
        return {
            "attempted": True,
            "executed": False,
            "action": decision.action,
            "confidence": decision.confidence,
            "reason": decision.reason or "low_confidence_or_no_action",
        }

    target = next((row for row in suggestions if str(row.get("id")) == str(decision.target_memory_id)), None)
    if not target:
        return {
            "attempted": True,
            "executed": False,
            "action": decision.action,
            "reason": "target_not_found_or_not_owned",
        }

    if decision.action == "accept_local":
        return await _accept_pending_suggestion_local(user_id=user_id, row=target, decision=decision)

    if decision.action == "accept_google":
        return await _accept_pending_suggestion_to_google(user_id=user_id, row=target, decision=decision)

    if decision.action == "dismiss":
        return await _dismiss_pending_suggestion(user_id=user_id, row=target, decision=decision)

    return {
        "attempted": True,
        "executed": False,
        "action": decision.action,
        "reason": "unsupported_action",
    }


async def _accept_pending_suggestion_local(
    *,
    user_id: str,
    row: dict[str, Any],
    decision: calendar_decision_router.CalendarDecision,
) -> dict[str, Any]:
    title = _event_title_from_row(row)
    event_date = _event_date_from_row(row)
    if not event_date:
        return {"attempted": True, "executed": False, "reason": "missing_event_date"}

    now = _now_iso()
    payload = {
        "calendar_candidate": False,
        "calendar_event_status": "confirmed_local",
        "calendar_event_title": title,
        "calendar_event_date": event_date,
        "calendar_event_start_at": row.get("calendar_event_start_at"),
        "calendar_event_end_at": row.get("calendar_event_end_at"),
        "calendar_event_all_day": bool(row.get("calendar_event_all_day")),
        "updated_at": now,
    }

    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .update(payload)
            .eq("id", str(row["id"]))
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_confirmation_actions: local accept failed: %s", exc)
        return {"attempted": True, "executed": False, "reason": "local_accept_failed"}

    return {
        "attempted": True,
        "executed": True,
        "action": "accept_local",
        "memory_id": row.get("id"),
        "title": title,
        "confidence": decision.confidence,
        "data": result.data,
    }


async def _accept_pending_suggestion_to_google(
    *,
    user_id: str,
    row: dict[str, Any],
    decision: calendar_decision_router.CalendarDecision,
) -> dict[str, Any]:
    title = _event_title_from_row(row)
    event_date = _event_date_from_row(row)
    if not event_date:
        return {"attempted": True, "executed": False, "reason": "missing_event_date"}

    access_token = await get_active_google_calendar_access_token(user_id=user_id)
    created = await _create_google_calendar_event(
        access_token=access_token,
        title=title,
        event_date=event_date,
        description="Created by Aliyya from chat confirmation.",
        start_at=row.get("calendar_event_start_at"),
        end_at=row.get("calendar_event_end_at"),
    )

    google_event_id = created.get("id")
    if not google_event_id:
        return {"attempted": True, "executed": False, "reason": "google_missing_event_id"}

    now = _now_iso()
    payload = {
        "calendar_candidate": False,
        "calendar_event_status": "synced_google",
        "calendar_event_title": title,
        "calendar_event_date": event_date,
        "calendar_event_start_at": row.get("calendar_event_start_at"),
        "calendar_event_end_at": row.get("calendar_event_end_at"),
        "calendar_event_all_day": bool(row.get("calendar_event_all_day")),
        "google_calendar_event_id": google_event_id,
        "google_calendar_event_link": created.get("htmlLink"),
        "google_calendar_id": "primary",
        "calendar_synced_at": now,
        "calendar_sync_error": None,
        "updated_at": now,
    }

    result = safe_execute(
        lambda sb: sb.table("memories")
        .update(payload)
        .eq("id", str(row["id"]))
        .eq("user_id", user_id)
        .execute()
    )

    return {
        "attempted": True,
        "executed": True,
        "action": "accept_google",
        "memory_id": row.get("id"),
        "title": title,
        "google_event_id": google_event_id,
        "confidence": decision.confidence,
        "data": result.data,
    }


async def _dismiss_pending_suggestion(
    *,
    user_id: str,
    row: dict[str, Any],
    decision: calendar_decision_router.CalendarDecision,
) -> dict[str, Any]:
    now = _now_iso()
    payload = {
        "calendar_candidate": False,
        "archived": True,
        "archived_by": "llm_calendar_confirmation_dismissed",
        "archived_at": now,
        "updated_at": now,
    }

    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .update(payload)
            .eq("id", str(row["id"]))
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_confirmation_actions: dismiss failed: %s", exc)
        return {"attempted": True, "executed": False, "reason": "dismiss_failed"}

    return {
        "attempted": True,
        "executed": True,
        "action": "dismiss",
        "memory_id": row.get("id"),
        "confidence": decision.confidence,
        "data": result.data,
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


def _event_title_from_row(row: dict[str, Any]) -> str:
    raw = str(row.get("calendar_event_title") or row.get("structured_value") or row.get("content") or "Untitled event")
    raw = re.sub(r"\s*\|\s*due_date=.*$", "", raw)
    raw = re.sub(r"^User has a scheduled event:\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s+on\s+\d{4}-\d{2}-\d{2}.*$", "", raw)
    return re.sub(r"\s+", " ", raw).strip()[:160] or "Untitled event"


def _event_date_from_row(row: dict[str, Any]) -> str | None:
    value = str(row.get("calendar_event_date") or row.get("due_date") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return None
    return value


def _format_time_range(start_at: Any, end_at: Any) -> str:
    start = str(start_at or "").strip()
    end = str(end_at or "").strip()
    if start and end:
        return f"{start} – {end}"
    if start:
        return start
    return "all day or unknown time"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
