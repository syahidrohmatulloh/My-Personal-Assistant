"""Durable pending state for recurring Google Calendar actions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

from app.services.supabase_client import safe_execute


PENDING_ACTION_TTL_MINUTES = 30

VALID_RECURRING_SCOPES = {
    "this_instance",
    "this_and_following",
    "entire_series",
}

_SCOPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "this_and_following",
        (
            "ini dan seterusnya",
            "yang ini dan seterusnya",
            "mulai ini ke depan",
            "mulai sekarang ke depan",
            "this and following",
        ),
    ),
    (
        "entire_series",
        (
            "seluruh rangkaian",
            "semua rangkaian",
            "semua jadwal",
            "semuanya",
            "entire series",
        ),
    ),
    (
        "this_instance",
        (
            "hari ini saja",
            "yang ini saja",
            "ini saja",
            "kejadian ini saja",
            "jadwal ini saja",
            "occurrence ini saja",
            "this instance",
        ),
    ),
)

_ACTION_MARKERS = (
    "ubah",
    "ganti",
    "edit",
    "update",
    "reschedule",
    "jadwal ulang",
    "hapus",
    "delete",
    "remove",
    "batalin",
    "batalkan",
    "cancel",
)


def parse_recurring_scope(text: str | None) -> str | None:
    normalized = _normalize(text)

    if not normalized:
        return None

    for scope, phrases in _SCOPE_PATTERNS:
        if any(phrase in normalized for phrase in phrases):
            return scope

    return None


def is_recurring_scope_only_reply(text: str | None) -> bool:
    normalized = _normalize(text)

    if not normalized or not parse_recurring_scope(normalized):
        return False

    return not any(
        marker in normalized
        for marker in _ACTION_MARKERS
    )


def create_pending_recurring_action(
    *,
    user_id: str,
    conversation_id: str,
    target: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_at = (
        now + timedelta(minutes=PENDING_ACTION_TTL_MINUTES)
    ).isoformat()

    # Only one unresolved recurring Calendar action may exist in one chat.
    safe_execute(
        lambda sb: sb.table("calendar_pending_actions")
        .update(
            {
                "status": "cancelled",
                "updated_at": now_iso,
            }
        )
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .eq("status", "pending")
        .execute()
    )

    payload = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "action_type": str(action.get("action") or ""),
        "target_source": "google",
        "google_event_id": str(
            target.get("google_calendar_event_id") or ""
        ),
        "google_calendar_id": str(
            target.get("google_calendar_id") or "primary"
        ),
        "google_recurring_event_id": (
            target.get("google_recurring_event_id")
        ),
        "target_snapshot": _json_safe_dict(target),
        "requested_action": _json_safe_dict(action),
        "status": "pending",
        "expires_at": expires_at,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    result = safe_execute(
        lambda sb: sb.table("calendar_pending_actions")
        .insert(payload)
        .execute()
    )

    rows = list(result.data or [])

    if not rows:
        raise RuntimeError(
            "Pending recurring Calendar action was not stored"
        )

    return rows[0]


def load_pending_recurring_action(
    *,
    user_id: str,
    conversation_id: str,
) -> dict[str, Any] | None:
    result = safe_execute(
        lambda sb: sb.table("calendar_pending_actions")
        .select(
            "id,user_id,conversation_id,action_type,"
            "target_source,google_event_id,google_calendar_id,"
            "google_recurring_event_id,target_snapshot,"
            "requested_action,status,expires_at,"
            "created_at,updated_at"
        )
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    rows = list(result.data or [])
    if not rows:
        return None

    row = rows[0]

    if _is_expired(row.get("expires_at")):
        _mark_status(
            pending_action_id=str(row["id"]),
            user_id=user_id,
            status_value="expired",
        )
        return None

    return row


def mark_pending_recurring_action_completed(
    *,
    pending_action_id: str,
    user_id: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()

    safe_execute(
        lambda sb: sb.table("calendar_pending_actions")
        .update(
            {
                "status": "completed",
                "completed_at": now,
                "updated_at": now,
            }
        )
        .eq("id", pending_action_id)
        .eq("user_id", user_id)
        .eq("status", "pending")
        .execute()
    )


def _mark_status(
    *,
    pending_action_id: str,
    user_id: str,
    status_value: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()

    safe_execute(
        lambda sb: sb.table("calendar_pending_actions")
        .update(
            {
                "status": status_value,
                "updated_at": now,
            }
        )
        .eq("id", pending_action_id)
        .eq("user_id", user_id)
        .eq("status", "pending")
        .execute()
    )


def _is_expired(value: Any) -> bool:
    if not value:
        return True

    try:
        expires_at = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except Exception:
        return True

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    return expires_at <= datetime.now(timezone.utc)


def _json_safe_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    result: dict[str, Any] = {}

    for key, item in value.items():
        if item is None or isinstance(
            item,
            (str, int, float, bool),
        ):
            result[str(key)] = item
        elif isinstance(item, list):
            result[str(key)] = [
                child
                for child in item
                if child is None
                or isinstance(
                    child,
                    (str, int, float, bool),
                )
            ]

    return result


def _normalize(value: str | None) -> str:
    normalized = re.sub(
        r"\s+",
        " ",
        str(value or "").casefold(),
    ).strip()

    # Indonesian colloquial continuation replies commonly use
    # "aja" instead of "saja", for example "hari ini aja".
    return re.sub(r"\baja\b", "saja", normalized)
