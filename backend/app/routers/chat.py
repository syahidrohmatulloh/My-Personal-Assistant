"""Chat router — parallelized pipeline with prompt caching and history trim.

Perf shifts vs Phase 4:

  * Ownership check, user-message save, context fetch, memory retrieval all
    fire concurrently via asyncio.gather instead of serially.
  * History load is the only awaited-after-save step.
  * System prompt is split into a stable cached block (BASE_PROMPT) and a
    volatile context block — Anthropic ephemeral cache cuts repeat-prompt
    cost by 90% and TTFT by ~30-50%.
  * History is trimmed to a token budget so long chats don't blow up.
  * Title generation runs in background after first message.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import get_current_user_id
from app.schemas import ChatIn
from app.services import conversation_summary, life_model, memory
from app.services.claude import get_claude
from app.services.prompt_builder import (
    BASE_PROMPT,
    render_context,
    trim_history,
)
from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


async def _check_ownership(supabase, conversation_id: str, user_id: str):
    return await asyncio.to_thread(
        lambda: supabase.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )


async def _save_user_message(supabase, conversation_id: str, content: str):
    await asyncio.to_thread(
        lambda: supabase.table("messages")
        .insert({"conversation_id": conversation_id, "role": "user", "content": content})
        .execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("conversations")
        .update({"updated_at": "now()"})
        .eq("id", conversation_id)
        .execute()
    )


async def _load_history(supabase, conversation_id: str) -> list[dict]:
    result = await asyncio.to_thread(
        lambda: supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )
    return [{"role": m["role"], "content": m["content"]} for m in (result.data or [])]


@router.post("/chat")
async def chat(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    # === Parallel phase 1: ownership + save + context + legacy mems + related summaries ===
    convo_result, _, context, legacy_memories, related_summaries = await asyncio.gather(
        _check_ownership(supabase, body.conversation_id, user_id),
        _save_user_message(supabase, body.conversation_id, body.message),
        life_model.get_context(user_id, mood_days=14),
        memory.retrieve_relevant(user_id, body.message, limit=5),
        conversation_summary.retrieve_related_summaries(
            user_id=user_id,
            query_text=body.message,
            exclude_conversation_id=body.conversation_id,
            limit=3,
        ),
    )

    if not convo_result or not convo_result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    # === Phase 2: history (must be after save) ===
    messages = await _load_history(supabase, body.conversation_id)
    messages = trim_history(messages)

    # === Build prompt with cached base + volatile context ===
    volatile_context = render_context(context)
    if legacy_memories:
        extra = "\n".join(f"- {m['content']}" for m in legacy_memories[:5])
        volatile_context += f"\n\n## Additional notes (unstructured)\n{extra}"

    # Inject related conversation summaries — cross-chat continuity.
    if related_summaries:
        lines = ["## Possibly related past conversations (for grounding, not for recital)"]
        for s in related_summaries:
            when = s["updated_at"][:10] if s.get("updated_at") else "?"
            title = s.get("title") or "Untitled"
            lines.append(f"- [{when}] {title}: {s['summary']}")
        volatile_context += "\n\n" + "\n".join(lines)

    log.info(
        "chat: user=%s context_keys=%s legacy_mems=%d related_summaries=%d history_len=%d",
        user_id[:8],
        list(context.keys()),
        len(legacy_memories),
        len(related_summaries),
        len(messages),
    )

    is_first_message = len(messages) <= 1  # only the user message we just saved

    return StreamingResponse(
        _stream_claude_response(
            user_id=user_id,
            conversation_id=body.conversation_id,
            messages=messages,
            volatile_context=volatile_context,
            user_message=body.message,
            background_tasks=background_tasks,
            is_first_message=is_first_message,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
        background=background_tasks,
    )


async def _stream_claude_response(
    *,
    user_id: str,
    conversation_id: str,
    messages: list[dict],
    volatile_context: str,
    user_message: str,
    background_tasks: BackgroundTasks,
    is_first_message: bool,
) -> AsyncIterator[str]:
    claude = get_claude()
    supabase = get_supabase()
    assistant_text = ""

    # System prompt as two blocks:
    #   - BASE_PROMPT: stable, cached for 5 min (ephemeral cache)
    #   - volatile_context: per-user, per-turn, not cached
    system_blocks: list[dict] = [
        {
            "type": "text",
            "text": BASE_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if volatile_context:
        system_blocks.append({"type": "text", "text": volatile_context})

    try:
        async with claude.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_blocks,
            messages=messages,
        ) as stream:
            async for text_chunk in stream.text_stream:
                assistant_text += text_chunk
                yield f"data: {json.dumps({'type': 'delta', 'text': text_chunk})}\n\n"
    except Exception as exc:  # noqa: BLE001
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        return

    if assistant_text:
        await asyncio.to_thread(
            lambda: supabase.table("messages")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": assistant_text,
                }
            )
            .execute()
        )

    # Background memory extraction (writes to legacy unstructured table)
    background_tasks.add_task(
        memory.extract_and_save,
        user_id=user_id,
        conversation_id=conversation_id,
        recent_messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_text},
        ],
    )

    # Background conversation-summary update. Idempotent — only runs Haiku
    # if the conversation has grown ≥N messages since last summarize.
    background_tasks.add_task(
        conversation_summary.summarize_conversation,
        conversation_id=conversation_id,
    )

    # Background title generation on first message
    if is_first_message and assistant_text:
        background_tasks.add_task(
            _generate_title,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_reply=assistant_text,
        )

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ---------------------------------------------------------------------------
# Background: title generation on first turn
# ---------------------------------------------------------------------------

async def _generate_title(
    *, conversation_id: str, user_message: str, assistant_reply: str
) -> None:
    """Generate a short conversation title with Haiku. Cheap, runs once."""
    claude = get_claude()
    supabase = get_supabase()
    try:
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=30,
            system=(
                "Generate a concise 3-6 word title summarizing this conversation. "
                "Output ONLY the title, no quotes, no punctuation at end."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"USER: {user_message[:500]}\n\nASSISTANT: {assistant_reply[:500]}",
                }
            ],
        )
        block = next((b for b in response.content if b.type == "text"), None)
        if not block:
            return
        title = block.text.strip().strip('"').strip("'")[:60]
        if not title:
            return
        await asyncio.to_thread(
            lambda: supabase.table("conversations")
            .update({"title": title})
            .eq("id", conversation_id)
            .execute()
        )
    except Exception as exc:
        log.warning("title generation failed: %s", exc)
