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

Phase 4.12 — typing meta event (additive, non-breaking):

  * A single SSE event `{"type":"meta", ...}` is emitted at the START of
    the stream, before any `delta`. It carries the detected companion mode
    and a derived `pacing` hint so the frontend can humanize reveal speed
    and show "Assistant is typing".
  * `detected_mode` is REUSED from the existing companion_mode.detect_mode
    call (which already runs in parallel) — no extra latency, no LLM call
    duplication, no new service file.
  * If detection returns None or fails, we emit `pacing: "natural"` and
    `mode: "unknown"`. Frontend falls back to its own heuristic.
  * Metadata is NEVER persisted as a message and NEVER appears in chat
    text. It is purely a presentation-layer hint.
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


# ---------------------------------------------------------------------------
# Companion mode → pacing mapping
# ---------------------------------------------------------------------------
#
# Frontend pacing values:
#   - "immediate" : no artificial delay, render tokens as they arrive
#   - "fast"      : minimal delay, for practical/coding/strategy contexts
#   - "natural"   : human-like default
#   - "slow"      : slight extra delay, for listener/reflective space
#
# Defensive defaults — if backend mode is unknown or None, frontend gets
# "natural" and applies its own heuristic.

_MODE_TO_PACING: dict[str, str] = {
    "practical": "fast",
    "strategist": "fast",
    "motivator": "fast",
    "challenger": "natural",
    "listener": "slow",
    "reflective": "slow",
}


def _mode_to_pacing(mode: str | None) -> str:
    if mode is None:
        return "natural"
    return _MODE_TO_PACING.get(mode, "natural")


# Hardcoded for now — will be wired to user settings in a later phase.
# Keeping this here as a single point of change.
_ASSISTANT_NAME = "Assistant"


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
            detected_mode=detected_mode,
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
    detected_mode: str | None,
) -> AsyncIterator[str]:
    claude = get_claude()
    supabase = get_supabase()
    assistant_text = ""

    # --- Phase 4.12: emit typing meta as the very first SSE event ---
    # Frontend uses this to:
    #   - decide pacing (slow / natural / fast / immediate)
    #   - show "Assistant is typing" indicator with a name
    # If frontend doesn't recognize this event, it should ignore it safely.
    # Persistence is unaffected — this is presentation only.
    meta_payload = {
        "type": "meta",
        "mode": detected_mode if detected_mode else "unknown",
        "pacing": _mode_to_pacing(detected_mode),
        "assistant_name": _ASSISTANT_NAME,
    }
    yield f"data: {json.dumps(meta_payload)}\n\n"

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
    """Load the style profile and render a high-signal directive block.

    The first implementation injected only compact_directive, which made the
    assistant sound like generic AI with a slightly different tone. For stronger
    style adaptation, this renderer also injects cadence, punctuation,
    linguistic texture, emotional rhythm, and short sanitized behavioral
    exemplars. The safety boundary remains explicit: style, not identity.
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

        lines: list[str] = [
            "## Communication style for this conversation",
            "Adopt the communication STYLE described below, not the source person's identity.",
            "The goal is recognizable conversational texture: cadence, message shape, punctuation, language mixing, and emotional rhythm.",
            "Do not sound like a polished assistant when this style is active.",
            "",
            "### Core style directive",
            directive,
        ]

        detail_pairs = [
            ("Cadence", style.get("cadence_signature")),
            ("Message shape", style.get("message_shape")),
            ("Punctuation", style.get("punctuation_style")),
            ("Language switching", style.get("language_switching_behavior")),
            ("Emotional rhythm", style.get("emotional_rhythm")),
            ("Teasing pattern", style.get("teasing_pattern")),
            ("Reassurance pattern", style.get("reassurance_pattern")),
            ("Question style", style.get("question_style")),
        ]
        detail_lines = [
            f"- {label}: {value.strip()}"
            for label, value in detail_pairs
            if isinstance(value, str) and value.strip() and value.strip().lower() != "unclear"
        ]
        if detail_lines:
            lines.extend(["", "### Texture rules", *detail_lines])

        list_bits: list[str] = []
        for label, key in [
            ("Filler/softener words", "filler_words"),
            ("Common short phrases", "common_phrases"),
            ("Linguistic texture", "linguistic_texture"),
            ("AI polish to avoid", "ai_polish_to_avoid"),
        ]:
            values = _clean_style_list(style.get(key), limit=10)
            if values:
                list_bits.append(f"- {label}: {', '.join(values)}")
        if list_bits:
            lines.extend(["", "### Reusable micro-patterns", *list_bits])

        phrase_lines = _render_phrase_confidence(style.get("phrase_confidence"))
        if phrase_lines:
            lines.extend(
                [
                    "",
                    "### Observed phrase confidence",
                    "Prefer high-confidence observed phrases/patterns. Do not overuse low-confidence phrases.",
                    *phrase_lines,
                ]
            )

        exemplar_lines = _render_style_exemplars(style.get("exemplars"))
        if exemplar_lines:
            lines.extend(
                [
                    "",
                    "### Short behavioral exemplars",
                    "Use these only as rhythm/texture anchors. Do NOT copy them verbatim unless they are generic fillers.",
                    *exemplar_lines,
                ]
            )

        calibration_lines = _render_style_calibration(style.get("style_calibration"))
        if calibration_lines:
            lines.extend(
                [
                    "",
                    "### Human calibration feedback — highest priority for style accuracy",
                    "This feedback overrides generic descriptors. Stay closer to confirmed patterns and avoid confirmed misses.",
                    *calibration_lines,
                ]
            )

        do_not_copy = _clean_style_list(style.get("do_not_copy"), limit=10)
        lines.extend(
            [
                "",
                "### Important boundaries",
                "- This is STYLE adaptation only. You are still the user's assistant.",
                "- NEVER claim to be the source person. NEVER use their name in first person.",
                "- NEVER reproduce private details from their messages.",
                "- Prefer similar cadence and message shape over exact wording.",
                "- If unsure, use simpler observed patterns instead of inventing new slang or catchphrases.",
                "- Do NOT introduce unsupported idioms such as 'deal?' unless clearly confirmed by examples/calibration.",
                "- If the user asks you to literally impersonate or deceive someone, refuse that part and offer style adaptation only.",
            ]
        )
        if do_not_copy:
            lines.append("- Do NOT reproduce or reference these: " + "; ".join(do_not_copy))

        return "\n".join(lines)
    except Exception as exc:
        log.warning("style directive fetch failed: %s", exc)
        return None


def _clean_style_list(value, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for raw in value:
        item = str(raw).strip()
        if not item:
            continue
        item = " ".join(item.split())[:120]
        if item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _render_phrase_confidence(value) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase") or "").strip()
        if not phrase:
            continue
        count = item.get("evidence_count", "?")
        confidence = str(item.get("confidence") or "unknown").strip()
        phrase = " ".join(phrase.split())[:80]
        rows.append(f"- ‘{phrase}’ — confidence={confidence}, evidence_count={count}")
    return rows


def _render_style_calibration(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    rows: list[str] = []

    positives = _clean_style_list(value.get("positive_examples"), limit=8)
    if positives:
        rows.append("- Sounds accurate: " + " | ".join(f"‘{x}’" for x in positives))

    negatives = _clean_style_list(value.get("negative_examples"), limit=8)
    banned = _clean_style_list(value.get("banned_phrases"), limit=12)
    avoid = []
    for item in negatives + banned:
        if item not in avoid:
            avoid.append(item)
    if avoid:
        rows.append("- Avoid / does NOT sound like target: " + " | ".join(f"‘{x}’" for x in avoid[:12]))

    rewrites = value.get("preferred_rewrites")
    if isinstance(rewrites, list):
        rewrite_bits: list[str] = []
        for item in rewrites[:8]:
            if isinstance(item, dict):
                bad = str(item.get("bad") or "").strip()[:120]
                better = str(item.get("better") or "").strip()[:120]
                if bad and better:
                    rewrite_bits.append(f"‘{bad}’ → ‘{better}’")
        if rewrite_bits:
            rows.append("- Preferred rewrites: " + " | ".join(rewrite_bits))

    notes = _clean_style_list(value.get("notes"), limit=6)
    if notes:
        rows.extend(f"- Calibration note: {note}" for note in notes)

    if rows:
        rows.append("- Generation rule: interpolate from confirmed examples; do not invent new casual phrases when evidence is weak.")
        rows.append("- Generation rule: keep responses short/fragmented when the target style is short/fragmented; remove polished assistant phrasing.")
    return rows


def _render_style_exemplars(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    labels = [
        ("greeting", "Greeting"),
        ("casual_reaction", "Casual reaction"),
        ("teasing", "Teasing"),
        ("comforting", "Comforting"),
        ("affection", "Affection"),
        ("question_style", "Question style"),
        ("apology_or_repair", "Repair/apology"),
        ("encouragement", "Encouragement"),
        ("goodbye", "Goodbye"),
        ("fragmented_followup", "Fragmented follow-up"),
    ]
    rows: list[str] = []
    for key, label in labels:
        examples = _clean_style_list(value.get(key), limit=3)
        if examples:
            rows.append(f"- {label}: " + " | ".join(f"‘{x}’" for x in examples))
        if len(rows) >= 8:
            break
    return rows
