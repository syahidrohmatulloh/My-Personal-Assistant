"""Memory supersession by structured key.

Some memory fields are single-value by nature. If a newer memory says the
user's sleep pattern changed, the old sleep pattern should not remain active
and conflict with it.

This module archives older active memories for single-value structured fields
when a new memory with the same structured_field is inserted.

It is intentionally generic:
- no user-specific hardcoding
- no assistant-name hardcoding
- no private fact hardcoding
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any

from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)


MULTI_VALUE_EXACT_FIELDS = {
    "food_preference",
    "visual_memory_food_photo",
    "visual_memory_personal_photo",
    "visual_memory_personal_travel_photo",
    "visual_memory_place_photo",
    "scheduled_event",
    "upcoming_meeting",
    "active_project",
    "active_goal_reference",
    "manual_memory",
}

MULTI_VALUE_PREFIXES = (
    "visual_memory_",
    "calendar_",
)

SINGLE_VALUE_EXACT_FIELDS = {
    "assistant_name",
    "preferred_address",
    "disallowed_address",
    "preferred_name",
    "name",
    "timezone",
    "location",
    "home_city",
    "work_role",
    "employer",
    "language",
    "sleep_pattern",
    "height",
    "weight",
    "age",
}


@dataclass(frozen=True)
class SupersessionDecision:
    should_supersede: bool
    reason: str


def is_single_value_field(field: str | None) -> bool:
    key = _norm_key(field)
    if not key:
        return False

    if key in MULTI_VALUE_EXACT_FIELDS:
        return False

    if any(key.startswith(prefix) for prefix in MULTI_VALUE_PREFIXES):
        return False

    if key in SINGLE_VALUE_EXACT_FIELDS:
        return True

    # Conservative generic rules. These tend to represent current profile/state,
    # not a list of memories.
    if key.endswith("_pattern"):
        return True
    if key.endswith("_name"):
        return True

    return False


def decide_supersession(old_value: str | None, new_value: str | None) -> SupersessionDecision:
    old_norm = _norm_value(old_value)
    new_norm = _norm_value(new_value)

    if not old_norm or not new_norm:
        return SupersessionDecision(False, "missing_value")

    if old_norm == new_norm:
        return SupersessionDecision(False, "same_value")

    # If one value is just a tiny formatting variation of the other, avoid
    # archiving to prevent churn.
    similarity = _similarity(old_norm, new_norm)
    if similarity >= 0.92:
        return SupersessionDecision(False, "near_duplicate")

    return SupersessionDecision(True, "single_value_field_replaced")


def apply_memory_supersession(*, user_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Archive existing conflicting memories before inserting new rows.

    Best effort: failures are logged and rows are returned unchanged so chat
    never fails because of memory maintenance.
    """
    if not rows:
        return rows

    candidates = [row for row in rows if _row_is_candidate(row)]
    if not candidates:
        return rows

    try:
        supabase = get_supabase()
        for row in candidates:
            _supersede_existing_for_row(supabase=supabase, user_id=user_id, row=row)
    except Exception as exc:  # noqa: BLE001
        log.warning("memory supersession failed: %s", exc)

    return _dedupe_incoming_single_value_rows(rows)


def _supersede_existing_for_row(*, supabase: Any, user_id: str, row: dict[str, Any]) -> None:
    field = _norm_key(row.get("structured_field"))
    new_value = str(row.get("structured_value") or "").strip()

    if not field or not new_value:
        return

    result = (
        supabase.table("memories")
        .select("id, structured_value, content")
        .eq("user_id", user_id)
        .eq("archived", False)
        .eq("structured_field", field)
        .limit(25)
        .execute()
    )

    existing = result.data or []
    to_archive: list[str] = []

    for old in existing:
        decision = decide_supersession(old.get("structured_value"), new_value)
        if decision.should_supersede:
            memory_id = str(old.get("id") or "").strip()
            if memory_id:
                to_archive.append(memory_id)

    if not to_archive:
        return

    now = datetime.now(timezone.utc).isoformat()
    (
        supabase.table("memories")
        .update(
            {
                "archived": True,
                "superseded": True,
                "archived_by": f"memory_supersession:{field}",
                "archived_at": now,
                "updated_at": now,
            }
        )
        .in_("id", to_archive)
        .execute()
    )

    log.info(
        "memory supersession: archived %d old memories for user=%s field=%s",
        len(to_archive),
        user_id[:8],
        field,
    )


def _dedupe_incoming_single_value_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """If the same extraction batch has duplicate single-value fields, keep last."""
    last_index_by_field: dict[str, int] = {}

    for index, row in enumerate(rows):
        field = _norm_key(row.get("structured_field"))
        if field and is_single_value_field(field):
            last_index_by_field[field] = index

    deduped: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        field = _norm_key(row.get("structured_field"))
        if field and is_single_value_field(field) and last_index_by_field.get(field) != index:
            continue
        deduped.append(row)

    return deduped


def _row_is_candidate(row: dict[str, Any]) -> bool:
    field = _norm_key(row.get("structured_field"))
    value = str(row.get("structured_value") or "").strip()
    return bool(field and value and is_single_value_field(field))


def _norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().casefold()).strip("_")


def _norm_value(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return text.strip(" ,.;:-")


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0

    left_tokens = {_singularize(t) for t in re.findall(r"[a-z0-9]+", left)}
    right_tokens = {_singularize(t) for t in re.findall(r"[a-z0-9]+", right)}

    if not left_tokens or not right_tokens:
        return 0.0

    overlap = len(left_tokens.intersection(right_tokens))
    return overlap / max(1, max(len(left_tokens), len(right_tokens)))


def _singularize(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token
