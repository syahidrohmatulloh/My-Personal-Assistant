"""Google Calendar OAuth foundation.

This phase only connects/disconnects Google Calendar. It does not create real
calendar events yet. Event creation is intentionally left for a later explicit
confirmation phase.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.auth import get_current_user_id
from app.services.supabase_client import get_supabase, safe_execute


router = APIRouter(prefix="/calendar/oauth", tags=["calendar_oauth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_CALENDAR_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.events",
]


@router.get("/status")
async def google_calendar_oauth_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    row = _get_connection(user_id=user_id)

    if not row or row.get("status") != "active":
        return {
            "connected": False,
            "email": None,
            "expires_at": None,
            "scope": None,
        }

    return {
        "connected": True,
        "email": row.get("email"),
        "expires_at": row.get("expires_at"),
        "scope": row.get("scope"),
        "connected_at": row.get("connected_at"),
        "updated_at": row.get("updated_at"),
    }


@router.get("/start")
async def google_calendar_oauth_start(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    client_id, _client_secret, redirect_uri = _require_google_oauth_config()

    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=10)).isoformat()

    try:
        safe_execute(
            lambda sb: sb.table("google_oauth_states")
            .insert(
                {
                    "state": state,
                    "user_id": user_id,
                    "provider": "google_calendar",
                    "expires_at": expires_at,
                }
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create OAuth state: {exc}",
        ) from exc

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }

    return {
        "auth_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}",
        "expires_at": expires_at,
    }


@router.get("/callback")
async def google_calendar_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    frontend_url = _frontend_url()

    if error:
        return RedirectResponse(f"{frontend_url}/settings/security?calendar_error={error}")

    if not code or not state:
        return RedirectResponse(f"{frontend_url}/settings/security?calendar_error=missing_code_or_state")

    client_id, client_secret, redirect_uri = _require_google_oauth_config()

    state_row = _get_oauth_state(state)
    if not state_row:
        return RedirectResponse(f"{frontend_url}/settings/security?calendar_error=invalid_state")

    if state_row.get("used_at"):
        return RedirectResponse(f"{frontend_url}/settings/security?calendar_error=state_already_used")

    expires_at = _parse_dt(state_row.get("expires_at"))
    if not expires_at or expires_at < datetime.now(timezone.utc):
        return RedirectResponse(f"{frontend_url}/settings/security?calendar_error=state_expired")

    user_id = str(state_row.get("user_id") or "")
    if not user_id:
        return RedirectResponse(f"{frontend_url}/settings/security?calendar_error=missing_user")

    try:
        token_payload = await _exchange_code_for_token(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
        email = await _fetch_google_email(token_payload.get("access_token"))
        _store_connection(user_id=user_id, token_payload=token_payload, email=email)
        _mark_state_used(state)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(
            f"{frontend_url}/settings/security?calendar_error={urlencode({'m': str(exc)})}"
        )

    return RedirectResponse(f"{frontend_url}/settings/security?calendar=connected")


@router.post("/disconnect")
async def google_calendar_oauth_disconnect(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()

    try:
        safe_execute(
            lambda sb: sb.table("google_calendar_connections")
            .update(
                {
                    "status": "disconnected",
                    "access_token": None,
                    "refresh_token": None,
                    "disconnected_at": now,
                    "updated_at": now,
                }
            )
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect Google Calendar: {exc}",
        ) from exc

    return {"ok": True, "connected": False}


def _require_google_oauth_config() -> tuple[str, str, str]:
    missing = []
    if not settings.GOOGLE_CLIENT_ID:
        missing.append("GOOGLE_CLIENT_ID")
    if not settings.GOOGLE_CLIENT_SECRET:
        missing.append("GOOGLE_CLIENT_SECRET")
    if not settings.GOOGLE_CALENDAR_REDIRECT_URI:
        missing.append("GOOGLE_CALENDAR_REDIRECT_URI")

    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google Calendar OAuth is not configured. Missing: {', '.join(missing)}",
        )

    return (
        settings.GOOGLE_CLIENT_ID,
        settings.GOOGLE_CLIENT_SECRET,
        settings.GOOGLE_CALENDAR_REDIRECT_URI,
    )


def _frontend_url() -> str:
    if settings.APP_FRONTEND_URL:
        return settings.APP_FRONTEND_URL.rstrip("/")
    origins = settings.cors_origins
    if origins:
        return origins[0].rstrip("/")
    return "http://localhost:3000"


def _get_connection(*, user_id: str) -> dict[str, Any] | None:
    result = safe_execute(
        lambda sb: sb.table("google_calendar_connections")
        .select("status,email,scope,expires_at,connected_at,updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _get_oauth_state(state: str) -> dict[str, Any] | None:
    result = safe_execute(
        lambda sb: sb.table("google_oauth_states")
        .select("state,user_id,expires_at,used_at")
        .eq("state", state)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _mark_state_used(state: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    safe_execute(
        lambda sb: sb.table("google_oauth_states")
        .update({"used_at": now})
        .eq("state", state)
        .execute()
    )


async def _exchange_code_for_token(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Google token exchange failed: {response.text[:300]}")

    return response.json()


async def _fetch_google_email(access_token: str | None) -> str | None:
    if not access_token:
        return None

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code >= 400:
            return None
        data = response.json()
        return data.get("email")
    except Exception:
        return None


def _store_connection(*, user_id: str, token_payload: dict[str, Any], email: str | None) -> None:
    now = datetime.now(timezone.utc)
    expires_in = int(token_payload.get("expires_in") or 3600)
    expires_at = (now + timedelta(seconds=expires_in)).isoformat()

    payload = {
        "user_id": user_id,
        "status": "active",
        "email": email,
        "scope": token_payload.get("scope"),
        "token_type": token_payload.get("token_type"),
        "access_token": token_payload.get("access_token"),
        "refresh_token": token_payload.get("refresh_token"),
        "expires_at": expires_at,
        "connected_at": now.isoformat(),
        "disconnected_at": None,
        "updated_at": now.isoformat(),
    }

    safe_execute(
        lambda sb: sb.table("google_calendar_connections")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
