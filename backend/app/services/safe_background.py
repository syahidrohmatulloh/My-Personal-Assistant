"""Safe background task helpers.

FastAPI BackgroundTasks are convenient, but task failures can be hard to notice.
This wrapper adds:
- task name logging;
- small retry loop;
- support for sync and async callables;
- no impact on the main streaming response.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

from fastapi import BackgroundTasks

log = logging.getLogger(__name__)


def _task_name(func: Callable[..., Any]) -> str:
    module = getattr(func, "__module__", "")
    qualname = getattr(func, "__qualname__", getattr(func, "__name__", "unknown"))
    return f"{module}.{qualname}".strip(".")


async def safe_background_task(
    task_name: str,
    func: Callable[..., Any],
    *args: Any,
    retries: int = 2,
    retry_delay_seconds: float = 1.0,
    **kwargs: Any,
) -> None:
    """Run a background task with logging and lightweight retry."""
    attempts = max(1, retries + 1)

    for attempt in range(1, attempts + 1):
        try:
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                await result

            if attempt > 1:
                log.info(
                    "background task succeeded after retry task=%s attempt=%s",
                    task_name,
                    attempt,
                )
            return
        except Exception as exc:  # noqa: BLE001
            if attempt >= attempts:
                log.exception(
                    "background task failed permanently task=%s attempts=%s",
                    task_name,
                    attempts,
                )
                return

            log.warning(
                "background task failed task=%s attempt=%s/%s error=%s",
                task_name,
                attempt,
                attempts,
                exc,
            )
            await asyncio.sleep(retry_delay_seconds)


def add_safe_background_task(
    background_tasks: BackgroundTasks,
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Add a FastAPI background task wrapped with safe_background_task."""
    background_tasks.add_task(
        safe_background_task,
        _task_name(func),
        func,
        *args,
        **kwargs,
    )
