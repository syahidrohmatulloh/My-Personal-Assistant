"""Companion mood state API — frontend-facing endpoints.

This router exists for frontend backwards compatibility. Internally it
delegates to the `companion` service (new architecture) which reads/writes
the singular `companion_mood_state` table.

API contract unchanged from previous version:
  - GET  /companion-mood?conversation_id=...  → returns {global, conversation, effective}
  - PUT  /companion-mood                       → upsert mood state

Changes vs previous implementation:
  - No longer reads/writes `companion_mood_states` (plural, dropped in Zip 1)
  - Conversation-scoped state requests collapse to global. Per audit decision:
    one user has ONE mood at a time, not different moods per conversation tab.
  - Mood ignored entirely if user's companion_settings is not partner+dynamic.
    The service layer enforces this — PUT becomes a no-op for those users.
  - `scope` and `conversation_id` fields preserved in request/response shape
    so frontend doesn't need to change.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import companion

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
    mood_scores: dict[str, int] = Field(default_factory=dict)

    expires_at: str | None = None


def _default_mood_scores() -> dict[str, int]:
    return {
        "calm": 2,
        "affectionate": 0,
        "romantic": 0,
        "playful": 0,
        "jealous_playful": 0,
        "clingy": 0,
        "annoyed": 0,
        "hurt": 0,
        "concerned": 0,
        "focused": 0,
        "reassured": 0,
        "withdrawn_soft": 0,
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_state(user_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    """Cold-start payload for frontend when no real state exists.

    Shape preserved from previous implementation so frontend deserialization
    doesn't break.
    """
    now = _now()
    return {
        "id": None,
        "user_id": user_id,
        "conversation_id": conversation_id,
        # Echo whatever scope the client asked for, even though backend
        # collapses to global internally.
        "scope": "conversation" if conversation_id else "global",
        "mood": "calm",
        "intensity": 1,
        "mood_scores": _default_mood_scores(),
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


def _new_table_row_to_legacy_shape(row: dict[str, Any] | None, user_id: str) -> dict[str, Any] | None:
    """Convert companion_mood_state (new singular table) row to legacy shape.

    The new table has the same columns minus `scope` and `conversation_id`,
    so we inject those for frontend compatibility.
    """
    if not row:
        return None
    out = dict(row)
    out["scope"] = "global"
    out["conversation_id"] = None
    return out


@router.get("")
async def get_companion_mood(
    conversation_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """Frontend-compat read endpoint.

    Always returns the same global mood (single source of truth in the new
    architecture). The `conversation` key is None unless we choose to mirror
    the global state under it — we don't, because frontend logic that prefers
    conversation over global would then double-render.

    For users not on partner+dynamic, returns the cold-start default and the
    frontend's UI will look the same as before mood-realism was disabled.
    """
    current_mood = await companion.get_current_mood(user_id)
    # current_mood is None when companion_mode != partner OR realism != dynamic.
    # Frontend already deals with default state, just give it one.
    global_state = _new_table_row_to_legacy_shape(current_mood, user_id)

    if not global_state:
        global_state = _default_state(user_id)

    return {
        "global": global_state,
        # Conversation scope is intentionally None — no per-conversation moods anymore.
        "conversation": None,
        "effective": global_state,
    }


@router.put("")
async def put_companion_mood(
    body: CompanionMoodIn,
    user_id: str = Depends(get_current_user_id),
):
    """Frontend-compat write endpoint.

    Delegates to `companion.update_mood`. Silently no-ops if user is not on
    partner+dynamic — that's per service-layer gating, not a router decision.
    In that case we return the in-memory payload so the frontend's optimistic
    update doesn't fail, but nothing is persisted.

    Note: `scope` and `conversation_id` are accepted but ignored — mood is
    always global now. We log nothing about this to keep frontend logs clean.
    """
    updated = await companion.update_mood(
        user_id,
        mood=body.mood,
        intensity=body.intensity,
        reason=body.reason,
        last_trigger=body.last_trigger,
        source=body.source,
        valence=body.valence,
        arousal=body.arousal,
        attachment=body.attachment,
        trust=body.trust,
        insecurity=body.insecurity,
        warmth=body.warmth,
        playfulness=body.playfulness,
        mood_scores=body.mood_scores or _default_mood_scores(),
    )

    if updated:
        return _new_table_row_to_legacy_shape(updated, user_id)

    # Service returned None = mood not enabled for this user. Return what the
    # client sent so its optimistic UI doesn't reject the response.
    now = _now()
    return {
        "id": None,
        "user_id": user_id,
        "conversation_id": body.conversation_id,
        "scope": "global",  # always global now
        "mood": body.mood,
        "intensity": body.intensity,
        "mood_scores": body.mood_scores or _default_mood_scores(),
        "valence": body.valence,
        "arousal": body.arousal,
        "attachment": body.attachment,
        "trust": body.trust,
        "insecurity": body.insecurity,
        "warmth": body.warmth,
        "playfulness": body.playfulness,
        "reason": body.reason,
        "last_trigger": body.last_trigger,
        "source": "noop_mood_disabled",
        "version": 0,
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
