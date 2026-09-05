"""Memory supersession by structured key.

Some memory fields are single-value by nature. If a newer memory says the
user's sleep pattern changed, the old sleep pattern should not remain active
and conflict with it.

This module plans supersession before insertion and finalizes older active
single-value memories only after the replacement row has been inserted.

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


DIRECT_USER_PRIORITIES = frozenset(
    {
        "explicit_user_statement",
        "user_answer_in_context",
        "user_correction",
    }
)


def _row_is_hidden(row: dict[str, Any]) -> bool:
    status_value = str(
        row.get("status") or ""
    ).strip().lower()

    return bool(
        row.get("archived")
        or row.get("superseded")
        or row.get("deleted_at")
        or status_value in {
            "archived",
            "superseded",
            "deleted",
        }
    )


def _row_is_authoritative(row: dict[str, Any]) -> bool:
    priority = str(
        row.get("source_priority") or ""
    ).strip().lower()

    return bool(
        priority in DIRECT_USER_PRIORITIES
        or row.get("last_user_confirmed_at")
    )


def _hidden_equivalent_exists(
    *,
    supabase: Any,
    user_id: str,
    row: dict[str, Any],
) -> bool:
    field = _norm_key(
        row.get("structured_field")
    )
    value = _norm_value(
        row.get("structured_value")
    )

    if not field or not value:
        return False

    result = (
        supabase.table("memories")
        .select(
            "id, structured_value, archived, superseded, "
            "status, deleted_at"
        )
        .eq("user_id", user_id)
        .eq("structured_field", field)
        .limit(50)
        .execute()
    )

    for existing in result.data or []:
        if (
            _row_is_hidden(existing)
            and _norm_value(
                existing.get("structured_value")
            )
            == value
        ):
            return True

    return False


def apply_memory_supersession(
    *,
    user_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Plan incoming rows without mutating existing truth.

    This phase may deduplicate the incoming batch and suppress inferred rows
    that would recreate a hidden memory. Existing database rows are NEVER
    mutated here.
    """
    if not rows:
        return rows

    deduped = _dedupe_incoming_single_value_rows(
        rows
    )

    weak_rows = [
        row
        for row in deduped
        if not _row_is_authoritative(row)
    ]

    if not weak_rows:
        return deduped

    try:
        supabase = get_supabase()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "memory resurrection guard unavailable: %s",
            exc,
        )
        # Fail closed for non-authoritative automatic rows. Direct user
        # evidence is allowed to proceed.
        return [
            row
            for row in deduped
            if _row_is_authoritative(row)
        ]

    guarded: list[dict[str, Any]] = []

    for row in deduped:
        if _row_is_authoritative(row):
            guarded.append(row)
            continue

        try:
            if _hidden_equivalent_exists(
                supabase=supabase,
                user_id=user_id,
                row=row,
            ):
                log.info(
                    "memory resurrection suppressed user=%s field=%s",
                    user_id[:8],
                    _norm_key(
                        row.get("structured_field")
                    ),
                )
                continue
        except Exception as exc:  # noqa: BLE001
            # Lifecycle state could not be established. Do not let machine
            # inference recreate unknown hidden state.
            log.warning(
                "memory resurrection check failed; "
                "suppressing inferred row: %s",
                exc,
            )
            continue

        guarded.append(row)

    return guarded


def finalize_memory_supersession(
    *,
    user_id: str,
    inserted_rows: list[dict[str, Any]],
) -> None:
    """Supersede replaced active truth only after replacement insert succeeds."""

    if not inserted_rows:
        return

    candidates = [
        row
        for row in inserted_rows
        if _row_is_candidate(row)
        and row.get("id")
    ]

    if not candidates:
        return

    try:
        supabase = get_supabase()

        for row in candidates:
            _finalize_existing_for_row(
                supabase=supabase,
                user_id=user_id,
                row=row,
            )
    except Exception as exc:  # noqa: BLE001
        # Safe failure mode: two active values are preferable to deleting the
        # old truth before its replacement exists.
        log.warning(
            "memory supersession finalize failed: %s",
            exc,
        )


def _finalize_existing_for_row(
    *,
    supabase: Any,
    user_id: str,
    row: dict[str, Any],
) -> None:
    field = _norm_key(
        row.get("structured_field")
    )
    new_value = str(
        row.get("structured_value") or ""
    ).strip()
    new_id = str(
        row.get("id") or ""
    ).strip()

    if not field or not new_value or not new_id:
        return

    result = (
        supabase.table("memories")
        .select(
            "id, structured_value, source_priority, "
            "last_user_confirmed_at, archived, superseded, "
            "status, deleted_at"
        )
        .eq("user_id", user_id)
        .eq("structured_field", field)
        .limit(50)
        .execute()
    )

    to_supersede: list[str] = []

    for old in result.data or []:
        old_id = str(
            old.get("id") or ""
        ).strip()

        if (
            not old_id
            or old_id == new_id
            or _row_is_hidden(old)
        ):
            continue

        # Weak automatic inference must never overwrite direct or explicitly
        # confirmed existing truth.
        if (
            _row_is_authoritative(old)
            and not _row_is_authoritative(row)
        ):
            continue

        decision = decide_supersession(
            old.get("structured_value"),
            new_value,
        )

        if decision.should_supersede:
            to_supersede.append(old_id)

    if not to_supersede:
        return

    now = datetime.now(
        timezone.utc
    ).isoformat()

    (
        supabase.table("memories")
        .update(
            {
                "superseded": True,
                "superseded_by": new_id,
                "superseded_at": now,
                "status": "superseded",
                "updated_at": now,
            }
        )
        .in_("id", to_supersede)
        .eq("user_id", user_id)
        .execute()
    )

    log.info(
        "memory supersession: finalized %d old memories "
        "for user=%s field=%s",
        len(to_supersede),
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
