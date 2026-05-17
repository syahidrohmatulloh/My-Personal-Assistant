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
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.core.auth import get_current_user_id
from app.services import style_extractor, style_parser
from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(prefix="/style-profiles", tags=["style-profiles"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AnalyzeIn(BaseModel):
    transcript: str = Field(min_length=20, max_length=settings.STYLE_ANALYSIS_UPLOAD_MAX_CHARS)
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


class PreferredRewriteIn(BaseModel):
    bad: str = Field(min_length=1, max_length=160)
    better: str = Field(min_length=1, max_length=160)


class CalibrationIn(BaseModel):
    positive_examples: list[str] = Field(default_factory=list, max_length=20)
    negative_examples: list[str] = Field(default_factory=list, max_length=20)
    preferred_rewrites: list[PreferredRewriteIn] = Field(default_factory=list, max_length=20)
    banned_phrases: list[str] = Field(default_factory=list, max_length=30)
    notes: list[str] = Field(default_factory=list, max_length=20)
    merge: bool = True




class PreviewParseIn(BaseModel):
    transcript: str = Field(min_length=1, max_length=settings.STYLE_ANALYSIS_UPLOAD_MAX_CHARS)
    current_user_name: str | None = Field(default=None, max_length=120)
    current_user_email: str | None = Field(default=None, max_length=160)
    current_user_aliases: list[str] = Field(default_factory=list, max_length=20)


class DetectedSenderOut(BaseModel):
    name: str
    count: int
    is_likely_user: bool = False
    recommended: bool = False


class PreviewParseOut(BaseModel):
    source_type: str
    message_count: int
    senders: list[DetectedSenderOut]
    recommended_target_name: str | None = None
    too_long: bool = False
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------




@router.post("/preview-parse", response_model=PreviewParseOut)
async def preview_parse(
    body: PreviewParseIn,
    user_id: str = Depends(get_current_user_id),
):
    """Preview transcript parsing without calling the LLM or storing raw transcript."""
    warnings: list[str] = []

    transcript_len = len(body.transcript or "")
    too_long = transcript_len > settings.STYLE_ANALYSIS_UPLOAD_MAX_CHARS

    source_type, parsed = style_parser.parse_transcript(body.transcript)

    if source_type == "plain" or not parsed:
        warnings.append("Format not detected; analyzing as plain text.")
        return PreviewParseOut(
            source_type=source_type,
            message_count=0,
            senders=[],
            recommended_target_name=None,
            too_long=too_long,
            warnings=warnings,
        )

    counts = Counter(sender for sender, _ in parsed)

    aliases = _build_user_aliases(
        current_user_name=body.current_user_name,
        current_user_email=body.current_user_email,
        current_user_aliases=body.current_user_aliases,
    )

    sender_rows = []
    recommended_name = None

    sorted_senders = sorted(counts.items(), key=lambda item: item[1], reverse=True)

    for sender, count in sorted_senders:
        likely_user = _is_likely_user_sender(sender, aliases)
        sender_rows.append(
            {
                "name": sender,
                "count": count,
                "is_likely_user": likely_user,
                "recommended": False,
            }
        )

    for row in sender_rows:
        if not row["is_likely_user"]:
            row["recommended"] = True
            recommended_name = row["name"]
            break

    if recommended_name is None and sender_rows:
        warnings.append(
            "Only likely-user sender(s) detected. Select a speaker manually if needed."
        )

    if transcript_len > 500_000:
        warnings.append(
            "Large transcript detected. The app will sample representative messages for analysis."
        )

    log.info(
        "style preview-parse: user=%s chars=%d source=%s messages=%d senders=%d recommended=%s",
        user_id[:8],
        transcript_len,
        source_type,
        len(parsed),
        len(sender_rows),
        recommended_name,
    )

    return PreviewParseOut(
        source_type=source_type,
        message_count=len(parsed),
        senders=[DetectedSenderOut(**row) for row in sender_rows],
        recommended_target_name=recommended_name,
        too_long=too_long,
        warnings=warnings,
    )


def _normalize_sender_name(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9@\.\s_-]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _build_user_aliases(
    current_user_name: str | None,
    current_user_email: str | None,
    current_user_aliases: list[str],
) -> set[str]:
    aliases: set[str] = set()

    for raw in [current_user_name, current_user_email, *(current_user_aliases or [])]:
        norm = _normalize_sender_name(raw)
        if norm:
            aliases.add(norm)

        if raw and "@" in raw:
            local = raw.split("@", 1)[0]
            local_norm = _normalize_sender_name(local)
            if local_norm:
                aliases.add(local_norm)

    if current_user_name:
        parts = [_normalize_sender_name(part) for part in current_user_name.split()]
        for part in parts:
            if len(part) >= 3:
                aliases.add(part)

    aliases.update({"me", "saya", "aku", "gue", "gua", "gw"})
    return aliases


def _is_likely_user_sender(sender: str, aliases: set[str]) -> bool:
    norm = _normalize_sender_name(sender)
    if not norm:
        return False

    if norm in aliases:
        return True

    compact = norm.replace(" ", "")
    for alias in aliases:
        alias_compact = alias.replace(" ", "")
        if not alias_compact:
            continue

        if compact == alias_compact:
            return True

        if len(alias_compact) >= 5 and (
            alias_compact in compact or compact in alias_compact
        ):
            return True

    return False


@router.post("/analyze", response_model=AnalyzeOut)
async def analyze(
    body: AnalyzeIn,
    user_id: str = Depends(get_current_user_id),
):
    source_type, parsed = style_parser.parse_transcript(body.transcript)

    log.info(
        "style analyze request: user=%s chars=%d source=%s parsed_lines=%d sample_cap=%d",
        user_id[:8],
        len(body.transcript),
        source_type,
        len(parsed),
        settings.STYLE_ANALYSIS_SAMPLE_CHARS,
    )

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


@router.patch("/{profile_id}/calibration")
async def update_profile_calibration(
    profile_id: str,
    body: CalibrationIn,
    user_id: str = Depends(get_current_user_id),
):
    """Add or replace human calibration feedback for a style profile.

    Stored inside extracted_style.style_calibration to avoid a DB migration.
    This is explicit user feedback (accurate/miss/rewrite), not raw transcript.
    """
    supabase = get_supabase()
    current = (
        supabase.table("style_profiles")
        .select("id, extracted_style")
        .eq("id", profile_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not current or not current.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")

    extracted_style = current.data.get("extracted_style") or {}
    existing = extracted_style.get("style_calibration") or {}
    incoming = body.model_dump(exclude={"merge"})

    if body.merge:
        merged = _merge_calibration(existing, incoming)
    else:
        merged = incoming

    extracted_style["style_calibration"] = merged
    result = (
        supabase.table("style_profiles")
        .update({"extracted_style": extracted_style, "updated_at": "now()"})
        .eq("id", profile_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update calibration")
    return result.data[0]


def _merge_calibration(existing: dict, incoming: dict) -> dict:
    def merge_list(key: str, limit: int) -> list:
        out = []
        for item in (existing.get(key) or []) + (incoming.get(key) or []):
            if isinstance(item, str):
                cleaned = " ".join(item.strip().split())[:180]
                if cleaned and cleaned not in out:
                    out.append(cleaned)
            if len(out) >= limit:
                break
        return out

    def merge_rewrites() -> list[dict]:
        out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in (existing.get("preferred_rewrites") or []) + (incoming.get("preferred_rewrites") or []):
            if not isinstance(item, dict):
                continue
            bad = " ".join(str(item.get("bad") or "").strip().split())[:160]
            better = " ".join(str(item.get("better") or "").strip().split())[:160]
            if not bad or not better:
                continue
            key = (bad, better)
            if key in seen:
                continue
            seen.add(key)
            out.append({"bad": bad, "better": better})
            if len(out) >= 20:
                break
        return out

    return {
        "positive_examples": merge_list("positive_examples", 20),
        "negative_examples": merge_list("negative_examples", 20),
        "preferred_rewrites": merge_rewrites(),
        "banned_phrases": merge_list("banned_phrases", 30),
        "notes": merge_list("notes", 20),
    }


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    supabase.table("style_profiles").delete().eq("id", profile_id).eq(
        "user_id", user_id
    ).execute()
