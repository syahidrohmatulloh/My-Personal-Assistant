"""Deterministic conversation chronology context.

This is for questions like:
- "when did we first chat?"
- "awal mula kita chatting tanggal berapa?"
- "conversation pertama kita kapan?"

Those questions are not semantic memories. They should be answered from
conversation/message metadata, not embedding retrieval.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from app.services.supabase_client import safe_execute


_CHRONOLOGY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(first|earliest|oldest)\b.{0,80}\b(chat|chatting|conversation|message|talk|talking)\b",
        r"\b(chat|chatting|conversation|message|talk|talking)\b.{0,80}\b(first|earliest|oldest)\b",
        r"\bwhen\b.{0,100}\b(first|start|started|begin|began)\b.{0,100}\b(chat|chatting|talk|talking|conversation)\b",
        r"\bhow long\b.{0,80}\b(chatting|talking|known|together)\b",
        r"pertama kali.{0,80}(chat|ngobrol|conversation|pesan|message)",
        r"(awal mula|awal kita|mulai).{0,80}(chat|ngobrol|conversation|pesan)",
        r"(chat|ngobrol|conversation|pesan).{0,80}(pertama|awal mula|mulai)",
        r"tanggal berapa.{0,80}(chat|ngobrol|conversation|pesan)",
        r"sejak kapan.{0,80}(chat|ngobrol|conversation|pesan|kenal)",
        r"udah berapa lama.{0,80}(chat|ngobrol|conversation|kenal)",
    )
)


@dataclass(frozen=True)
class ConversationChronology:
    first_conversation_id: str | None
    first_conversation_title: str | None
    first_conversation_created_at: str | None
    first_message_created_at: str | None
    latest_conversation_updated_at: str | None
    conversation_count: int
    source: str = "database"


def is_chronology_question(text: str | None) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    return any(pattern.search(value) for pattern in _CHRONOLOGY_PATTERNS)


async def build_context_if_relevant(*, user_id: str, query_text: str | None) -> str | None:
    if not is_chronology_question(query_text):
        return None

    chronology = await get_conversation_chronology(user_id=user_id)
    return render_chronology_context(chronology)


async def get_conversation_chronology(*, user_id: str) -> ConversationChronology:
    first_conversation_res, latest_conversation_res, count_res = await asyncio.gather(
        asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("conversations")
                .select("id,title,created_at,updated_at")
                .eq("user_id", user_id)
                .order("created_at", desc=False)
                .limit(1)
                .execute()
            )
        ),
        asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("conversations")
                .select("id,updated_at")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
        ),
        asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("conversations")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        ),
    )

    first_conversation = _first(first_conversation_res.data)
    latest_conversation = _first(latest_conversation_res.data)

    first_message_created_at = None
    if first_conversation and first_conversation.get("id"):
        first_message_res = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("messages")
                .select("created_at")
                .eq("conversation_id", first_conversation["id"])
                .order("created_at", desc=False)
                .limit(1)
                .execute()
            )
        )
        first_message = _first(first_message_res.data)
        first_message_created_at = first_message.get("created_at") if first_message else None

    return ConversationChronology(
        first_conversation_id=str(first_conversation.get("id")) if first_conversation else None,
        first_conversation_title=first_conversation.get("title") if first_conversation else None,
        first_conversation_created_at=first_conversation.get("created_at") if first_conversation else None,
        first_message_created_at=first_message_created_at,
        latest_conversation_updated_at=latest_conversation.get("updated_at") if latest_conversation else None,
        conversation_count=int(getattr(count_res, "count", 0) or 0),
    )


def render_chronology_context(chronology: ConversationChronology) -> str:
    if not chronology.first_conversation_created_at and not chronology.first_message_created_at:
        return (
            "## Conversation chronology (deterministic database lookup)\n"
            "- No conversation chronology is available for this user yet.\n"
            "- If asked when the first chat happened, say you cannot find it in the app database yet."
        )

    first_at = chronology.first_message_created_at or chronology.first_conversation_created_at
    first_date = _date_only(first_at)

    lines = [
        "## Conversation chronology (deterministic database lookup)",
        "- Use this block when the user asks when they first chatted, started chatting, or how long the app has known them.",
        "- This comes from app database metadata, not semantic memory.",
        f"- First known conversation date: {first_date or first_at}",
        f"- First known conversation timestamp: {first_at}",
    ]

    if chronology.first_conversation_title:
        lines.append(f"- First known conversation title: {chronology.first_conversation_title}")

    if chronology.latest_conversation_updated_at:
        lines.append(f"- Latest conversation activity timestamp: {chronology.latest_conversation_updated_at}")

    lines.append(f"- Total conversations found: {chronology.conversation_count}")
    lines.append(
        "- If answering in Indonesian, say roughly: "
        '"Dari data app, chat pertama kita yang tercatat adalah ..." '
        "Do not say you cannot access this if the timestamp above is present."
    )

    return "\n".join(lines)


def _first(rows: Any) -> dict[str, Any] | None:
    if isinstance(rows, list) and rows:
        row = rows[0]
        return row if isinstance(row, dict) else None
    return None


def _date_only(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return value[:10] if len(value) >= 10 else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.date().isoformat()
