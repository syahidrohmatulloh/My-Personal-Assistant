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
from app.services import briefing
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)
router = APIRouter(prefix="/briefing", tags=["briefing"])


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


@router.post("/{briefing_id}/open", status_code=status.HTTP_201_CREATED)
async def open_briefing(
    briefing_id: str,
    body: OpenBriefingIn,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new conversation seeded with the briefing as the first
    assistant message. Returns {conversation_id}.

    Idempotent — if the briefing was already opened, returns the existing
    conversation_id.
    """
    # Look up the briefing.
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

    # If already opened, return existing convo.
    if row.get("conversation_id"):
        return {"conversation_id": row["conversation_id"]}

    # Create the conversation.
    title = body.title or "Morning briefing"
    convo_res = safe_execute(
        lambda sb: sb.table("conversations")
        .insert({"user_id": user_id, "title": title})
        .execute()
    )
    conversation_id = convo_res.data[0]["id"]

    # Seed the conversation with the briefing as an assistant message.
    safe_execute(
        lambda sb: sb.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": row["content"],
            }
        )
        .execute()
    )

    # Link briefing → conversation.
    await briefing.mark_briefing_opened(
        user_id=user_id,
        briefing_id=briefing_id,
        conversation_id=conversation_id,
    )

    return {"conversation_id": conversation_id}
