"""Companion settings and mood state service.

Replaces the orphan `user_state.py` and consolidates companion_mood_states
into a single-row-per-user model.

Architecture:
- `companion_settings` holds stable user preferences (mode, name, toggles)
- `companion_mood_state` holds the AI's current dynamic mood

Permission ladder enforced here (not in DB) so existing rows survive migration:
  professional / friendly / affectionate  → mood ignored
  partner + mood_realism='dynamic'        → mood drives behavior
  partner + dynamic + repair_gate_enabled → ngambek allowed

Mood state has a 30-minute TTL. Reads transparently reset to calm if expired.
Writes refresh the TTL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CompanionMode = Literal["professional", "friendly", "affectionate", "partner"]
MoodRealism = Literal["stable", "dynamic"]


# Default settings row used when no DB record exists yet. The shape matches
# what get_settings returns. Mirrors DB defaults.
_DEFAULT_SETTINGS = {
    "companion_mode": "professional",
    "assistant_name": "Assistant",
    "mood_realism": "stable",
    "repair_gate_enabled": False,
    "preferences": {},
}

# Default mood used when no row exists OR when the row has expired.
# Mirrors DB defaults in schema.
_DEFAULT_MOOD = {
    "mood": "calm",
    "intensity": 1,
    "valence": 0.35,
    "arousal": 0.2,
    "attachment": 0.45,
    "trust": 0.6,
    "insecurity": 0.12,
    "warmth": 0.65,
    "playfulness": 0.35,
    "mood_scores": {
        "calm": 2,
        "hurt": 0,
        "clingy": 0,
        "annoyed": 0,
        "focused": 0,
        "playful": 0,
        "romantic": 0,
        "concerned": 0,
        "reassured": 0,
        "affectionate": 0,
        "withdrawn_soft": 0,
        "jealous_playful": 0,
    },
    "reason": "",
    "last_trigger": "",
    "source": "cold_start_default",
    "version": 1,
}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


async def get_settings(user_id: str) -> dict[str, Any]:
    """Return the user's companion settings.

    Always returns a dict — never None. If no row exists, returns defaults
    and does NOT auto-create (idempotent reads, write happens on update).
    """
    try:
        result = safe_execute(
            lambda sb: sb.table("companion_settings")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data
    except Exception as exc:
        log.warning("get_settings failed for user=%s: %s", user_id[:8], exc)

    return {**_DEFAULT_SETTINGS, "user_id": user_id}


async def update_settings(
    user_id: str,
    *,
    companion_mode: CompanionMode | None = None,
    assistant_name: str | None = None,
    assistant_mode: str | None = None,
    mood_realism: MoodRealism | None = None,
    repair_gate_enabled: bool | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update one or more settings fields. Enforces escalation ladder.

    Raises ValueError if a setting violates the escalation rules:
      - mood_realism='dynamic' requires companion_mode='partner'
      - repair_gate_enabled=True requires mood_realism='dynamic'

    For the check we use the resulting state (current row + requested update),
    not just the request — so user can set partner+dynamic+repair_gate in one
    upsert without ordering issues.
    """
    # Load current state to compute resulting state.
    current = await get_settings(user_id)

    next_mode = companion_mode if companion_mode is not None else current.get("companion_mode", "professional")
    next_realism = mood_realism if mood_realism is not None else current.get("mood_realism", "stable")
    next_repair = (
        repair_gate_enabled
        if repair_gate_enabled is not None
        else current.get("repair_gate_enabled", False)
    )

    # Enforce ladder.
    if next_realism == "dynamic" and next_mode != "partner":
        raise ValueError(
            "mood_realism='dynamic' requires companion_mode='partner'. "
            f"You requested mode={next_mode!r}."
        )
    if next_repair and next_realism != "dynamic":
        raise ValueError(
            "repair_gate_enabled=True requires mood_realism='dynamic'."
        )

    if assistant_mode is not None:
        normalised_assistant_mode = str(assistant_mode).lower().strip()
        if normalised_assistant_mode not in {"life_companion", "chief_of_staff"}:
            raise ValueError(f"Invalid assistant_mode={assistant_mode!r}.")

        current_preferences = current.get("preferences")
        merged_preferences: dict[str, Any] = (
            dict(current_preferences) if isinstance(current_preferences, dict) else {}
        )
        if preferences:
            merged_preferences.update(preferences)
        merged_preferences["assistant_mode"] = normalised_assistant_mode
        preferences = merged_preferences

    # Build upsert payload — only set fields that were explicitly provided.
    # This way unset fields keep their existing values via the on-conflict behavior.
    payload: dict[str, Any] = {"user_id": user_id, "updated_at": "now()"}
    if companion_mode is not None:
        payload["companion_mode"] = companion_mode
    if assistant_name is not None:
        payload["assistant_name"] = assistant_name.strip() or "Assistant"
    if mood_realism is not None:
        payload["mood_realism"] = mood_realism
    if repair_gate_enabled is not None:
        payload["repair_gate_enabled"] = repair_gate_enabled
    if preferences is not None:
        # Merge with existing preferences (don't blindly overwrite).
        merged = {**(current.get("preferences") or {}), **preferences}
        payload["preferences"] = merged

    try:
        result = safe_execute(
            lambda sb: sb.table("companion_settings")
            .upsert(payload, on_conflict="user_id")
            .execute()
        )
        if result and result.data:
            return result.data[0]
    except Exception as exc:
        log.error("update_settings failed for user=%s: %s", user_id[:8], exc)
        raise

    # Should be unreachable, but return a sane fallback.
    return {**current, **{k: v for k, v in payload.items() if k != "updated_at"}}


# ---------------------------------------------------------------------------
# Mood state
# ---------------------------------------------------------------------------


async def get_current_mood(user_id: str) -> dict[str, Any] | None:
    """Return the current mood state, or None if mood is not applicable.

    Returns None when:
      - companion_mode != 'partner' (mood not in use)
      - mood_realism == 'stable' (mood not in use)

    Returns default calm mood when:
      - settings are partner+dynamic but no mood row exists yet
      - existing mood row has expired (past TTL)

    Returns actual stored mood otherwise.
    """
    settings = await get_settings(user_id)
    if settings.get("companion_mode") != "partner":
        return None
    if settings.get("mood_realism") != "dynamic":
        return None

    try:
        result = safe_execute(
            lambda sb: sb.table("companion_mood_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        log.warning("get_current_mood read failed for user=%s: %s", user_id[:8], exc)
        return {**_DEFAULT_MOOD, "user_id": user_id}

    if not result or not result.data:
        return {**_DEFAULT_MOOD, "user_id": user_id}

    row = result.data

    # TTL check — if expired, treat as calm. Don't auto-reset DB; let the
    # next mood update overwrite.
    expires_at = row.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                return {**_DEFAULT_MOOD, "user_id": user_id, "source": "ttl_expired"}
        except Exception:
            pass  # malformed timestamp — return row as-is rather than crash

    return row


async def update_mood(
    user_id: str,
    *,
    mood: str,
    intensity: int,
    reason: str = "",
    last_trigger: str = "",
    source: str = "chat_inference",
    valence: float | None = None,
    arousal: float | None = None,
    attachment: float | None = None,
    trust: float | None = None,
    insecurity: float | None = None,
    warmth: float | None = None,
    playfulness: float | None = None,
    mood_scores: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    """Update mood state. No-op if mood not applicable per settings.

    Returns the new state, or None if mood was not applicable.

    Refreshes TTL by 30 minutes from now.
    """
    settings = await get_settings(user_id)
    if (
        settings.get("companion_mode") != "partner"
        or settings.get("mood_realism") != "dynamic"
    ):
        return None  # silently no-op when mood disabled

    intensity = max(0, min(10, int(intensity)))

    payload: dict[str, Any] = {
        "user_id": user_id,
        "mood": mood,
        "intensity": intensity,
        "reason": reason[:500],
        "last_trigger": last_trigger[:200],
        "source": source[:100],
        "expires_at": "now() + interval '30 minutes'",
        "updated_at": "now()",
    }
    # Only include numeric axes that caller provided. Otherwise keep existing DB values.
    if valence is not None:
        payload["valence"] = valence
    if arousal is not None:
        payload["arousal"] = arousal
    if attachment is not None:
        payload["attachment"] = attachment
    if trust is not None:
        payload["trust"] = trust
    if insecurity is not None:
        payload["insecurity"] = insecurity
    if warmth is not None:
        payload["warmth"] = warmth
    if playfulness is not None:
        payload["playfulness"] = playfulness
    if mood_scores is not None:
        payload["mood_scores"] = mood_scores

    try:
        # Supabase upsert with string expressions like "now() + interval..." fails
        # because the python client wraps everything as a literal value. Use two
        # separate operations: upsert basic fields, then patch expires_at via raw RPC.
        # Simplest: use Python-side timestamp instead of SQL expression.
        from datetime import timedelta

        now_utc = datetime.now(timezone.utc)
        payload["expires_at"] = (now_utc + timedelta(minutes=30)).isoformat()
        payload["updated_at"] = now_utc.isoformat()

        # Bump version on every update for audit.
        current = await get_current_mood(user_id)
        if current:
            payload["version"] = (current.get("version") or 1) + 1

        result = safe_execute(
            lambda sb: sb.table("companion_mood_state")
            .upsert(payload, on_conflict="user_id")
            .execute()
        )
        if result and result.data:
            return result.data[0]
    except Exception as exc:
        log.error("update_mood failed for user=%s: %s", user_id[:8], exc)

    return None


# ---------------------------------------------------------------------------
# Convenience for chat router (used in Zip 2)
# ---------------------------------------------------------------------------


def is_mood_active(settings: dict[str, Any]) -> bool:
    """Quick check: does this user have dynamic mood enabled?"""
    return (
        settings.get("companion_mode") == "partner"
        and settings.get("mood_realism") == "dynamic"
    )


def is_repair_gate_active(settings: dict[str, Any]) -> bool:
    """Quick check: is the repair gate enabled (subsumes is_mood_active)?"""
    return is_mood_active(settings) and bool(settings.get("repair_gate_enabled"))
