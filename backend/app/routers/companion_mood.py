"""Companion mood state API.

This stores Aliyya's current companion mood as an active state with expiry.
It does not write to memories, messages, journal, goals, or identity.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services.supabase_client import get_supabase

router = APIRouter(prefix="/companion-mood", tags=["companion_mood"])


class CompanionMoodIn(BaseModel):
    conversation_id: str | None = None
    scope: Literal["global", "conversation"] = "global"

    mood: str = "calm"
    intensity: int = Field(default=1, ge=1, le=10)

    valence: float = 0.35
    arousal: float = 0.2
    attachment: float = 0.45
    trust: float = 0.6
    insecurity: float = 0.12
    warmth: float = 0.65
    playfulness: float = 0.35

    reason: str = "default calm companion state"
    last_trigger: str = "default"
    source: str = "frontend"

    expires_at: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_state(user_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    now = _now()
    return {
        "id": None,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "scope": "conversation" if conversation_id else "global",
        "mood": "calm",
        "intensity": 1,
        "valence": 0.35,
        "arousal": 0.2,
        "attachment": 0.45,
        "trust": 0.6,
        "insecurity": 0.12,
        "warmth": 0.65,
        "playfulness": 0.35,
        "reason": "no previous companion mood state",
        "last_trigger": "cold_start",
        "source": "cold_start_default",
        "version": 0,
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _normalize_scope(scope: str, conversation_id: str | None) -> str:
    if scope == "conversation" or conversation_id:
        return "conversation"
    return "global"


def _fetch_state(supabase, user_id: str, scope: str, conversation_id: str | None):
    q = (
        supabase.table("companion_mood_states")
        .select("*")
        .eq("user_id", user_id)
        .eq("scope", scope)
        .limit(1)
    )

    if scope == "conversation" and conversation_id:
        q = q.eq("conversation_id", conversation_id)
    else:
        q = q.is_("conversation_id", "null")

    result = q.execute()
    return result.data[0] if result.data else None


@router.get("")
async def get_companion_mood(
    conversation_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    global_state = _fetch_state(supabase, user_id, "global", None)
    conversation_state = (
        _fetch_state(supabase, user_id, "conversation", conversation_id)
        if conversation_id
        else None
    )

    effective = conversation_state or global_state or _default_state(user_id, conversation_id)

    return {
        "global": global_state,
        "conversation": conversation_state,
        "effective": effective,
    }


@router.put("")
async def put_companion_mood(
    body: CompanionMoodIn,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    scope = _normalize_scope(body.scope, body.conversation_id)
    conversation_id = body.conversation_id if scope == "conversation" else None
    existing = _fetch_state(supabase, user_id, scope, conversation_id)

    now = _now()
    expires_at = body.expires_at or (now + timedelta(minutes=30)).isoformat()

    row = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "scope": scope,
        "mood": body.mood,
        "intensity": body.intensity,
        "valence": body.valence,
        "arousal": body.arousal,
        "attachment": body.attachment,
        "trust": body.trust,
        "insecurity": body.insecurity,
        "warmth": body.warmth,
        "playfulness": body.playfulness,
        "reason": body.reason,
        "last_trigger": body.last_trigger,
        "source": body.source,
        "expires_at": expires_at,
        "updated_at": now.isoformat(),
        "version": (existing.get("version", 0) + 1) if existing else 1,
    }

    if existing:
        result = (
            supabase.table("companion_mood_states")
            .update(row)
            .eq("id", existing["id"])
            .eq("user_id", user_id)
            .execute()
        )
    else:
        result = supabase.table("companion_mood_states").insert(row).execute()

    return result.data[0] if result.data else row
