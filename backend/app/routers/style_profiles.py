"""Style profile endpoints.

  POST   /style-profiles/preview-parse
         Parses transcript, returns sender list + recommendation. NO LLM call.
         Used by frontend to show "whose style?" picker.

  POST   /style-profiles/analyze
         Builds sample (begin/mid/end), calls Haiku, returns structured profile.
         Transcript NOT persisted.

  POST   /style-profiles            Save the previewed profile.
  GET    /style-profiles            List user's profiles.
  PATCH  /style-profiles/{id}       Rename.
  DELETE /style-profiles/{id}       Remove.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import style_extractor, style_parser
from app.services.style_extractor import MAX_UPLOAD_CHARS
from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/style-profiles", tags=["style-profiles"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PreviewParseIn(BaseModel):
    transcript: str = Field(min_length=1)
    # Optional caller-provided context for user detection. If omitted, the
    # endpoint loads user_identity.profile.name from the database.
    current_user_name: str | None = None
    current_user_email: str | None = None
    current_user_aliases: list[str] = Field(default_factory=list)


class PreviewParseSender(BaseModel):
    name: str
    count: int
    is_likely_user: bool
    recommended: bool


class PreviewParseOut(BaseModel):
    source_type: str
    message_count: int
    senders: list[PreviewParseSender]
    recommended_target_name: str | None
    too_long: bool
    warnings: list[str]


class AnalyzeIn(BaseModel):
    transcript: str = Field(min_length=20)
    target_name: str | None = Field(default=None, max_length=80)
    # User identity for fallback target picking. Same as preview-parse.
    current_user_name: str | None = None
    current_user_email: str | None = None
    current_user_aliases: list[str] = Field(default_factory=list)


class AnalyzeOut(BaseModel):
    profile: dict
    sample_count: int
    source_type: str
    suggested_name: str
    warnings: list[str]


class CreateIn(BaseModel):
    profile_name: str = Field(min_length=1, max_length=80)
    source_type: str
    extracted_style: dict
    sample_count: int = 0
    confidence: float | None = None


class RenameIn(BaseModel):
    profile_name: str = Field(min_length=1, max_length=80)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_user_context(
    user_id: str,
    *,
    override_name: str | None,
    override_email: str | None,
    override_aliases: list[str],
) -> tuple[str | None, str | None, list[str]]:
    """Resolve current user's name + email + aliases for sender detection.

    Order of precedence:
    1. Explicit caller overrides (frontend-supplied)
    2. user_identity.profile.name + user_identity.profile.email
    3. Empty fallback (sender detection will only catch "Me"/"Saya" labels)
    """
    name = override_name
    email = override_email
    aliases = list(override_aliases or [])

    if not name or not email:
        try:
            supabase = get_supabase()
            row = (
                supabase.table("user_identity")
                .select("profile")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if row and row.data and isinstance(row.data.get("profile"), dict):
                profile = row.data["profile"]
                if not name:
                    name = profile.get("name") or profile.get("preferred_name")
                if not email:
                    email = profile.get("email")
                nickname = profile.get("nickname")
                if nickname and nickname not in aliases:
                    aliases.append(nickname)
        except Exception as exc:
            log.warning("style: user_identity lookup failed: %s", exc)

    return name, email, aliases


def _check_size(transcript: str) -> None:
    if len(transcript) > MAX_UPLOAD_CHARS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Transcript too large ({len(transcript) // 1024} KB). "
            f"Maximum is {MAX_UPLOAD_CHARS // 1024} KB.",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/preview-parse", response_model=PreviewParseOut)
async def preview_parse(
    body: PreviewParseIn,
    user_id: str = Depends(get_current_user_id),
):
    """Parse transcript and identify senders. No LLM call, no storage."""
    _check_size(body.transcript)

    user_name, user_email, user_aliases = _load_user_context(
        user_id,
        override_name=body.current_user_name,
        override_email=body.current_user_email,
        override_aliases=body.current_user_aliases,
    )

    source_type, parsed = style_parser.parse_transcript(body.transcript)
    warnings: list[str] = []
    too_long = len(body.transcript) > 1_000_000  # advisory only — already passed hard cap

    if not parsed:
        # Plain text — no senders to enumerate.
        warnings.append(
            "Transcript format not recognized. Will be analyzed as plain text."
        )
        return PreviewParseOut(
            source_type=source_type,
            message_count=0,
            senders=[],
            recommended_target_name=None,
            too_long=too_long,
            warnings=warnings,
        )

    sender_dicts = style_parser.summarize_senders(
        parsed,
        user_name=user_name,
        user_aliases=user_aliases,
        user_email=user_email,
    )
    recommended = style_parser.recommend_target(sender_dicts)

    if recommended is None and sender_dicts:
        warnings.append(
            "All detected senders look like you. You can still analyze, but it "
            "will be your own writing sample, not someone else's style."
        )

    senders = [
        PreviewParseSender(
            name=s["name"],
            count=s["count"],
            is_likely_user=s["is_likely_user"],
            recommended=(s["name"] == recommended),
        )
        for s in sender_dicts
    ]

    return PreviewParseOut(
        source_type=source_type,
        message_count=len(parsed),
        senders=senders,
        recommended_target_name=recommended,
        too_long=too_long,
        warnings=warnings,
    )


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(
    body: AnalyzeIn,
    user_id: str = Depends(get_current_user_id),
):
    _check_size(body.transcript)

    user_name, user_email, user_aliases = _load_user_context(
        user_id,
        override_name=body.current_user_name,
        override_email=body.current_user_email,
        override_aliases=body.current_user_aliases,
    )

    source_type, parsed = style_parser.parse_transcript(body.transcript)

    profile, sample_count, warnings = await style_extractor.extract_style(
        source_type=source_type,
        parsed_lines=parsed,
        raw_text=body.transcript,
        target_sender=body.target_name,
        user_name=user_name,
        user_email=user_email,
        user_aliases=user_aliases,
    )

    if profile is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            (warnings[0] if warnings else "Could not extract a meaningful style profile."),
        )

    log.info(
        "style analyze: user=%s source=%s sample_count=%d target=%s display_name=%s",
        user_id[:8],
        source_type,
        sample_count,
        body.target_name or "(auto)",
        profile.display_name,
    )

    return AnalyzeOut(
        profile=profile.model_dump(),
        sample_count=sample_count,
        source_type=source_type,
        suggested_name=profile.display_name,
        warnings=warnings,
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
