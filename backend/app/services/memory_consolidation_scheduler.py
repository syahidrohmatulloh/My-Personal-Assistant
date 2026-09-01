"""M33 — optional deferred memory consolidation scheduler.

The scheduler is disabled by default. When enabled, it periodically runs the
deterministic M33 evidence-consolidation service for users with recent memory
activity.

It does not import CognitiveRuntime, does not call an LLM, and does not emit a
per-turn cognitive trace.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services import memory_consolidation
from app.services.supabase_client import safe_execute


log = logging.getLogger(__name__)

_TASK: asyncio.Task[None] | None = None
_STOP_EVENT: asyncio.Event | None = None

_LAST_STARTED_AT: str | None = None
_LAST_FINISHED_AT: str | None = None
_LAST_ERROR: str | None = None
_LAST_SUMMARY: dict[str, Any] | None = None

DEFAULT_INTERVAL_MINUTES = 1440
DEFAULT_INITIAL_DELAY_SECONDS = 120
DEFAULT_LOOKBACK_DAYS = 30
MAX_USERS_PER_CYCLE = 200
MAX_DISCOVERY_ROWS = 5000


def scheduler_enabled() -> bool:
    value = os.getenv(
        "MEMORY_CONSOLIDATION_SCHEDULER_ENABLED"
    )
    if value is None:
        return False

    return value.strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def scheduler_interval_minutes() -> int:
    raw = os.getenv(
        "MEMORY_CONSOLIDATION_INTERVAL_MINUTES",
        str(DEFAULT_INTERVAL_MINUTES),
    )
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_INTERVAL_MINUTES

    return max(value, 60)


def scheduler_initial_delay_seconds() -> int:
    raw = os.getenv(
        "MEMORY_CONSOLIDATION_INITIAL_DELAY_SECONDS",
        str(DEFAULT_INITIAL_DELAY_SECONDS),
    )
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_INITIAL_DELAY_SECONDS

    return max(value, 0)


def scheduler_lookback_days() -> int:
    raw = os.getenv(
        "MEMORY_CONSOLIDATION_LOOKBACK_DAYS",
        str(DEFAULT_LOOKBACK_DAYS),
    )
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_LOOKBACK_DAYS

    return min(max(value, 7), 90)


async def start_memory_consolidation_scheduler() -> None:
    global _TASK, _STOP_EVENT

    if not scheduler_enabled():
        log.info(
            "memory consolidation scheduler disabled"
        )
        return

    if _TASK and not _TASK.done():
        return

    _STOP_EVENT = asyncio.Event()
    _TASK = asyncio.create_task(
        _scheduler_loop(),
        name="memory-consolidation-scheduler",
    )

    log.info(
        "memory consolidation scheduler started "
        "interval_minutes=%s",
        scheduler_interval_minutes(),
    )


async def stop_memory_consolidation_scheduler() -> None:
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

    log.info(
        "memory consolidation scheduler stopped"
    )


async def _load_candidate_user_ids(
    *,
    days: int,
) -> list[str]:
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=max(1, days))
    ).isoformat()

    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "user_id,archived,superseded,status,"
                "deleted_at,created_at"
            )
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(MAX_DISCOVERY_ROWS)
            .execute()
        )
    )

    users: list[str] = []
    seen: set[str] = set()

    for row in (
        getattr(result, "data", None)
        or []
    ):
        if (
            row.get("archived")
            or row.get("superseded")
            or row.get("deleted_at")
            or str(
                row.get("status")
                or ""
            ).strip().casefold()
            in {"archived", "superseded", "deleted"}
        ):
            continue

        user_id = str(
            row.get("user_id")
            or ""
        ).strip()

        if not user_id or user_id in seen:
            continue

        seen.add(user_id)
        users.append(user_id)

        if len(users) >= MAX_USERS_PER_CYCLE:
            break

    return users


async def run_memory_consolidation_cycle_once() -> dict[str, Any]:
    global _LAST_STARTED_AT, _LAST_FINISHED_AT
    global _LAST_ERROR, _LAST_SUMMARY

    started = datetime.now(
        timezone.utc
    ).isoformat()

    _LAST_STARTED_AT = started
    _LAST_ERROR = None

    lookback_days = scheduler_lookback_days()

    try:
        user_ids = await _load_candidate_user_ids(
            days=lookback_days,
        )
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR = type(exc).__name__
        _LAST_FINISHED_AT = datetime.now(
            timezone.utc
        ).isoformat()

        result = {
            "ok": False,
            "started_at": started,
            "finished_at": _LAST_FINISHED_AT,
            "users_checked": 0,
            "merged": 0,
            "failed_users": 0,
            "error_type": type(exc).__name__,
        }
        _LAST_SUMMARY = result
        return result

    merged = 0
    failed_users = 0
    users_with_candidates = 0

    for user_id in user_ids:
        try:
            result = (
                await memory_consolidation
                .consolidate_and_persist(
                    user_id=user_id,
                    days=lookback_days,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failed_users += 1
            log.warning(
                "memory consolidation failed "
                "user=%s type=%s",
                user_id[:8],
                type(exc).__name__,
            )
            continue

        merged += int(
            result.get("merged")
            or 0
        )

        if int(
            result.get("candidates")
            or 0
        ) > 0:
            users_with_candidates += 1

        if not result.get("ok", False):
            failed_users += 1

    _LAST_FINISHED_AT = datetime.now(
        timezone.utc
    ).isoformat()

    payload = {
        "ok": failed_users == 0,
        "started_at": started,
        "finished_at": _LAST_FINISHED_AT,
        "users_checked": len(user_ids),
        "users_with_candidates": (
            users_with_candidates
        ),
        "merged": merged,
        "failed_users": failed_users,
        "lookback_days": lookback_days,
    }

    _LAST_SUMMARY = payload

    log.info(
        "memory consolidation cycle completed: %s",
        payload,
    )

    return payload


def get_memory_consolidation_scheduler_status() -> dict[str, Any]:
    return {
        "enabled": scheduler_enabled(),
        "running": bool(
            _TASK
            and not _TASK.done()
        ),
        "interval_minutes": (
            scheduler_interval_minutes()
        ),
        "lookback_days": (
            scheduler_lookback_days()
        ),
        "last_started_at": _LAST_STARTED_AT,
        "last_finished_at": _LAST_FINISHED_AT,
        "last_error": _LAST_ERROR,
        "last_summary": _LAST_SUMMARY,
    }


async def _scheduler_loop() -> None:
    stop_event = _STOP_EVENT
    if stop_event is None:
        return

    initial_delay = (
        scheduler_initial_delay_seconds()
    )

    if initial_delay:
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=initial_delay,
            )
            return
        except asyncio.TimeoutError:
            pass

    while not stop_event.is_set():
        await run_memory_consolidation_cycle_once()

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=(
                    scheduler_interval_minutes()
                    * 60
                ),
            )
        except asyncio.TimeoutError:
            continue
