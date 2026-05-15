"""Phase 3 chat router — adaptive personality + cross-chat continuity."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import get_current_user_id
from app.schemas import ChatIn
from app.services import life_model, memory
from app.services.claude import get_claude
from app.services.prompt_builder import build_system_prompt
from app.services.supabase_client import get_supabase

# 🔥 tone system
from app.tone import (
    detect_romantic_tone,
    detect_emotional_state,
    detect_mode,
    compute_romantic_baseline,
    resolve_romantic_tone,
    resolve_mode,
)

# 🔥 prompts
from app.prompts import (
    build_interaction_context,
    build_emotional_context,
    build_mode_context,
    get_tone_instruction,
    get_emotional_instruction,
    get_mode_instruction,
    build_greeting,
)

# 🔥 persistence
from app.services.user_state import get_user_state, save_user_state

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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    # =========================
    # SAVE USER MESSAGE
    # =========================
    supabase.table("messages").insert(
        {
            "conversation_id": body.conversation_id,
            "role": "user",
            "content": body.message,
        }
    ).execute()

    supabase.table("conversations").update({"updated_at": "now()"}).eq(
        "id", body.conversation_id
    ).execute()

    # =========================
    # LOAD CONTEXT
    # =========================
    context = await life_model.get_context(user_id, mood_days=14)

    # 🔥 LOAD CROSS-CHAT STATE
    user_state = await get_user_state(user_id)
    persisted_mode = user_state.get("mode")
    persisted_baseline = user_state.get("romantic_baseline")

    # =========================
    # DETECT SIGNALS
    # =========================
    romantic_level = detect_romantic_tone(body.message)
    emotion = detect_emotional_state(body.message)

    # =========================
    # HISTORY (SHORT)
    # =========================
    history_result = (
        supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", body.conversation_id)
        .order("created_at", desc=True)
        .limit(6)
        .execute()
    )

    is_first_message = len(history_result.data) <= 1

    recent_messages = [
        m["content"]
        for m in history_result.data
        if m["role"] == "user"
    ]

    computed_baseline = compute_romantic_baseline(recent_messages)
    baseline = persisted_baseline or computed_baseline

    # =========================
    # MODE
    # =========================
    current_mode = detect_mode(
        body.message,
        emotion.value,
        romantic_level.value,
    )

    mode = resolve_mode(current_mode.value, persisted_mode)

    context["mode"] = mode
    context["romantic_baseline"] = baseline

    # =========================
    # FINAL TONE
    # =========================
    final_tone = resolve_romantic_tone(
        romantic_level.value,
        baseline
    )

    # =========================
    # MEMORY
    # =========================
    legacy_memories = await memory.retrieve_relevant(
        user_id,
        body.message,
        limit=3
    )

    if legacy_memories:
        context.setdefault("unstructured_memories", legacy_memories)

    # =========================
    # BUILD PROMPT
    # =========================
    system_prompt = build_system_prompt(context)

    # 🔥 GREETING
    if is_first_message:
        greeting = build_greeting(
            name=context.get("identity", {}).get("name", "there"),
            tone=final_tone,
            emotion=emotion.value,
            mode=mode,
        )

        system_prompt += f"\n\n## Opening Style\nStart with:\n{greeting}"

    # =========================
    # CONTEXT
    # =========================
    system_prompt += build_interaction_context(final_tone, baseline)
    system_prompt += build_emotional_context(emotion.value)
    system_prompt += build_mode_context(mode)

    # =========================
    # RESPONSE SHAPING
    # =========================
    system_prompt += get_tone_instruction(final_tone)
    system_prompt += get_emotional_instruction(emotion.value)
    system_prompt += get_mode_instruction(mode)

    # =========================
    # EXTRA MEMORY
    # =========================
    if legacy_memories:
        extra = "\n".join(f"- {m['content']}" for m in legacy_memories[:3])
        system_prompt += f"\n\n## Additional notes\n{extra}"

    log.info(
        "chat: user=%s tone=%s mode=%s emotion=%s",
        user_id[:8],
        final_tone,
        mode,
        emotion.value,
    )

    # =========================
    # FULL HISTORY
    # =========================
    history_full = (
        supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", body.conversation_id)
        .order("created_at")
        .execute()
    )

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history_full.data
    ]

    # 🔥 SAVE STATE (CROSS-CHAT)
    await save_user_state(
        user_id=user_id,
        mode=mode,
        romantic_baseline=baseline,
    )

    # =========================
    # STREAM RESPONSE
    # =========================
    return StreamingResponse(
        _stream_claude_response(
            user_id=user_id,
            conversation_id=body.conversation_id,
            messages=messages,
            system_prompt=system_prompt,
            user_message=body.message,
            background_tasks=background_tasks,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_claude_response(
    *,
    user_id: str,
    conversation_id: str,
    messages: list[dict],
    system_prompt: str,
    user_message: str,
    background_tasks: BackgroundTasks,
) -> AsyncIterator[str]:

    claude = get_claude()
    supabase = get_supabase()
    assistant_text = ""

    try:
        async with claude.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            timeout=60,
        ) as stream:
            async for text_chunk in stream.text_stream:
                assistant_text += text_chunk
                yield f"data: {json.dumps({'type': 'delta', 'text': text_chunk})}\n\n"

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    if assistant_text:
        supabase.table("messages").insert(
            {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": assistant_text,
            }
        ).execute()

    background_tasks.add_task(
        memory.extract_and_save,
        user_id=user_id,
        conversation_id=conversation_id,
        recent_messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_text},
        ],
    )

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
