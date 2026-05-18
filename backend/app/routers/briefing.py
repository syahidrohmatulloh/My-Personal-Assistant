"""Briefing endpoints.

  - GET  /briefing/today?date=YYYY-MM-DD       returns today's briefing (generating if absent)
  - POST /briefing/{briefing_id}/open          creates a conversation seeded with the briefing text
                                                and links the briefing to it
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import get_current_user_id
from app.services import briefing, companion
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)
router = APIRouter(prefix="/briefing", tags=["briefing"])


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _main_chat_title_from_settings(settings_row: dict | None) -> str:
    assistant_name = str((settings_row or {}).get("assistant_name") or "").strip()
    return f"Main Chat - {assistant_name or 'Assistant'}"



@router.get("/today")
async def get_today_briefing(
    date: str,
    user_id: str = Depends(get_current_user_id),
):
    """Return today's briefing for the user. Generates if missing.

    `date` is the user's local date 'YYYY-MM-DD'. The frontend computes this
    using the browser's timezone so we don't have to resolve the user's
    timezone server-side just to check "is today's briefing already made".
    """
    if not _DATE_RE.match(date):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "date must be YYYY-MM-DD")

    row = await briefing.get_or_generate_briefing(user_id=user_id, local_date=date)
    if not row:
        return {"briefing": None}
    return {"briefing": row}


class OpenBriefingIn(BaseModel):
    title: str | None = None


@router.post("/{briefing_id}/open")
async def open_briefing(
    briefing_id: str,
    body: OpenBriefingIn,
    user_id: str = Depends(get_current_user_id),
):
    """Link the briefing to the user's Main Chat and return that conversation.

    This does not create a separate briefing conversation and does not insert
    the briefing as an automatic chat message. The frontend can show the
    briefing as a card and only discuss it when the user explicitly asks.
    """
    res = safe_execute(
        lambda sb: sb.table("daily_briefings")
        .select("id, content, conversation_id")
        .eq("id", briefing_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not res or not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Briefing not found")

    row = res.data

    mapping = safe_execute(
        lambda sb: sb.table("user_main_chats")
        .select("conversation_id")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    conversation_id = (mapping.data or {}).get("conversation_id") if mapping else None

    if conversation_id:
        existing = safe_execute(
            lambda sb: sb.table("conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not existing or not existing.data:
            conversation_id = None

    if not conversation_id:
        companion_settings = await companion.get_settings(user_id)
        title = _main_chat_title_from_settings(companion_settings)
        created = safe_execute(
            lambda sb: sb.table("conversations")
            .insert({"user_id": user_id, "title": title})
            .execute()
        )
        if not created.data:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Failed to create Main Chat",
            )

        conversation_id = created.data[0]["id"]

        safe_execute(
            lambda sb: sb.table("user_main_chats")
            .upsert(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                }
            )
            .execute()
        )

    if row.get("conversation_id") != conversation_id:
        await briefing.mark_briefing_opened(
            user_id=user_id,
            briefing_id=briefing_id,
            conversation_id=conversation_id,
        )

    return {"conversation_id": conversation_id}
