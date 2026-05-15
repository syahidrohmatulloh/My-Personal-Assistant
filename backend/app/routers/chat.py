import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.core.auth import get_current_user_id
from app.services.claude import get_claude
from app.services.supabase_client import get_supabase
from app.services.embeddings import embed_document, embed_query
from app.prompts import build_system_prompt

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    conversation_id: str
    message: str
    client_id: Optional[str] = None


def detect_mode(message: str) -> str:
    msg = message.lower()

    if any(k in msg for k in ["pdf", "summarize", "resume", "analisa"]):
        return "work"

    if any(k in msg for k in ["stress", "capek", "sedih"]):
        return "relationship"

    return "life"


def classify_memory(message: str) -> str:
    msg = message.lower()

    if any(k in msg for k in ["suka", "prefer", "favorite", "biasanya"]):
        return "preference"

    if any(k in msg for k in ["lagi", "sekarang", "sedang"]):
        return "context"

    return "fact"


def extract_state(message: str) -> Optional[str]:
    msg = message.lower()

    if any(k in msg for k in ["lagi", "sedang", "sekarang"]):
        return message

    if "di " in msg and not any(
        k in msg for k in ["akan", "besok", "tahun", "bulan"]
    ):
        return message

    return None


def get_importance(message: str) -> float:
    msg = message.lower()

    score = 0.5

    if "aku" in msg or "saya" in msg:
        score += 0.2

    if "rencana" in msg or "tujuan" in msg:
        score += 0.2

    if "stress" in msg or "sedih" in msg:
        score += 0.2

    return min(score, 1.0)


def extract_temporal_info(message: str):
    msg = message.lower()

    event_type = "general"
    temporal_status = "present"
    event_date = None

    if "usa" in msg or "jepang" in msg:
        event_type = "travel"
    elif "hotel" in msg or "restoran" in msg:
        event_type = "place"

    if "akan" in msg or "besok" in msg:
        temporal_status = "future"
    elif "kemarin" in msg or "pernah" in msg:
        temporal_status = "past"

    year_match = re.search(r"(202[0-9])", msg)
    if year_match:
        event_date = year_match.group(1)

    return {
        "event_type": event_type,
        "temporal_status": temporal_status,
        "event_date": event_date,
    }

@router.post("/chat")
async def chat(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    # SAVE USER MESSAGE
    supabase.table("messages").insert({
        "conversation_id": body.conversation_id,
        "role": "user",
        "content": body.message,
        "client_id": body.client_id,
    }).execute()

    # STATE
    state = extract_state(body.message)

    if state:
        try:
            supabase.table("user_state").update({
                "superseded": True
            }).eq("user_id", user_id).eq("superseded", False).execute()

            supabase.table("user_state").insert({
                "user_id": user_id,
                "content": state,
                "superseded": False,
            }).execute()
        except Exception as e:
            log.warning(f"State error: {e}")

    # MEMORY
    try:
        embedding = await embed_document(body.message)
        temporal = extract_temporal_info(body.message)

        supabase.table("memories").insert({
            "user_id": user_id,
            "content": body.message,
            "embedding": embedding,
            "kind": classify_memory(body.message),
            "importance": get_importance(body.message),
            "source": "auto",
            "source_conversation_id": body.conversation_id,
            "event_type": temporal["event_type"],
            "temporal_status": temporal["temporal_status"],
            "event_date": temporal["event_date"],
        }).execute()
    except Exception as e:
        log.warning(f"Memory error: {e}")

    # LOAD STATE
    current_state = ""
    st = supabase.table("user_state").select("content").eq("user_id", user_id).eq("superseded", False).limit(1).execute()

    if st.data:
        current_state = st.data[0]["content"]

    # LOAD MEMORY
    memory_text = ""
    try:
        query_embedding = await embed_query(body.message)

        memories = supabase.rpc("match_memories", {
            "p_user_id": user_id,
            "p_query_embedding": query_embedding,
            "p_match_count": 8,
        }).execute()

        if memories.data:
            memory_text = "\n".join([m["content"] for m in memories.data[:5]])

    except Exception as e:
        log.warning(f"Memory load error: {e}")

    # LOAD HISTORY
    history = supabase.table("messages").select("role, content").eq("conversation_id", body.conversation_id).order("created_at").execute()

    messages = [{"role": m["role"], "content": m["content"]} for m in (history.data or [])]

    # PROMPT
    context = {
        "mode": detect_mode(body.message),
        "memory": memory_text,
        "state": current_state,
    }

    system_prompt = build_system_prompt(context)

    return StreamingResponse(
        _stream(messages, system_prompt, body.conversation_id, body.client_id),
        media_type="text/event-stream",
    )

async def _stream(messages, system_prompt, conversation_id, client_id):
    claude = get_claude()
    supabase = get_supabase()

    assistant_text = ""

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

    if assistant_text.strip():
        supabase.table("messages").insert({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": assistant_text,
            "client_id": client_id,
        }).execute()

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
