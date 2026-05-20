"""AI Avatar Mode profile service.

This stores safe avatar display preferences only.
It deliberately does not clone faces, generate talking videos, or impersonate a real person.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)

_ALLOWED_ANIMATION_STYLES = {"calm", "subtle", "minimal"}
_DEFAULT_PROFILE: dict[str, Any] = {
    "image_url": None,
    "avatar_mode_enabled": False,
    "consent_confirmed": False,
    "animation_style": "calm",
}


def _clean_optional_text(value: Any, *, max_len: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected a text value")
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_len:
        raise ValueError(f"Text value is too long; max length is {max_len}")
    return cleaned


def _validate_image_url(value: Any) -> str | None:
    cleaned = _clean_optional_text(value, max_len=2048)
    if cleaned is None:
        return None

    parsed = urlparse(cleaned)
    is_http_asset = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    is_app_relative_asset = cleaned.startswith("/") and not cleaned.startswith("//")

    if not (is_http_asset or is_app_relative_asset):
        raise ValueError("image_url must be an http(s) URL or an app-relative asset path")
    return cleaned


def _validate_animation_style(value: Any) -> str:
    if value is None:
        return "calm"
    if not isinstance(value, str):
        raise ValueError("animation_style must be text")
    cleaned = value.strip().lower()
    if cleaned not in _ALLOWED_ANIMATION_STYLES:
        allowed = ", ".join(sorted(_ALLOWED_ANIMATION_STYLES))
        raise ValueError(f"animation_style must be one of: {allowed}")
    return cleaned


def _serialize(row: dict[str, Any] | None, user_id: str) -> dict[str, Any]:
    base = {**_DEFAULT_PROFILE, "user_id": user_id}
    if not row:
        return base
    return {**base, **row}


async def get_avatar_profile(user_id: str) -> dict[str, Any]:
    """Return the current user's avatar profile or a safe default profile."""
    try:
        result = (
            get_supabase()
            .table("assistant_avatar_profiles")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return _serialize(result.data if result else None, user_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("get_avatar_profile failed for user=%s: %s", user_id[:8], exc)
        return _serialize(None, user_id)


async def upsert_avatar_profile(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create/update a user's avatar profile with conservative validation."""
    current = await get_avatar_profile(user_id)

    next_enabled = bool(payload.get("avatar_mode_enabled", current.get("avatar_mode_enabled", False)))
    next_consent = bool(payload.get("consent_confirmed", current.get("consent_confirmed", False)))
    next_image_url = _validate_image_url(payload.get("image_url", current.get("image_url")))

    if next_enabled and not next_consent:
        raise ValueError("Avatar Mode requires explicit permission confirmation before it can be enabled")
    if next_enabled and not next_image_url:
        raise ValueError("Avatar Mode requires an avatar image before it can be enabled")

    data = {
        "user_id": user_id,
        "image_url": next_image_url,
        "avatar_mode_enabled": next_enabled,
        "consent_confirmed": next_consent,
        "animation_style": _validate_animation_style(payload.get("animation_style", current.get("animation_style"))),
    }

    result = (
        get_supabase()
        .table("assistant_avatar_profiles")
        .upsert(data, on_conflict="user_id")
        .execute()
    )
    if result and result.data:
        return _serialize(result.data[0], user_id)
    return _serialize(data, user_id)


async def delete_avatar_profile(user_id: str) -> None:
    """Delete the user's avatar profile/settings."""
    (
        get_supabase()
        .table("assistant_avatar_profiles")
        .delete()
        .eq("user_id", user_id)
        .execute()
    )
