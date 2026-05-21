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


_HIGH_CONFIDENCE_PHRASES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # English explicit forms
        r"\bwhen\b.{0,100}\b(first|start|started|begin|began)\b.{0,100}\b(chat|chatted|chatting|talk|talked|talking|conversation|message)\b",
        r"\b(first|earliest|oldest)\b.{0,100}\b(chat|chatted|chatting|talk|talked|talking|conversation|message)\b",
        r"\b(chat|chatted|chatting|talk|talked|talking|conversation|message)\b.{0,100}\b(first|earliest|oldest)\b",
        r"\bhow\s+long\b.{0,100}\b(chatting|talking|known|conversation|using this app)\b",

        # Indonesian explicit forms. Use \s* so "pertama kali", "pertamakali",
        # and "pertama   kali" are treated the same.
        r"pertama\s*kali.{0,120}(chat|chatting|ngobrol|obrol|conversation|pesan|message|bicara|ngomong)",
        r"(chat|chatting|ngobrol|obrol|conversation|pesan|message|bicara|ngomong).{0,120}pertama\s*kali",
        r"(awal\s*mula|awal\s*kita|mulai).{0,120}(chat|chatting|ngobrol|obrol|conversation|pesan|message|bicara|ngomong)",
        r"(chat|chatting|ngobrol|obrol|conversation|pesan|message|bicara|ngomong).{0,120}(awal\s*mula|awal\s*kita|mulai)",
        r"tanggal\s*berapa.{0,120}(chat|chatting|ngobrol|obrol|conversation|pesan|message|bicara|ngomong)",
        r"sejak\s*kapan.{0,120}(chat|chatting|ngobrol|obrol|conversation|pesan|message|bicara|ngomong|kenal)",
        r"(udah|sudah).{0,30}berapa\s*lama.{0,120}(chat|chatting|ngobrol|obrol|conversation|kenal)",
    )
)

_CHRONOLOGY_TERMS = {
    "first",
    "earliest",
    "oldest",
    "start",
    "started",
    "begin",
    "began",
    "beginning",
    "since",
    "awal",
    "mula",
    "mulai",
    "pertama",
    "sejak",
    "kapan",
    "tanggal",
    "lama",
}

_CONVERSATION_TERMS = {
    "chat",
    "chatting",
    "conversation",
    "conversations",
    "message",
    "messages",
    "talk",
    "talked",
    "talking",
    "ngobrol",
    "obrol",
    "obrolan",
    "pesan",
    "bicara",
    "ngomong",
    "kenal",
}

_NEGATIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # Avoid falsely triggering on generic preference/memory questions.
        r"\b(favorite|favourite|prefer|preference|suka|kesukaan|makanan|warna|hobi)\b",
        r"\b(calendar|kalender|meeting|schedule|jadwal)\b.{0,80}\bpertama\b",
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
    """Return True when the user asks for conversation chronology.

    This intentionally does not rely on a single phrase. Users may write:
    - "pertama kali chat"
    - "pertamakali chatting"
    - "awal mula kita ngobrol"
    - "when did we first talk?"
    - "udah berapa lama kita chat?"

    The detector combines:
    1. high-confidence phrase regexes;
    2. normalized token/proximity matching;
    3. joined-text checks for Indonesian spacing variants.
    """
    raw = (text or "").strip()
    if not raw:
        return False

    normalized = _normalize_for_detection(raw)
    joined = normalized.replace(" ", "")

    if any(pattern.search(normalized) or pattern.search(raw) for pattern in _HIGH_CONFIDENCE_PHRASES):
        return True

    # Catch compact Indonesian variants that may be missed by punctuation/spacing:
    # "pertamakalichatting", "awalmulangobrol", etc.
    compact_pairs = (
        ("pertamakali", ("chat", "chatting", "ngobrol", "obrol", "pesan")),
        ("awalmula", ("chat", "chatting", "ngobrol", "obrol", "pesan")),
        ("sejakkapan", ("chat", "chatting", "ngobrol", "obrol", "kenal")),
        ("tanggalberapa", ("chat", "chatting", "ngobrol", "obrol", "pesan")),
    )
    for chrono_compact, conversation_compacts in compact_pairs:
        if chrono_compact in joined and any(term in joined for term in conversation_compacts):
            return True

    if any(pattern.search(normalized) for pattern in _NEGATIVE_PATTERNS):
        # Still allow explicit "first chat" forms despite generic words.
        if not any(pattern.search(normalized) for pattern in _HIGH_CONFIDENCE_PHRASES):
            return False

    tokens = normalized.split()
    if not tokens:
        return False

    chronology_positions = [
        idx for idx, token in enumerate(tokens)
        if token in _CHRONOLOGY_TERMS or token.startswith(("pertama", "awal", "mulai"))
    ]
    conversation_positions = [
        idx for idx, token in enumerate(tokens)
        if token in _CONVERSATION_TERMS
        or token.startswith(("chat", "talk", "ngobrol", "obrol", "conversation", "message"))
    ]

    if not chronology_positions or not conversation_positions:
        return False

    # Users often phrase it casually; allow proximity within a short sentence.
    closest_distance = min(
        abs(a - b) for a in chronology_positions for b in conversation_positions
    )
    if closest_distance <= 12:
        return True

    # For questions with explicit time-question words, allow a slightly wider window.
    questionish = {"kapan", "tanggal", "when", "how", "long", "lama", "sejak"}
    if any(token in questionish for token in tokens) and closest_distance <= 20:
        return True

    return False


def _normalize_for_detection(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[_\-\\/]+", " ", value)
    value = re.sub(r"[^a-z0-9\u00c0-\u024f\u1e00-\u1eff]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


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
