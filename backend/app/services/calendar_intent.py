"""LLM-assisted calendar intent extraction.

This module is intentionally used as a fallback after the deterministic calendar
candidate extractor. It lets Haiku read the current user message together with
recent chat context and browser-provided local time, then returns a strict JSON
draft that the deterministic persistence layer still validates before saving.

It never creates Google Calendar events directly.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import importlib
import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

MODEL_NAME = "claude-haiku-4-5"

SYSTEM_PROMPT = """You extract calendar event drafts for a review-first personal assistant app.

Return ONLY one JSON object. No markdown. No prose.

Schema:
{
  "is_calendar_candidate": true/false,
  "title": string|null,
  "event_date": "YYYY-MM-DD"|null,
  "start_at": "YYYY-MM-DDTHH:MM:SS+07:00"|null,
  "end_at": "YYYY-MM-DDTHH:MM:SS+07:00"|null,
  "all_day": true/false,
  "location": string|null,
  "confidence": number,
  "reason": string
}

Rules:
- Extract only if the user is asking to add/schedule/catat/masukin something to a calendar, or clearly states a scheduled event.
- The app is review-first: you are only preparing a Calendar event draft, not creating a Google Calendar event unless the caller explicitly uses the Google Calendar create flow.
- Use the browser/client local time context as the source of truth.
- Use recent conversation context when the user says things like "setelah dari agora", "habis itu", "same event", "yang tadi", or omits the date but clearly refers to the current day/context.
- If the user explicitly asks to add to calendar, provides a time, and no date is stated, default to the client local date when it is available.
- If date/time cannot be inferred safely, set missing fields to null and lower confidence.
- Use ISO timestamps with the user's timezone offset. If timezone is missing, use +07:00.
- Keep title concise and user-friendly.
- Prefer preserving important people, purpose, and location.
- Do not include phrases like "masukin kalender", "tolong", or raw database fields in the title.
"""


def _get_claude_client():
    from app.services.claude import get_claude

    return get_claude()


def _client_context_dict(client_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(client_context, dict):
        return {}

    return {
        key: value
        for key, value in client_context.items()
        if key in {"local_time", "timezone", "timezone_offset_minutes", "locale"}
    }


def _compact_recent_messages(recent_messages: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []

    for message in (recent_messages or [])[-10:]:
        role = str(message.get("role") or "").strip()
        content = message.get("content")

        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            text = "\n".join(parts)
        else:
            text = str(content or "")

        text = re.sub(r"\s+", " ", text).strip()
        if not role or not text:
            continue

        compact.append({"role": role, "content": text[:700]})

    return compact


def _response_text(response: Any) -> str:
    chunks: list[str] = []

    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(str(text))

    if chunks:
        return "\n".join(chunks).strip()

    return str(response or "").strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    return value if isinstance(value, dict) else None


def _normalise_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except Exception:
        return 0.0

    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def _valid_iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()
    try:
        date.fromisoformat(value)
    except ValueError:
        return None

    return value


def _valid_iso_datetime(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    return value


def _fallback_event_date_from_start(start_at: str | None) -> str | None:
    if not start_at:
        return None

    try:
        return datetime.fromisoformat(start_at.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _default_end_at(start_at: str | None) -> str | None:
    if not start_at:
        return None

    try:
        start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    except ValueError:
        return None

    return (start + timedelta(hours=1)).isoformat()


def _clean_title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    title = re.sub(r"\s+", " ", value).strip(" ,.;:-")
    title = re.sub(
        r"(?i)\b(masukin|masukkan|tambahin|tambahkan|catat|buat|bikin)\b.{0,35}\b(kalender|calendar|jadwal)\b[:,]?",
        " ",
        title,
    )
    title = re.sub(r"(?i)\b(tolong|please|ya|dong|beb)\b", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" ,.;:-")

    if not title:
        return None

    return title[:160]


def normalise_calendar_intent_draft(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not raw.get("is_calendar_candidate"):
        return None

    title = _clean_title(raw.get("title"))
    start_at = _valid_iso_datetime(raw.get("start_at"))
    end_at = _valid_iso_datetime(raw.get("end_at"))
    event_date = _valid_iso_date(raw.get("event_date")) or _fallback_event_date_from_start(start_at)
    confidence = _normalise_confidence(raw.get("confidence"))

    if not title or not event_date:
        return None

    if start_at and not end_at:
        end_at = _default_end_at(start_at)

    all_day = bool(raw.get("all_day"))
    if start_at:
        all_day = False

    if confidence < 0.62:
        return None

    location = raw.get("location")
    if isinstance(location, str):
        location = re.sub(r"\s+", " ", location).strip(" ,.;:-")[:180] or None
    else:
        location = None

    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "haiku_calendar_intent"

    return {
        "title": title,
        "event_date": event_date,
        "start_at": start_at,
        "end_at": end_at,
        "all_day": all_day,
        "location": location,
        "confidence": confidence,
        "reason": reason[:160],
    }


async def extract_calendar_intent_draft(
    *,
    user_message: str,
    recent_messages: list[dict[str, Any]] | None = None,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not user_message.strip():
        return None

    payload = {
        "client_context": _client_context_dict(client_context),
        "recent_messages": _compact_recent_messages(recent_messages),
        "current_user_message": user_message,
    }

    prompt = (
        "Extract a review-first calendar event draft from this conversation payload.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )

    claude = _get_claude_client()
    response = await claude.messages.create(
        model=MODEL_NAME,
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    parsed = _parse_json_object(_response_text(response))
    if not parsed:
        return None

    return normalise_calendar_intent_draft(parsed)
