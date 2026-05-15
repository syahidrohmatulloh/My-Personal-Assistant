"""Supabase client used from the FastAPI backend.

We use the service role key, which bypasses Row-Level Security. This is fine
because the backend has already verified the JWT and knows the user_id — we
then filter every query by that user_id ourselves. RLS still protects against
the frontend talking to Supabase directly (which it does for auth).

# Connection lifecycle

Postgrest (the REST layer Supabase exposes) speaks HTTP/2. We hold a singleton
client. When Fly restarts a machine or migrates it, the HTTP/2 connection is
torn down server-side, but our client still holds the dead socket. The next
request fails with `httpx.RemoteProtocolError: ConnectionTerminated`.

To handle this:
  - `reset_supabase()` clears the cached singleton so the next call creates fresh.
  - `safe_execute()` wraps a callable, catches transport errors, resets the
    client, and retries once.

Use `safe_execute()` for any call where stale connections would cause
visible user-facing failure (the main chat pipeline). Lower-priority
background tasks can call directly and rely on their own logging.

Important: never expose SUPABASE_SERVICE_ROLE_KEY to the frontend. Only the
anon key goes in the browser.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Callable, TypeVar

import httpx
from supabase import Client, create_client

from app.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T")


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def reset_supabase() -> None:
    """Drop the cached client so the next get_supabase() call creates fresh."""
    get_supabase.cache_clear()


# Errors that indicate the underlying TCP/HTTP2 connection is dead.
# Catching these specifically (rather than broad Exception) avoids hiding
# real bugs.
_TRANSIENT_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.PoolTimeout,
)


def safe_execute(fn: Callable[[Client], T]) -> T:
    """Run `fn(supabase_client)` with one retry on transient transport errors.

    Use this wrapper around any synchronous supabase call from the hot path
    (chat router, prompt build, etc) where a stale connection would surface
    to the user.

    Example:
        result = safe_execute(
            lambda sb: sb.table("conversations").select("*").eq("user_id", uid).execute()
        )
    """
    try:
        return fn(get_supabase())
    except _TRANSIENT_TRANSPORT_ERRORS as exc:
        log.warning("supabase: transient transport error, resetting client: %s", exc)
        reset_supabase()
        # One retry. If it fails again, propagate so the caller can decide.
        return fn(get_supabase())
