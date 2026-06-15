"""Execution layer for LLM-routed Calendar confirmations.

The LLM decides intent. This module validates ownership, confidence, allowed
actions, and performs the actual side effects.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from app.routers.calendar_oauth import get_active_google_calendar_access_token
from app.services import calendar_decision_router
from app.services.supabase_client import safe_execute
from app.services.google_calendar_payload import build_google_event_body
from app.services.memory_user_facing_safety import human_calendar_structured_value

log = logging.getLogger(__name__)


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


def render_calendar_confirmation_user_receipt(
    result: dict[str, Any] | None,
    address_term: str | None = None,
) -> str | None:
    """Render deterministic user-facing receipt for Calendar confirmations."""
    if not isinstance(result, dict):
        return None

    if not result.get("attempted"):
        return None

    action = str(result.get("action") or "").strip()
    executed = bool(result.get("executed"))

    if executed and action == "accept_local":
        return (
            _receipt_opener("Sudah aku masukin ke Calendar", address_term)
            + _receipt_details_block(result)
        )

    if executed and action == "accept_google":
        return (
            _receipt_opener("Sudah aku sync ke Google Calendar", address_term)
            + _receipt_details_block(result)
        )

    if executed and action == "dismiss":
        return _receipt_opener("Oke, aku abaikan jadwal itu", address_term)

    if executed and action == "update_pending_details":
        return (
            _receipt_opener("Oke, aku update detailnya", address_term)
            + _receipt_details_block(result)
            + "\n\nMau aku masukin ke Calendar?"
        )

    reason = str(result.get("reason") or "").strip()
    if action == "clarify" and reason == "multiple_pending_suggestions":
        return (
            _receipt_opener("Aku menemukan beberapa agenda pending", address_term)
            + " Yang mana yang kamu maksud?"
        )
    if reason in {"no_pending_suggestions", "low_confidence_or_no_action"}:
        return None

    if action in {"accept_local", "accept_google"}:
        return (
            _receipt_opener("Belum berhasil aku masukin ke Calendar", address_term)
            + " Coba ulangi dengan detail acara, tanggal, dan jamnya ya."
        )

    return None


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


def _receipt_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _format_receipt_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        try:
            parsed = datetime.fromisoformat(f"{raw}T00:00:00")
        except Exception:
            return raw

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_RECEIPT_TZ)

    month = _RECEIPT_MONTHS_ID.get(parsed.month, str(parsed.month))
    return f"{parsed.day} {month} {parsed.year}"


def _format_receipt_time_range(start_value: Any, end_value: Any) -> str:
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
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return raw

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(_RECEIPT_TZ)

    return f"{parsed.hour:02d}.{parsed.minute:02d}"


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
    is_reminder = "reminder" in str(row.get("content") or "").lower()
    item_label = "reminder" if is_reminder else "calendar item"

    return (
        "Calendar/reminder pending suggestion context — internal:\n"
        f"- There is a hidden pending {item_label} awaiting user confirmation.\n"
        "- If the user seems to be asking you to remember/remind/schedule something, ask for confirmation naturally.\n"
        "- For reminders, prefer wording like: 'Mau aku ingetin?' or 'Do you want me to remind you?'\n"
        "- If the user confirms, you may say you will add it to Calendar/reminders.\n"
        "- If the user asks for Google Calendar, you may say you will sync it to Google Calendar.\n"
        "- If the user declines, you may say you will ignore/remove the suggestion.\n"
        "- Do not use internal terms like candidate or event draft.\n"
        f"- Pending suggestion id: {row.get('id')}\n"
        f"- Item: {title}\n"
        f"- Date: {date}\n"
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
                    "calendar_candidate, calendar_event_status, calendar_event_title, calendar_event_location, "
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

    detail_update = await _apply_pending_detail_update_if_possible(
        user_id=user_id,
        suggestions=suggestions,
        user_message=user_message,
    )
    if detail_update:
        return detail_update

    deterministic_decision = _deterministic_confirmation_decision(
        user_message=user_message,
        suggestions=suggestions,
    )
    if deterministic_decision:
        decision = deterministic_decision
    else:
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

    if decision.action == "update_pending_details":
        updates = _extract_pending_detail_updates(user_message, target)
        if updates:
            return await _update_pending_suggestion_details(
                user_id=user_id,
                row=target,
                updates=updates,
                decision=decision,
            )

        return {
            "attempted": True,
            "executed": False,
            "action": "update_pending_details",
            "reason": "no_detail_updates_detected",
            "confidence": decision.confidence,
        }

    return {
        "attempted": True,
        "executed": False,
        "action": decision.action,
        "reason": "unsupported_action",
    }


def _deterministic_confirmation_decision(
    *,
    user_message: str,
    suggestions: list[dict[str, Any]],
) -> calendar_decision_router.CalendarDecision | None:
    normalized = _normalize_reply(user_message)
    if not normalized:
        return None

    action: str | None = None
    if normalized in {
        "iya",
        "ya",
        "yes",
        "y",
        "oke",
        "ok",
        "sip",
        "siap",
        "boleh",
        "lanjut",
        "masukin",
        "masukkan",
        "masukin ke calendar",
        "masukin ke kalender",
        "masukkan ke calendar",
        "masukkan ke kalender",
    }:
        action = "accept_local"
    elif normalized in {
        "sync",
        "sync google",
        "sync ke google",
        "sync ke google calendar",
        "sync ke google kalender",
        "google calendar",
        "google kalender",
    } or ("google" in normalized and ("sync" in normalized or "calendar" in normalized or "kalender" in normalized)):
        action = "accept_google"
    elif normalized in {
        "batal",
        "cancel",
        "skip",
        "abaikan",
        "gajadi",
        "ga jadi",
        "nggak jadi",
        "tidak jadi",
        "jangan",
        "jangan dulu",
    }:
        action = "dismiss"

    if not action:
        return None

    if len(suggestions) != 1:
        return calendar_decision_router.CalendarDecision(
            action="clarify",
            target_memory_id=None,
            confidence=1.0,
            reason="multiple_pending_suggestions",
        )

    target_id = str(suggestions[0].get("id") or "").strip() or None
    return calendar_decision_router.CalendarDecision(
        action=action,
        target_memory_id=target_id,
        confidence=1.0,
        reason="deterministic_short_reply",
    )


async def _apply_pending_detail_update_if_possible(
    *,
    user_id: str,
    suggestions: list[dict[str, Any]],
    user_message: str,
) -> dict[str, Any] | None:
    if not _looks_like_pending_detail_update(user_message):
        return None

    if len(suggestions) != 1:
        return {
            "attempted": True,
            "executed": False,
            "action": "clarify",
            "reason": "multiple_pending_suggestions",
        }

    row = suggestions[0]
    updates = _extract_pending_detail_updates(user_message, row)
    if not updates:
        return None

    decision = calendar_decision_router.CalendarDecision(
        action="update_pending_details",
        target_memory_id=str(row.get("id") or ""),
        confidence=1.0,
        reason="deterministic_slot_fill",
    )
    return await _update_pending_suggestion_details(
        user_id=user_id,
        row=row,
        updates=updates,
        decision=decision,
    )


def _looks_like_pending_detail_update(user_message: str | None) -> bool:
    normalized = _normalize_reply(user_message)
    if not normalized:
        return False

    if _deterministic_confirmation_decision(
        user_message=normalized,
        suggestions=[{"id": "placeholder"}],
    ):
        return False

    explicit_markers = (
        "lokasinya",
        "lokasi nya",
        "tempatnya",
        "tempat nya",
        "venue",
        "bioskopnya",
        "bioskop nya",
        "kliniknya",
        "klinik nya",
        "jamnya",
        "jam nya",
        "waktunya",
        "waktu nya",
        "tanggalnya",
        "tanggal nya",
    )
    if any(marker in normalized for marker in explicit_markers):
        return True

    # Short proper slot-fill replies, e.g. "CGV Agora" after a pending agenda.
    words = normalized.split()
    return 1 <= len(words) <= 6 and not any(
        token in normalized
        for token in (
            "aku mau",
            "saya mau",
            "jadwal",
            "agenda",
            "meeting",
            "rapat",
            "besok",
            "tanggal",
            "tgl",
        )
    )


def _extract_pending_detail_updates(
    user_message: str | None,
    row: dict[str, Any],
) -> dict[str, Any]:
    text = str(user_message or "").strip()
    normalized = _normalize_reply(text)
    updates: dict[str, Any] = {}

    location = _extract_pending_location_update(text, row)
    if location:
        updates["calendar_event_location"] = location

    time_updates = _extract_pending_time_update(text, row)
    updates.update(time_updates)

    return updates


def _extract_pending_location_update(
    text: str,
    row: dict[str, Any],
) -> str | None:
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return None

    patterns = [
        r"(?i)\b(?:lokasinya|lokasi nya|tempatnya|tempat nya|venue(?:nya)?|bioskopnya|bioskop nya|kliniknya|klinik nya)\s+(?:di|ke|at)?\s*(.+)$",
        r"(?i)^di\s+(.+)$",
        r"(?i)^ke\s+(.+)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return _clean_pending_location(match.group(1))

    current_location = _clean_pending_location(row.get("calendar_event_location"))
    if _pending_location_can_be_replaced(current_location):
        # Short replies like "CGV Agora" should update a pending location.
        words = raw.split()
        if 1 <= len(words) <= 6:
            return _clean_pending_location(raw)

    return None


def _clean_pending_location(value: Any) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    text = re.sub(r"(?i)^(di|ke|at)\s+", "", text).strip()
    text = text.strip(" .,:;!?'\"")
    if not text:
        return None

    lowered = text.casefold()
    if lowered in {
        "iya",
        "ya",
        "oke",
        "ok",
        "batal",
        "gajadi",
        "ga jadi",
        "nggak jadi",
        "tidak jadi",
        "sana",
        "situ",
        "tempat itu",
    }:
        return None

    if len(text) > 180:
        return None

    return text


def _pending_location_can_be_replaced(current_location: str | None) -> bool:
    if not current_location:
        return True

    lowered = current_location.casefold()
    return lowered in {
        "bioskop",
        "klinik",
        "tempat",
        "venue",
        "lokasi",
        "-",
        "—",
    }


def _extract_pending_time_update(
    text: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}

    event_date = _event_date_from_row(row)
    if not event_date:
        return {}

    parsed = _parse_time_range_for_pending_update(raw)
    if not parsed:
        return {}

    start_time, end_time = parsed
    tz = ZoneInfo("Asia/Jakarta")
    base_date = date.fromisoformat(event_date)
    start_dt = datetime.combine(base_date, start_time, tzinfo=tz)
    end_dt = datetime.combine(base_date, end_time, tzinfo=tz)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return {
        "calendar_event_start_at": start_dt.isoformat(),
        "calendar_event_end_at": end_dt.isoformat(),
        "calendar_event_all_day": False,
    }


def _parse_time_range_for_pending_update(text: str) -> tuple[time, time] | None:
    normalized = text.casefold()

    match = re.search(
        r"(?:jam\s*)?(\d{1,2})(?:[.:](\d{2}))?\s*(?:-|–|—|sampai|sampe|sd|s/d)\s*(?:jam\s*)?(\d{1,2})(?:[.:](\d{2}))?",
        normalized,
    )
    if not match:
        return None

    start_hour = int(match.group(1))
    start_minute = int(match.group(2) or 0)
    end_hour = int(match.group(3))
    end_minute = int(match.group(4) or 0)

    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
        return None
    if not (0 <= start_minute <= 59 and 0 <= end_minute <= 59):
        return None

    return time(start_hour, start_minute), time(end_hour, end_minute)


async def _update_pending_suggestion_details(
    *,
    user_id: str,
    row: dict[str, Any],
    updates: dict[str, Any],
    decision: calendar_decision_router.CalendarDecision,
) -> dict[str, Any]:
    title = _event_title_from_row(row)
    event_date = _event_date_from_row(row)
    if not event_date:
        return {
            "attempted": True,
            "executed": False,
            "action": "update_pending_details",
            "reason": "missing_event_date",
            "confidence": decision.confidence,
        }

    start_at = updates.get("calendar_event_start_at", row.get("calendar_event_start_at"))
    end_at = updates.get("calendar_event_end_at", row.get("calendar_event_end_at"))
    all_day = bool(updates.get("calendar_event_all_day", row.get("calendar_event_all_day")))
    location = updates.get("calendar_event_location", row.get("calendar_event_location"))

    structured_value = human_calendar_structured_value(
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
    payload = {
        **updates,
        "content": content,
        "structured_value": structured_value,
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
        log.warning("calendar_confirmation_actions: pending detail update failed: %s", exc)
        return {
            "attempted": True,
            "executed": False,
            "action": "update_pending_details",
            "reason": "detail_update_failed",
            "confidence": decision.confidence,
        }

    return {
        "attempted": True,
        "executed": True,
        "action": "update_pending_details",
        "memory_id": row.get("id"),
        "title": title,
        "date": event_date,
        "start_at": start_at,
        "end_at": end_at,
        "location": location,
        "confidence": decision.confidence,
        "data": result.data,
    }


def _normalize_reply(value: str | None) -> str:
    return " ".join(str(value or "").casefold().split()).strip()


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
        "calendar_event_location": row.get("calendar_event_location"),
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
        "date": event_date,
        "start_at": row.get("calendar_event_start_at"),
        "end_at": row.get("calendar_event_end_at"),
        "location": row.get("calendar_event_location"),
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
        location=row.get("calendar_event_location"),
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
        "calendar_event_location": row.get("calendar_event_location"),
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
        "date": event_date,
        "start_at": row.get("calendar_event_start_at"),
        "end_at": row.get("calendar_event_end_at"),
        "location": row.get("calendar_event_location"),
        "google_event_id": google_event_id,
        "google_event_link": created.get("htmlLink"),
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
