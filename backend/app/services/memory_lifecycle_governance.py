"""Memory lifecycle governance policy.

MR7 is intentionally conservative:
- never auto-delete;
- never auto-archive;
- only classify lifecycle state and expose safe aggregate diagnostics;
- retrieval still excludes hidden memories through the existing active-memory path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


DEFAULT_STALE_AFTER_DAYS = 365
LOW_CONFIDENCE_THRESHOLD = 0.55

_HIDDEN_STATUSES = {"archived", "superseded", "deleted"}


@dataclass(frozen=True)
class MemoryLifecycleAssessment:
    state: str
    hidden: bool
    stale: bool
    needs_confirmation: bool
    confirmed: bool
    age_days: int | None = None
    reason: str = "active"


@dataclass(frozen=True)
class MemoryLifecycleAggregate:
    total: int
    active: int
    hidden: int
    stale: int
    needs_confirmation: int
    confirmed: int

    def safe_diagnostics(self) -> str:
        return (
            "memory_lifecycle:"
            f" total={self.total}"
            f" active={self.active}"
            f" hidden={self.hidden}"
            f" stale={self.stale}"
            f" needs_confirmation={self.needs_confirmation}"
            f" confirmed={self.confirmed}"
        )


def _as_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_days(row: dict[str, Any], *, now: datetime) -> int | None:
    anchor = (
        _parse_dt(row.get("last_confirmed_at"))
        or _parse_dt(row.get("updated_at"))
        or _parse_dt(row.get("created_at"))
    )
    if not anchor:
        return None
    return max(0, (now - anchor.astimezone(timezone.utc)).days)


def lifecycle_state(row: dict[str, Any]) -> str:
    status = _as_text(row.get("status")).casefold()

    if row.get("deleted_at") or status == "deleted":
        return "deleted"
    if _as_bool(row.get("archived")) or status == "archived":
        return "archived"
    if _as_bool(row.get("superseded")) or status == "superseded":
        return "superseded"
    return "active"


def is_hidden_memory(row: dict[str, Any]) -> bool:
    return lifecycle_state(row) in _HIDDEN_STATUSES


def is_retrievable_memory(row: dict[str, Any]) -> bool:
    return not is_hidden_memory(row)


def assess_memory_lifecycle(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> MemoryLifecycleAssessment:
    now = now or datetime.now(timezone.utc)
    state = lifecycle_state(row)
    hidden = state in _HIDDEN_STATUSES
    confirmed = bool(row.get("last_confirmed_at"))

    age = None if hidden else _age_days(row, now=now)
    stale = bool(age is not None and age >= stale_after_days and not confirmed)

    confidence = _as_float(row.get("confidence"), 1.0)
    needs_confirmation = bool(
        not hidden
        and (
            stale
            or confidence < LOW_CONFIDENCE_THRESHOLD
            or _as_text(row.get("status")).casefold() in {"needs_review", "pending_review"}
        )
    )

    if hidden:
        reason = state
    elif stale:
        reason = "stale"
    elif needs_confirmation:
        reason = "needs_confirmation"
    elif confirmed:
        reason = "confirmed"
    else:
        reason = "active"

    return MemoryLifecycleAssessment(
        state=state,
        hidden=hidden,
        stale=stale,
        needs_confirmation=needs_confirmation,
        confirmed=confirmed,
        age_days=age,
        reason=reason,
    )


def build_lifecycle_aggregate(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    now: datetime | None = None,
) -> MemoryLifecycleAggregate:
    now = now or datetime.now(timezone.utc)
    assessments = [
        assess_memory_lifecycle(row, now=now)
        for row in rows
        if isinstance(row, dict)
    ]

    return MemoryLifecycleAggregate(
        total=len(assessments),
        active=sum(1 for item in assessments if item.state == "active"),
        hidden=sum(1 for item in assessments if item.hidden),
        stale=sum(1 for item in assessments if item.stale),
        needs_confirmation=sum(1 for item in assessments if item.needs_confirmation),
        confirmed=sum(1 for item in assessments if item.confirmed and not item.hidden),
    )


def safe_lifecycle_diagnostics(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> str:
    return build_lifecycle_aggregate(rows).safe_diagnostics()
