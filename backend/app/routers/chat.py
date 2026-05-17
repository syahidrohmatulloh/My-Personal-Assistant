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
from app.services import attachments, companion_mode, conversation_summary, life_model, memory
from app.services.claude import get_claude
from app.services.prompt_builder import (
    BASE_PROMPT,
    render_context,
    trim_history,
)
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


async def _check_ownership(_supabase, conversation_id: str, user_id: str):
    return await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("conversations")
            .select("id, style_profile_id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    )


async def _save_user_message(_supabase, conversation_id: str, content: str) -> str:
    """Save the user's message and bump the conversation's updated_at.
    Returns the new message ID so attachments can be linked to it.
    """
    insert_result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("messages")
            .insert(
                {"conversation_id": conversation_id, "role": "user", "content": content}
            )
            .execute()
        )
    )
    await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("conversations")
            .update({"updated_at": "now()"})
            .eq("id", conversation_id)
            .execute()
        )
    )
    return insert_result.data[0]["id"]


async def _load_history(_supabase, conversation_id: str) -> list[dict]:
    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("messages")
            .select("role, content")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        )
    )
    return [{"role": m["role"], "content": m["content"]} for m in (result.data or [])]


@router.post("/chat")
async def chat(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    # === Parallel phase 1: ownership + save + context + legacy mems + related summaries + attachments + mode ===
    (
        convo_result,
        user_message_id,
        context,
        legacy_memories,
        related_summaries,
        attachment_rows,
        detected_mode,
    ) = await asyncio.gather(
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
        asyncio.to_thread(
            lambda: attachments.fetch_for_user(
                user_id=user_id, attachment_ids=body.attachment_ids
            )
        ),
        # Mode detection — runs in parallel so it doesn't add serial latency.
        # Returns None for short messages or on failure, which gracefully
        # skips directive injection below.
        companion_mode.detect_mode(user_message=body.message),
    )

    if not convo_result or not convo_result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    # Link attachments to the saved user message (still pending until now).
    if attachment_rows:
        await asyncio.to_thread(
            lambda: attachments.link_to_message(
                user_id=user_id,
                attachment_ids=[r["id"] for r in attachment_rows],
                message_id=user_message_id,
            )
        )

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

    # Inject companion mode directive. Placed near the end so it has high
    # recency weight in Claude's attention. None on short / ambiguous messages.
    mode_directive = companion_mode.directive_for(detected_mode)
    if mode_directive:
        volatile_context += "\n\n" + mode_directive

    # Inject style profile directive if this conversation has one. The
    # safety preamble is non-negotiable — Claude is adopting STYLE, never
    # impersonating the source person.
    style_profile_id = convo_result.data.get("style_profile_id")
    if style_profile_id:
        style_block = await asyncio.to_thread(
            lambda: _fetch_style_directive(user_id, style_profile_id)
        )
        if style_block:
            volatile_context += "\n\n" + style_block

    # Audit log — explicit which style mode is active. Per design contract,
    # "default" means baseline assistant; "style_profile:<id>" means the
    # conversation has an attached profile that loaded successfully.
    style_audit = (
        f"style_profile:{style_profile_id[:8]}" if style_profile_id else "default"
    )

    log.info(
        "chat: user=%s context_keys=%s legacy_mems=%d related_summaries=%d history_len=%d attachments=%d mode=%s style=%s",
        user_id[:8],
        list(context.keys()),
        len(legacy_memories),
        len(related_summaries),
        len(messages),
        len(attachment_rows),
        detected_mode,
        style_audit,
    )

    # If there are attachments on this turn, replace the last user message's
    # content (currently a plain string) with a multimodal content array:
    # image/document blocks first, then the text. Claude works best when
    # images precede the question about them.
    if attachment_rows and messages:
        content_blocks: list[dict] = []
        for row in attachment_rows:
            block = await asyncio.to_thread(
                lambda r=row: attachments.to_claude_content_block(row=r)
            )
            if block:
                content_blocks.append(block)
        content_blocks.append({"type": "text", "text": body.message})

        # Find and replace the last user message.
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                messages[i] = {"role": "user", "content": content_blocks}
                break

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
            lambda: safe_execute(
                lambda sb: sb.table("messages")
                .insert(
                    {
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": assistant_text,
                    }
                )
                .execute()
            )
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


# ---------------------------------------------------------------------------
# Style profile fetch + directive rendering
# ---------------------------------------------------------------------------


def _fetch_style_directive(user_id: str, style_profile_id: str) -> str | None:
    """Load style profile and render a directive block for the system prompt.

    Schema-aware: v2 profiles include exemplars + concrete patterns and get
    a much richer prompt. v1 (legacy) profiles get the minimal renderer.
    Either way, safety preamble is non-negotiable.
    """
    try:
        supabase = get_supabase()
        row = (
            supabase.table("style_profiles")
            .select("profile_name, extracted_style")
            .eq("id", style_profile_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not row or not row.data:
            return None
        style = row.data["extracted_style"] or {}
        directive = (style.get("compact_directive") or "").strip()
        if not directive:
            return None

        version = style.get("schema_version") or 1
        if version >= 2:
            return _render_v2_directive(style)
        return _render_v1_directive(style)
    except Exception as exc:
        log.warning("style directive fetch failed: %s", exc)
        return None


def _render_v2_directive(style: dict) -> str:
    """Rich renderer for v2 profiles: exemplars + concrete patterns +
    explicit override of baseline 'polished' behavior."""
    directive = (style.get("compact_directive") or "").strip()
    exemplars = [e for e in (style.get("exemplars") or []) if isinstance(e, str) and e.strip()][:10]
    phrases = [p for p in (style.get("common_phrases") or []) if isinstance(p, str) and p.strip()][:15]
    do_not_copy = [d for d in (style.get("do_not_copy") or []) if isinstance(d, str) and d.strip()][:10]

    parts: list[str] = ["## Communication style for this conversation", "", directive]

    if exemplars:
        parts.append("")
        parts.append("**Style anchors — examples of how this person actually writes:**")
        for ex in exemplars:
            parts.append(f'  · "{ex}"')
        parts.append("")
        parts.append(
            "Use these as TEXTURE references — match their cadence, "
            "fragmentation, punctuation, and filler patterns. Do NOT quote them "
            "verbatim back to the user; they're for shape, not for content."
        )

    if phrases:
        parts.append("")
        parts.append(f"**Fillers/phrases they use naturally:** {', '.join(phrases)}")
        parts.append("Drop these in where they fit. Do not force them.")

    # Override baseline behavior — without this, BASE_PROMPT's "complete
    # sentences" and "no excessive emoji" rules suppress the style.
    parts.extend([
        "",
        "**Override the assistant's default polished register for this conversation.**",
        "- If their style is fragmented, send fragmented short replies — not one balanced paragraph.",
        "- If their punctuation is loose, be loose. Drop periods if they do.",
        "- If their capitalization is informal, follow it.",
        "- Imperfect texting flow over polished AI prose.",
        "- BUT: still serve the user's actual question or need. Style shapes HOW you reply, not WHAT you reply about.",
    ])

    parts.extend([
        "",
        "**Hard boundaries (these always win over style):**",
        "- This is STYLE adaptation only. You are still the user's assistant.",
        "- NEVER claim to be the source person. NEVER speak as if you ARE them.",
        "- NEVER reproduce private details from their messages.",
        "- If the user asks 'are you Anna?' or similar — answer honestly that you're their assistant adopting a style.",
    ])

    if do_not_copy:
        parts.append("- NEVER reproduce or reference these specific items:")
        for item in do_not_copy:
            parts.append(f"    · {item}")

    return "\n".join(parts)


def _render_v1_directive(style: dict) -> str:
    """Minimal renderer for legacy v1 profiles. Suggests user re-analyze."""
    directive = (style.get("compact_directive") or "").strip()
    do_not_copy = [d for d in (style.get("do_not_copy") or []) if isinstance(d, str)][:10]

    parts: list[str] = [
        "## Communication style for this conversation",
        "",
        directive,
        "",
        "**Override the assistant's default polished register for this conversation.**",
        "If the style above implies short/fragmented messages, send those — not one balanced paragraph.",
        "",
        "**Hard boundaries:**",
        "- STYLE adaptation only. You are still the user's assistant.",
        "- NEVER claim to be the source person.",
        "- NEVER reproduce private details.",
    ]
    if do_not_copy:
        parts.append("- NEVER reproduce these:")
        for item in do_not_copy:
            parts.append(f"    · {item}")
    parts.append("")
    parts.append("(Note: this profile uses an older format. Re-analyze in Settings → Style Profiles for richer texture.)")
    return "\n".join(parts)
