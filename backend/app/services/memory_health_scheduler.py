"""Automatic read-only memory health scheduler.

This scheduler never edits, archives, merges, or resolves memories.
It periodically reads existing memory rows, runs the existing quality engine,
and keeps a lightweight in-process health summary for visibility.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.services import memory_epistemic_governance
from app.services.memory_quality import assess_memory_quality
from app.services.supabase_client import safe_execute

log = logging.getLogger(__name__)

_TASK: asyncio.Task[None] | None = None
_STOP_EVENT: asyncio.Event | None = None
_LAST_STARTED_AT: str | None = None
_LAST_FINISHED_AT: str | None = None
_LAST_ERROR: str | None = None
_LAST_SUMMARY_BY_USER: dict[str, dict[str, Any]] = {}
_LAST_TOTAL_USERS = 0
_LAST_TOTAL_MEMORIES = 0

_DIRECT_USER_PRIORITIES = frozenset(
    {
        "explicit_user_statement",
        "user_answer_in_context",
        "user_correction",
    }
)


def _row_is_active_for_health(
    row: dict[str, Any],
) -> bool:
    status_value = str(
        row.get("status") or ""
    ).strip().lower()

    return not bool(
        row.get("archived")
        or row.get("superseded")
        or row.get("deleted_at")
        or status_value in {
            "archived",
            "superseded",
            "deleted",
        }
    )


def _row_is_direct_user_memory(
    row: dict[str, Any],
) -> bool:
    return (
        str(
            row.get("source_priority")
            or ""
        )
        .strip()
        .lower()
        in _DIRECT_USER_PRIORITIES
    )


def _row_is_authoritative_memory(
    row: dict[str, Any],
) -> bool:
    return bool(
        _row_is_direct_user_memory(row)
        or memory_epistemic_governance
        .has_confirmation(row)
    )


def scheduler_enabled() -> bool:
    return _env_bool("MEMORY_HEALTH_SCHEDULER_ENABLED", default=True)


def scheduler_interval_minutes() -> int:
    raw = os.getenv("MEMORY_HEALTH_INTERVAL_MINUTES", "360")
    try:
        value = int(raw)
    except ValueError:
        value = 360

    return max(value, 15)


def scheduler_initial_delay_seconds() -> int:
    raw = os.getenv("MEMORY_HEALTH_INITIAL_DELAY_SECONDS", "30")
    try:
        value = int(raw)
    except ValueError:
        value = 30

    return max(value, 0)


def scheduler_row_limit() -> int:
    raw = os.getenv("MEMORY_HEALTH_MAX_ROWS", "5000")
    try:
        value = int(raw)
    except ValueError:
        value = 5000

    return max(value, 100)


async def start_memory_health_scheduler() -> None:
    global _TASK, _STOP_EVENT

    if not scheduler_enabled():
        log.info("memory health scheduler disabled")
        return

    if _TASK and not _TASK.done():
        return

    _STOP_EVENT = asyncio.Event()
    _TASK = asyncio.create_task(_scheduler_loop(), name="memory-health-scheduler")
    log.info(
        "memory health scheduler started interval_minutes=%s",
        scheduler_interval_minutes(),
    )


async def stop_memory_health_scheduler() -> None:
    global _TASK, _STOP_EVENT

    if _STOP_EVENT:
        _STOP_EVENT.set()

    if _TASK and not _TASK.done():
        _TASK.cancel()
        try:
            await _TASK
        except asyncio.CancelledError:
            pass

    _TASK = None
    _STOP_EVENT = None
    log.info("memory health scheduler stopped")


async def run_memory_health_audit_once() -> dict[str, Any]:
    """Run one read-only audit across existing memory rows."""
    global _LAST_STARTED_AT, _LAST_FINISHED_AT, _LAST_ERROR
    global _LAST_SUMMARY_BY_USER, _LAST_TOTAL_USERS, _LAST_TOTAL_MEMORIES

    started = datetime.now(timezone.utc).isoformat()
    _LAST_STARTED_AT = started
    _LAST_ERROR = None

    try:
        rows = await _load_memory_rows()
        summaries = build_user_memory_health_summaries(rows)

        _LAST_SUMMARY_BY_USER = summaries
        _LAST_TOTAL_USERS = len(summaries)
        _LAST_TOTAL_MEMORIES = len(rows)
        _LAST_FINISHED_AT = datetime.now(timezone.utc).isoformat()

        payload = {
            "ok": True,
            "started_at": started,
            "finished_at": _LAST_FINISHED_AT,
            "users_checked": _LAST_TOTAL_USERS,
            "memories_checked": _LAST_TOTAL_MEMORIES,
            "users_with_review_items": sum(
                1
                for summary in summaries.values()
                if int(summary.get("needs_review", 0)) > 0
            ),
        }

        log.info("memory health audit completed: %s", payload)
        return payload
    except Exception as exc:
        _LAST_ERROR = str(exc)
        _LAST_FINISHED_AT = datetime.now(timezone.utc).isoformat()
        log.warning("memory health audit failed: %s", exc, exc_info=True)
        return {
            "ok": False,
            "started_at": started,
            "finished_at": _LAST_FINISHED_AT,
            "error": _LAST_ERROR,
        }


def build_user_memory_health_summaries(
    memories: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Pure helper used by the scheduler and tests."""
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in memories:
        user_id = str(row.get("user_id") or "").strip()
        if not user_id:
            continue

        by_user[user_id].append(row)

    out: dict[str, dict[str, Any]] = {}

    for user_id, rows in by_user.items():
        assessment = assess_memory_quality(
            rows
        )
        summary = (
            assessment.get("summary")
            or {}
        )

        active_rows = [
            row
            for row in rows
            if _row_is_active_for_health(
                row
            )
        ]

        direct_user_memories = sum(
            1
            for row in active_rows
            if _row_is_direct_user_memory(
                row
            )
        )

        canonically_confirmed_memories = sum(
            1
            for row in active_rows
            if (
                memory_epistemic_governance
                .has_confirmation(row)
            )
        )

        authoritative_memories = sum(
            1
            for row in active_rows
            if _row_is_authoritative_memory(
                row
            )
        )

        unverified_memories = max(
            0,
            len(active_rows)
            - authoritative_memories,
        )

        out[user_id] = {
            "active_memories": int(
                summary.get(
                    "active_memories"
                )
                or 0
            ),
            "duplicate_groups": int(
                summary.get(
                    "duplicate_groups"
                )
                or 0
            ),
            "conflict_groups": int(
                summary.get(
                    "conflict_groups"
                )
                or 0
            ),
            "low_quality_memories": int(
                summary.get(
                    "low_quality_memories"
                )
                or 0
            ),
            "stale_memories": int(
                summary.get(
                    "stale_memories"
                )
                or 0
            ),
            "needs_review": int(
                summary.get(
                    "needs_review"
                )
                or 0
            ),
            "authoritative_memories": (
                authoritative_memories
            ),
            "unverified_memories": (
                unverified_memories
            ),
            "canonically_confirmed_memories": (
                canonically_confirmed_memories
            ),
            "direct_user_memories": (
                direct_user_memories
            ),
        }

    return out


def get_memory_health_scheduler_status(
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    running = bool(_TASK and not _TASK.done())

    payload: dict[str, Any] = {
        "enabled": scheduler_enabled(),
        "running": running,
        "interval_minutes": scheduler_interval_minutes(),
        "last_started_at": _LAST_STARTED_AT,
        "last_finished_at": _LAST_FINISHED_AT,
        "last_error": _LAST_ERROR,
        "last_total_users": _LAST_TOTAL_USERS,
        "last_total_memories": _LAST_TOTAL_MEMORIES,
    }

    if user_id:
        payload["user_summary"] = _LAST_SUMMARY_BY_USER.get(user_id)

    return payload


async def _scheduler_loop() -> None:
    stop_event = _STOP_EVENT
    if stop_event is None:
        return

    initial_delay = scheduler_initial_delay_seconds()
    if initial_delay:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=initial_delay)
            return
        except asyncio.TimeoutError:
            pass

    while not stop_event.is_set():
        await run_memory_health_audit_once()

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=scheduler_interval_minutes() * 60,
            )
        except asyncio.TimeoutError:
            continue


async def _load_memory_rows() -> list[dict[str, Any]]:
    limit = scheduler_row_limit()

    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id,user_id,content,kind,category,structured_field,"
                "structured_value,source,source_priority,confidence,"
                "archived,superseded,status,deleted_at,created_at,updated_at,"
                "last_confirmed_at,last_user_confirmed_at,"
                "last_user_confirmation_source,"
                "last_user_confirmation_evidence"
            )
            .limit(limit)
            .execute()
        )
    )

    return list(result.data or [])


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}
