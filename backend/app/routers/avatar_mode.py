"""AI Avatar Mode endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import avatar_mode

log = logging.getLogger(__name__)
router = APIRouter(prefix="/avatar-mode", tags=["avatar-mode"])


class AvatarProfileOut(BaseModel):
    id: str | None = None
    user_id: str | None = None
    image_url: str | None = None
    avatar_mode_enabled: bool = False
    consent_confirmed: bool = False
    animation_style: str = "calm"
    created_at: str | None = None
    updated_at: str | None = None


class AvatarProfileIn(BaseModel):
    image_url: str | None = Field(default=None, max_length=2048)
    avatar_mode_enabled: bool | None = None
    consent_confirmed: bool | None = None
    animation_style: str | None = Field(default=None, pattern="^(calm|subtle|minimal)$")


@router.get("/profile", response_model=AvatarProfileOut)
async def get_profile(user_id: str = Depends(get_current_user_id)):
    return await avatar_mode.get_avatar_profile(user_id)


@router.put("/profile", response_model=AvatarProfileOut)
async def put_profile(
    body: AvatarProfileIn,
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await avatar_mode.upsert_avatar_profile(user_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.error("avatar profile update failed: %s", exc, exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Failed to update avatar profile",
        ) from exc


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(user_id: str = Depends(get_current_user_id)):
    await avatar_mode.delete_avatar_profile(user_id)
    return None
