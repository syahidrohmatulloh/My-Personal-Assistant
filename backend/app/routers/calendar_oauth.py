"""Google Calendar OAuth foundation.

This phase only connects/disconnects Google Calendar. It does not create real
calendar events yet. Event creation is intentionally left for a later explicit
confirmation phase.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.auth import get_current_user_id
from app.services.supabase_client import get_supabase, safe_execute
from app.services.token_crypto import (
    TokenCryptoError,
    decrypt_token,
    encrypt_token,
    is_encrypted_token,
    require_token_encryption_configured,
)


log = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar/oauth", tags=["calendar_oauth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

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
        log.exception("calendar oauth: failed to create state user=%s", user_id[:8])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start Google Calendar connection",
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
        log.warning("calendar oauth: provider returned error=%s", str(error)[:120])
        return RedirectResponse(f"{frontend_url}/settings/security?calendar_error=oauth_denied")

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
    except Exception:  # noqa: BLE001
        log.exception("calendar oauth: callback failed state=%s", str(state)[:12])
        return RedirectResponse(
            f"{frontend_url}/settings/security?calendar_error=connect_failed"
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
        log.exception("calendar oauth: disconnect failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect Google Calendar",
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
        log.warning(
            "calendar oauth: missing config keys=%s",
            ",".join(missing),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar OAuth is not configured",
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


def _google_oauth_error_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if isinstance(error, dict):
        error = error.get("status") or error.get("message")

    cleaned = str(error or "").strip()
    return cleaned[:80] or None


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
        log.warning(
            "calendar oauth: token exchange failed status=%s error=%s",
            response.status_code,
            _google_oauth_error_code(response),
        )
        raise RuntimeError("Google token exchange failed")

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

    encrypted_access_token = _encrypt_google_token(
        token_payload.get("access_token")
    )
    if not encrypted_access_token:
        raise RuntimeError("Google token exchange returned no access token")

    payload = {
        "user_id": user_id,
        "status": "active",
        "email": email,
        "scope": token_payload.get("scope"),
        "token_type": token_payload.get("token_type"),
        "access_token": encrypted_access_token,
        "expires_at": expires_at,
        "connected_at": now.isoformat(),
        "disconnected_at": None,
        "updated_at": now.isoformat(),
    }

    refresh_token = _encrypt_google_token(
        token_payload.get("refresh_token")
    )
    if refresh_token:
        payload["refresh_token"] = refresh_token

    safe_execute(
        lambda sb: sb.table("google_calendar_connections")
        .upsert(payload, on_conflict="user_id")
        .execute()
    )


def _encrypt_google_token(value: Any) -> str | None:
    try:
        return encrypt_token(
            str(value).strip() if value is not None else None
        )
    except TokenCryptoError as exc:
        log.error(
            "calendar oauth: token encryption failed error_type=%s",
            type(exc).__name__,
        )
        raise RuntimeError(
            "Google Calendar token encryption is unavailable"
        ) from exc


def _migrate_legacy_tokens(
    *,
    user_id: str,
    raw_access_token: str,
    raw_refresh_token: str,
    access_token: str,
    refresh_token: str,
) -> None:
    updates: dict[str, Any] = {}

    if raw_access_token and not is_encrypted_token(raw_access_token):
        updates["access_token"] = _encrypt_google_token(access_token)

    if raw_refresh_token and not is_encrypted_token(raw_refresh_token):
        updates["refresh_token"] = _encrypt_google_token(refresh_token)

    if not updates:
        return

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        safe_execute(
            lambda sb: sb.table("google_calendar_connections")
            .update(updates)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        log.error(
            "calendar oauth: legacy token migration failed user=%s error_type=%s",
            user_id[:8],
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to secure stored Google Calendar credentials",
        ) from exc


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


async def get_active_google_calendar_access_token(*, user_id: str) -> str:
    """Return a valid Google Calendar access token, refreshing if needed.

    Raises HTTPException when not connected or refresh is impossible.
    """
    row = _get_token_connection(user_id=user_id)
    if not row or row.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar is not connected",
        )

    raw_access_token = str(row.get("access_token") or "").strip()
    raw_refresh_token = str(row.get("refresh_token") or "").strip()

    try:
        require_token_encryption_configured()
        access_token = str(
            decrypt_token(raw_access_token) or ""
        ).strip()
        refresh_token = str(
            decrypt_token(raw_refresh_token) or ""
        ).strip()
    except TokenCryptoError as exc:
        log.error(
            "calendar oauth: token decryption failed user=%s error_type=%s",
            user_id[:8],
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Calendar credentials could not be accessed securely",
        ) from exc

    _migrate_legacy_tokens(
        user_id=user_id,
        raw_access_token=raw_access_token,
        raw_refresh_token=raw_refresh_token,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    expires_at = _parse_dt(row.get("expires_at"))

    if access_token and expires_at and expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
        return access_token

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar access token expired and no refresh token is available. Reconnect Google Calendar.",
        )

    client_id, client_secret, _redirect_uri = _require_google_oauth_config()
    refreshed = await _refresh_access_token(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )

    new_access_token = str(refreshed.get("access_token") or "").strip()
    if not new_access_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google token refresh did not return an access token",
        )

    _store_refreshed_token(user_id=user_id, token_payload=refreshed)
    return new_access_token


def _get_token_connection(*, user_id: str) -> dict[str, Any] | None:
    result = safe_execute(
        lambda sb: sb.table("google_calendar_connections")
        .select("status,access_token,refresh_token,expires_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


async def _refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

    if response.status_code >= 400:
        log.warning(
            "calendar oauth: token refresh failed status=%s error=%s",
            response.status_code,
            _google_oauth_error_code(response),
        )
        raise RuntimeError("Google token refresh failed")

    return response.json()


def _store_refreshed_token(*, user_id: str, token_payload: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    expires_in = int(token_payload.get("expires_in") or 3600)
    expires_at = (now + timedelta(seconds=expires_in)).isoformat()

    encrypted_access_token = _encrypt_google_token(
        token_payload.get("access_token")
    )
    if not encrypted_access_token:
        raise RuntimeError("Google token refresh returned no access token")

    updates: dict[str, Any] = {
        "access_token": encrypted_access_token,
        "token_type": token_payload.get("token_type"),
        "expires_at": expires_at,
        "updated_at": now.isoformat(),
    }

    refreshed_refresh_token = _encrypt_google_token(
        token_payload.get("refresh_token")
    )
    if refreshed_refresh_token:
        updates["refresh_token"] = refreshed_refresh_token

    safe_execute(
        lambda sb: sb.table("google_calendar_connections")
        .update(updates)
        .eq("user_id", user_id)
        .execute()
    )

GOOGLE_CALENDAR_EVENTS_MAX_RANGE_DAYS = 31
GOOGLE_CALENDAR_EVENTS_PAGE_SIZE = 250
GOOGLE_CALENDAR_EVENTS_MAX_RESULTS = 500


@router.get("/events")
async def google_calendar_oauth_events(
    start: str = Query(..., min_length=1, max_length=80),
    end: str = Query(..., min_length=1, max_length=80),
    time_zone: str | None = Query(default=None, max_length=100),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Read sanitized events directly from the user's primary Google Calendar."""

    start_dt = _parse_google_events_range_datetime(start, field_name="start")
    end_dt = _parse_google_events_range_datetime(end, field_name="end")

    if end_dt <= start_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar event range end must be after start",
        )

    if end_dt - start_dt > timedelta(days=GOOGLE_CALENDAR_EVENTS_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google Calendar event range cannot exceed "
                f"{GOOGLE_CALENDAR_EVENTS_MAX_RANGE_DAYS} days"
            ),
        )

    clean_time_zone = _validate_google_events_time_zone(time_zone)

    connection = _get_connection(user_id=user_id)
    if not connection or connection.get("status") != "active":
        return {
            "connected": False,
            "events": [],
            "truncated": False,
        }

    try:
        access_token = await get_active_google_calendar_access_token(
            user_id=user_id
        )
        events, truncated = await _list_google_calendar_events(
            access_token=access_token,
            start_dt=start_dt,
            end_dt=end_dt,
            time_zone=clean_time_zone,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "calendar oauth: event read failed user=%s error_type=%s",
            user_id[:8],
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to read Google Calendar",
        ) from exc

    return {
        "connected": True,
        "events": events,
        "truncated": truncated,
    }


def _parse_google_events_range_datetime(
    value: str,
    *,
    field_name: str,
) -> datetime:
    cleaned = str(value or "").strip()

    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be a valid ISO datetime",
        ) from exc

    if parsed.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must include a timezone offset",
        )

    return parsed.astimezone(timezone.utc)


def _validate_google_events_time_zone(value: str | None) -> str | None:
    cleaned = str(value or "").strip()

    if not cleaned:
        return None

    try:
        ZoneInfo(cleaned)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_zone must be a valid IANA timezone",
        ) from exc

    return cleaned


def _build_google_calendar_events_params(
    *,
    start_dt: datetime,
    end_dt: datetime,
    time_zone: str | None,
    page_token: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "timeMin": start_dt.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "timeMax": end_dt.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "singleEvents": "true",
        "orderBy": "startTime",
        "showDeleted": "false",
        "maxResults": GOOGLE_CALENDAR_EVENTS_PAGE_SIZE,
    }

    if time_zone:
        params["timeZone"] = time_zone

    if page_token:
        params["pageToken"] = page_token

    return params


async def _list_google_calendar_events(
    *,
    access_token: str,
    start_dt: datetime,
    end_dt: datetime,
    time_zone: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    events: list[dict[str, Any]] = []
    page_token: str | None = None
    truncated = False

    async with httpx.AsyncClient(timeout=20.0) as client:
        while len(events) < GOOGLE_CALENDAR_EVENTS_MAX_RESULTS:
            params = _build_google_calendar_events_params(
                start_dt=start_dt,
                end_dt=end_dt,
                time_zone=time_zone,
                page_token=page_token,
            )

            response = await client.get(
                GOOGLE_CALENDAR_EVENTS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )

            if response.status_code >= 400:
                log.warning(
                    "calendar oauth: event list failed status=%s error=%s",
                    response.status_code,
                    _google_oauth_error_code(response),
                )
                raise RuntimeError("Google Calendar event list failed")

            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Google Calendar returned an invalid payload")

            raw_items = payload.get("items")
            if not isinstance(raw_items, list):
                raw_items = []

            remaining = GOOGLE_CALENDAR_EVENTS_MAX_RESULTS - len(events)

            normalized_page = [
                normalized
                for item in raw_items
                if isinstance(item, dict)
                for normalized in [
                    _normalize_google_calendar_event(
                        item,
                        time_zone=time_zone,
                    )
                ]
                if normalized is not None
            ]

            if len(normalized_page) > remaining:
                events.extend(normalized_page[:remaining])
                truncated = True
                break

            events.extend(normalized_page)

            next_page_token = str(
                payload.get("nextPageToken") or ""
            ).strip()

            if not next_page_token:
                break

            if len(events) >= GOOGLE_CALENDAR_EVENTS_MAX_RESULTS:
                truncated = True
                break

            page_token = next_page_token

    return events, truncated


def _normalize_google_calendar_event(
    item: dict[str, Any],
    *,
    time_zone: str | None,
) -> dict[str, Any] | None:
    if str(item.get("status") or "").strip().lower() == "cancelled":
        return None

    event_id = str(item.get("id") or "").strip()
    if not event_id:
        return None

    start = item.get("start")
    end = item.get("end")

    if not isinstance(start, dict):
        return None

    if not isinstance(end, dict):
        end = {}

    start_date = str(start.get("date") or "").strip()

    if start_date:
        event_date = start_date
        start_at = None
        end_at = None
        all_day = True
    else:
        start_at = str(start.get("dateTime") or "").strip() or None
        end_at = str(end.get("dateTime") or "").strip() or None

        if not start_at:
            return None

        event_date = _google_event_local_date(
            start_at,
            time_zone=time_zone,
        )
        all_day = False

    title = str(item.get("summary") or "").strip() or "Untitled event"
    location = str(item.get("location") or "").strip() or None
    html_link = str(item.get("htmlLink") or "").strip() or None
    event_status = str(item.get("status") or "").strip() or "confirmed"

    return {
        "id": event_id,
        "title": title[:250],
        "event_date": event_date,
        "start_at": start_at,
        "end_at": end_at,
        "all_day": all_day,
        "location": location[:180] if location else None,
        "html_link": html_link,
        "status": event_status,
        "source": "google",
    }


def _google_event_local_date(
    start_at: str,
    *,
    time_zone: str | None,
) -> str:
    try:
        parsed = datetime.fromisoformat(
            str(start_at).replace("Z", "+00:00")
        )
    except Exception as exc:
        raise RuntimeError(
            "Google Calendar returned an invalid event start datetime"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    if time_zone:
        parsed = parsed.astimezone(ZoneInfo(time_zone))

    return parsed.date().isoformat()
