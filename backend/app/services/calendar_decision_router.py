"""LLM decision router for Calendar chat confirmations.

This module intentionally avoids hardcoded natural-language confirmation phrases.
Haiku classifies the user's reply against the latest hidden pending Calendar
suggestion and returns a safe structured action. Backend code remains the
execution gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any

from app.services.claude import get_claude

log = logging.getLogger(__name__)

MODEL_NAME = "claude-haiku-4-5"

ALLOWED_ACTIONS = {
    "accept_local",
    "accept_google",
    "dismiss",
    "clarify",
    "none",
}

MIN_CONFIDENCE_TO_EXECUTE = 0.72

SYSTEM_PROMPT = """You are a Calendar decision router for a personal assistant app.

Your job:
- Read the user's latest message.
- Compare it with pending hidden Calendar suggestions.
- Decide whether the user is accepting, accepting to Google Calendar, dismissing, asking for clarification, or doing nothing.

Return ONLY one JSON object. No markdown. No prose.

Schema:
{
  "intent": "calendar_confirmation",
  "action": "accept_local" | "accept_google" | "dismiss" | "clarify" | "none",
  "target_memory_id": string | null,
  "confidence": number,
  "reason": string
}

Rules:
- Use semantic understanding, not keyword matching.
- If the user confirms adding the pending suggestion to the app Calendar, action="accept_local".
- If the user confirms adding/syncing the pending suggestion to Google Calendar, action="accept_google".
- If the user declines, cancels, skips, ignores, or says not to add it, action="dismiss".
- If there are multiple suggestions and the target is unclear, action="clarify".
- If the message is unrelated, action="none".
- Only choose a target_memory_id from the provided pending suggestions.
- If confidence is below 0.72, use action="none" or "clarify".
- Never invent an event or a memory id.
"""


@dataclass
class CalendarDecision:
    action: str
    target_memory_id: str | None
    confidence: float
    reason: str


async def classify_calendar_confirmation(
    *,
    user_message: str,
    pending_suggestions: list[dict[str, Any]],
    recent_messages: list[dict[str, Any]] | None = None,
    client_context: dict[str, Any] | None = None,
) -> CalendarDecision:
    if not pending_suggestions:
        return CalendarDecision(
            action="none",
            target_memory_id=None,
            confidence=0.0,
            reason="no_pending_suggestions",
        )

    payload = {
        "current_user_message": user_message,
        "pending_calendar_suggestions": [_compact_suggestion(row) for row in pending_suggestions[:5]],
        "recent_messages": _compact_recent_messages(recent_messages),
        "client_context": _client_context_dict(client_context),
        "allowed_actions": sorted(ALLOWED_ACTIONS),
    }

    prompt = "Classify this Calendar confirmation decision.\n\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )

    try:
        response = await get_claude().messages.create(
            model=MODEL_NAME,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("calendar_decision_router: LLM classify failed: %s", exc)
        return CalendarDecision(
            action="none",
            target_memory_id=None,
            confidence=0.0,
            reason="llm_failed",
        )

    raw = _parse_json_object(_response_text(response))
    return _normalise_decision(raw, pending_suggestions)


def should_execute_decision(decision: CalendarDecision) -> bool:
    return (
        decision.action in {"accept_local", "accept_google", "dismiss"}
        and bool(decision.target_memory_id)
        and decision.confidence >= MIN_CONFIDENCE_TO_EXECUTE
    )


def _normalise_decision(
    raw: dict[str, Any] | None,
    pending_suggestions: list[dict[str, Any]],
) -> CalendarDecision:
    if not isinstance(raw, dict):
        return CalendarDecision(action="none", target_memory_id=None, confidence=0.0, reason="invalid_json")

    action = str(raw.get("action") or "none").strip().lower()
    if action not in ALLOWED_ACTIONS:
        action = "none"

    confidence = _normalise_confidence(raw.get("confidence"))
    valid_ids = {str(row.get("id")) for row in pending_suggestions if row.get("id")}
    target_memory_id = str(raw.get("target_memory_id") or "").strip() or None

    if target_memory_id not in valid_ids:
        if len(valid_ids) == 1 and action in {"accept_local", "accept_google", "dismiss"} and confidence >= 0.86:
            target_memory_id = next(iter(valid_ids))
        else:
            target_memory_id = None
            if action in {"accept_local", "accept_google", "dismiss"}:
                action = "clarify" if len(valid_ids) > 1 else "none"

    if confidence < MIN_CONFIDENCE_TO_EXECUTE and action in {"accept_local", "accept_google", "dismiss"}:
        action = "clarify" if len(valid_ids) > 1 else "none"

    return CalendarDecision(
        action=action,
        target_memory_id=target_memory_id,
        confidence=confidence,
        reason=str(raw.get("reason") or "").strip()[:300],
    )


def _compact_suggestion(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("calendar_event_title") or _title_from_row(row),
        "date": row.get("calendar_event_date") or row.get("due_date"),
        "start_at": row.get("calendar_event_start_at"),
        "end_at": row.get("calendar_event_end_at"),
        "all_day": row.get("calendar_event_all_day"),
        "content": row.get("content"),
        "structured_value": row.get("structured_value"),
        "updated_at": row.get("updated_at"),
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
        text = " ".join(text.split()).strip()
        if role and text:
            compact.append({"role": role, "content": text[:700]})
    return compact


def _client_context_dict(client_context: Any) -> dict[str, Any]:
    if hasattr(client_context, "model_dump"):
        client_context = client_context.model_dump(exclude_none=True)
    elif hasattr(client_context, "dict"):
        client_context = client_context.dict(exclude_none=True)

    if not isinstance(client_context, dict):
        return {}

    return {
        key: value
        for key, value in client_context.items()
        if key in {"local_time", "timezone", "timezone_offset_minutes", "locale"}
    }


def _title_from_row(row: dict[str, Any]) -> str:
    raw = str(row.get("calendar_event_title") or row.get("structured_value") or row.get("content") or "Untitled event")
    raw = raw.split("| due_date=", 1)[0]
    raw = raw.removeprefix("User has a scheduled event: ")
    if " on 20" in raw:
        raw = raw.split(" on 20", 1)[0]
    return " ".join(raw.split()).strip()[:160] or "Untitled event"


def _response_text(response: Any) -> str:
    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            chunks.append(str(text))
    return "\n".join(chunks).strip() if chunks else str(response or "").strip()


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
    return max(0.0, min(1.0, confidence))
