"""Style profile endpoints.

  POST   /style-profiles/analyze    body: {transcript, target_name?, profile_name?}
         -> {profile: StyleProfile, sample_count, source_type, suggested_name}
         The transcript is NOT persisted.

  POST   /style-profiles            body: {profile_name, source_type, extracted_style, sample_count, confidence?}
         -> created row
         Frontend flow: call /analyze, show preview, user clicks Save → call this.

  GET    /style-profiles            -> list of user's profiles (without sample transcripts; we never had them)
  PATCH  /style-profiles/{id}       body: {profile_name}
         -> rename
  DELETE /style-profiles/{id}       -> 204
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import style_extractor, style_parser
from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/style-profiles", tags=["style-profiles"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AnalyzeIn(BaseModel):
    transcript: str = Field(min_length=20, max_length=200_000)
    target_name: str | None = Field(default=None, max_length=80)
    # profile_name unused at analyze time — name is set on save


class AnalyzeOut(BaseModel):
    profile: dict
    sample_count: int
    source_type: str
    suggested_name: str


class CreateIn(BaseModel):
    profile_name: str = Field(min_length=1, max_length=80)
    source_type: str
    extracted_style: dict
    sample_count: int = 0
    confidence: float | None = None


class RenameIn(BaseModel):
    profile_name: str = Field(min_length=1, max_length=80)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(
    body: AnalyzeIn,
    user_id: str = Depends(get_current_user_id),
):
    source_type, parsed = style_parser.parse_transcript(body.transcript)

    profile, sample_count = await style_extractor.extract_style(
        source_type=source_type,
        parsed_lines=parsed,
        raw_text=body.transcript,
        target_sender=body.target_name,
    )

    if profile is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Could not extract a meaningful style profile from this transcript. "
            "Try pasting more messages from the target person.",
        )

    log.info(
        "style analyze: user=%s source=%s sample_count=%d display_name=%s",
        user_id[:8],
        source_type,
        sample_count,
        profile.display_name,
    )

    return AnalyzeOut(
        profile=profile.model_dump(),
        sample_count=sample_count,
        source_type=source_type,
        suggested_name=profile.display_name,
    )


@router.get("")
async def list_profiles(user_id: str = Depends(get_current_user_id)):
    supabase = get_supabase()
    result = (
        supabase.table("style_profiles")
        .select(
            "id, profile_name, source_type, extracted_style, sample_count, confidence, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: CreateIn,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    try:
        result = (
            supabase.table("style_profiles")
            .insert(
                {
                    "user_id": user_id,
                    "profile_name": body.profile_name.strip(),
                    "source_type": body.source_type,
                    "extracted_style": body.extracted_style,
                    "sample_count": body.sample_count,
                    "confidence": body.confidence,
                }
            )
            .execute()
        )
    except Exception as exc:
        # Most common: unique-name conflict.
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A profile with this name already exists. Pick a different name.",
            ) from exc
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to save profile"
        ) from exc

    if not result.data:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to save profile"
        )
    return result.data[0]


@router.patch("/{profile_id}")
async def rename_profile(
    profile_id: str,
    body: RenameIn,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    result = (
        supabase.table("style_profiles")
        .update(
            {
                "profile_name": body.profile_name.strip(),
                "updated_at": "now()",
            }
        )
        .eq("id", profile_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return result.data[0]


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    supabase.table("style_profiles").delete().eq("id", profile_id).eq(
        "user_id", user_id
    ).execute()
