"""Companion settings endpoints.

  GET   /companion/settings   — read current user's companion settings
  PATCH /companion/settings   — update fields with escalation rule enforcement

Mood state is not exposed here (it's internal to chat pipeline). The user
controls *whether* mood is active via mood_realism toggle, not the mood
content itself.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import companion

log = logging.getLogger(__name__)
router = APIRouter(prefix="/companion", tags=["companion"])


class CompanionSettingsOut(BaseModel):
    companion_mode: str
    assistant_name: str
    mood_realism: str
    repair_gate_enabled: bool
    assistant_mode: str


class CompanionSettingsPatchIn(BaseModel):
    """All fields optional. Only provided fields are updated.

    Validation (escalation ladder) happens in the service layer.
    """

    companion_mode: str | None = Field(
        default=None,
        pattern="^(professional|friendly|affectionate|partner)$",
    )
    assistant_name: str | None = Field(default=None, min_length=1, max_length=32)
    mood_realism: str | None = Field(
        default=None,
        pattern="^(stable|dynamic)$",
    )
    repair_gate_enabled: bool | None = None
    assistant_mode: str | None = Field(
        default=None,
        pattern="^(life_companion|chief_of_staff)$",
    )


def _to_response(row: dict) -> CompanionSettingsOut:
    preferences = row.get("preferences") or {}
    assistant_mode = (
        preferences.get("assistant_mode")
        if isinstance(preferences, dict)
        else None
    )
    return CompanionSettingsOut(
        companion_mode=row.get("companion_mode") or "professional",
        assistant_name=row.get("assistant_name") or "Assistant",
        mood_realism=row.get("mood_realism") or "stable",
        repair_gate_enabled=bool(row.get("repair_gate_enabled")),
        assistant_mode=assistant_mode or "life_companion",
    )


@router.get("/settings", response_model=CompanionSettingsOut)
async def get_settings(user_id: str = Depends(get_current_user_id)):
    row = await companion.get_settings(user_id)
    return _to_response(row)


@router.patch("/settings", response_model=CompanionSettingsOut)
async def patch_settings(
    body: CompanionSettingsPatchIn,
    user_id: str = Depends(get_current_user_id),
):
    try:
        updated = await companion.update_settings(
            user_id,
            companion_mode=body.companion_mode,  # type: ignore[arg-type]
            assistant_name=body.assistant_name,
            mood_realism=body.mood_realism,  # type: ignore[arg-type]
            repair_gate_enabled=body.repair_gate_enabled,
            preferences=(
                {"assistant_mode": body.assistant_mode}
                if body.assistant_mode is not None
                else None
            ),
        )
    except ValueError as exc:
        log.warning(
            "companion settings: invalid update user=%s error=%s",
            user_id[:8],
            str(exc)[:160],
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invalid companion settings update",
        ) from exc
    except Exception as exc:
        log.exception("companion settings: update failed user=%s", user_id[:8])
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Failed to update settings",
        ) from exc

    return _to_response(updated)
