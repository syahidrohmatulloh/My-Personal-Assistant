"""Anthropic async client.

Why async: FastAPI is async, and streaming responses with sync code blocks the
whole event loop. AsyncAnthropic + uvicorn lets one process handle many
concurrent chats.
"""

from functools import lru_cache

from anthropic import AsyncAnthropic

from app.config import settings


@lru_cache(maxsize=1)
def get_claude() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
