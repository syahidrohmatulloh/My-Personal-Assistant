import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import get_current_user_id
from app.services.claude import get_claude
from app.services.supabase_client import get_supabase
from typing import Optional
from pydantic import BaseModel

class ChatIn(BaseModel):
    conversation_id: str
    message: str
    client_id: Optional[str] = None

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    # =========================
    # VALIDATE CONVERSATION
    # =========================
    convo = (
        supabase.table("conversations")
        .select("id")
        .eq("id", body.conversation_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    if not convo or not convo.data:
        raise HTTPException(404, "Conversation not found")

    # =========================
    # SAVE USER MESSAGE
    # =========================
    supabase.table("messages").insert(
        {
            "conversation_id": body.conversation_id,
            "role": "user",
            "content": body.message,
            "client_id": body.client_id,
        }
    ).execute()

    # =========================
    # LOAD HISTORY
    # =========================
    history = (
        supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", body.conversation_id)
        .order("created_at")
        .execute()
    )

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in (history.data or [])
    ]

    system_prompt = "You are a helpful AI companion."

    return StreamingResponse(
        _stream(messages, system_prompt, body.conversation_id, body.client_id),
        media_type="text/event-stream",
    )


# =========================
# STREAM (STABLE VERSION)
# =========================
async def _stream(messages, system_prompt, conversation_id, client_id):
    claude = get_claude()
    supabase = get_supabase()

    assistant_text = ""

    # 🔥 IMPORTANT: handshake supaya frontend langsung start
    yield f"data: {json.dumps({'type': 'start'})}\n\n"

    try:
        async with claude.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for chunk in stream.text_stream:
                assistant_text += chunk

                yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    # =========================
    # SAVE FINAL MESSAGE
    # =========================
    if assistant_text.strip():
        supabase.table("messages").insert(
            {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": assistant_text,
                "client_id": client_id,
            }
        ).execute()

    # DONE SIGNAL
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
