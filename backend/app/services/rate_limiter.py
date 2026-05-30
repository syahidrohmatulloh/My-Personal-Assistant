"""Lightweight in-memory rate limiter.

This is intentionally simple:
- protects expensive endpoints from accidental spam/abuse;
- stores counters only in memory per running Fly machine;
- uses a hashed bearer token when available, otherwise client IP;
- does not require Redis or an external queue.

For multi-machine deployments this is best-effort, not a global hard limit.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class RateLimitRule:
    path: str
    max_requests: int
    window_seconds: int


_RULES: tuple[RateLimitRule, ...] = (
    RateLimitRule(path="/chat", max_requests=20, window_seconds=60),
    RateLimitRule(path="/voice/speak", max_requests=30, window_seconds=60),
    RateLimitRule(path="/voice/transcribe", max_requests=20, window_seconds=60),
    RateLimitRule(path="/attachments/upload", max_requests=12, window_seconds=60),
)

# key: "{path}:{identity}:{window_seconds}" -> timestamps
_BUCKETS: dict[str, Deque[float]] = defaultdict(deque)
_LOCK = asyncio.Lock()


def _matched_rule(path: str) -> RateLimitRule | None:
    for rule in _RULES:
        if path == rule.path:
            return rule
    return None


def _client_identity(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
            return f"token:{digest}"

    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return f"ip:{forwarded_for.split(',', 1)[0].strip()}"

    if request.client and request.client.host:
        return f"ip:{request.client.host}"

    return "unknown"


def _retry_after_seconds(bucket: Deque[float], *, now: float, window_seconds: int) -> int:
    if not bucket:
        return window_seconds

    oldest = bucket[0]
    retry_after = max(1, int(window_seconds - (now - oldest)))
    return retry_after


async def check_rate_limit(request: Request) -> JSONResponse | None:
    """Return a 429 response when the request exceeds its endpoint limit."""
    if request.method.upper() == "OPTIONS":
        return None

    rule = _matched_rule(request.url.path)
    if rule is None:
        return None

    now = time.monotonic()
    identity = _client_identity(request)
    key = f"{rule.path}:{identity}:{rule.window_seconds}"

    async with _LOCK:
        bucket = _BUCKETS[key]
        cutoff = now - rule.window_seconds

        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= rule.max_requests:
            retry_after = _retry_after_seconds(
                bucket,
                now=now,
                window_seconds=rule.window_seconds,
            )
            return JSONResponse(
                {
                    "detail": "Too many requests. Please wait before trying again.",
                    "retry_after_seconds": retry_after,
                },
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)

    return None
