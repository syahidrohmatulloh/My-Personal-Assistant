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

Phase 4.12 Zip 2 changes:
  * Companion mood state + assistant name now sourced from the new
    `companion_settings` + `companion_mood_state` tables via the
    `companion` service, not from identity.profile or the old
    `companion_mood_states` table.
  * Companion mood is fully gated by user settings:
      - companion_mode='professional' | 'friendly' | 'affectionate' →
        mood block + repair gate are NOT injected
      - companion_mode='partner' + mood_realism='dynamic' → mood block injected
      - repair_gate_enabled=true → repair gate logic injected
  * Default assistant_name is "Assistant", not "Aliyya". Aliyya stays for
    users who explicitly have her configured (the migration preserved that).
"""

import asyncio
import time
import json
import logging
import re
from datetime import datetime, timedelta
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import get_current_user_id
from app.schemas import ChatIn
from app.services import (
    calendar_candidate_extractor,
    calendar_confirmation_actions,
    calendar_draft_actions,
    conversation_summary,
    attachments,
    companion,
    companion_comeback_affect,
    cognitive_runtime,
    memory,
    memory_intelligence,
    proactive_nudges,
    name_normalization,
    background_extraction_gate,
    goal_intelligence,
    mood_memory_feedback,
    relationship_memory,
)
from app.services.claude import get_claude
from app.services.prompt_builder import (
    trim_history,
)
from app.services.supabase_client import get_supabase, safe_execute
from app.services.safe_background import add_safe_background_task

log = logging.getLogger(__name__)
timing_log = logging.getLogger("uvicorn.error")
CHAT_HISTORY_LOAD_LIMIT = 80

router = APIRouter(tags=["chat"])

def _clean_assistant_name(name: str | None) -> str | None:
    return name_normalization.normalize_assistant_name(name)



def _extract_assistant_name(user_message: str) -> str | None:
    names = name_normalization.extract_explicit_names(user_message)
    return names.assistant_name


def _mode_to_pacing(mode: str | None) -> str:
    """Map companion mode to frontend reveal pacing."""
    if mode in {"practical", "strategist", "motivator"}:
        return "fast"
    if mode in {"listener", "reflective"}:
        return "slow"
    if mode == "challenger":
        return "natural"
    return "natural"


def _mode_to_mood(mode: str | None) -> str:
    """A gentle visual mood hint for ambient background color regulation."""
    if mode in {"practical", "strategist"}:
        return "focused"
    if mode == "motivator":
        return "happy"
    if mode == "challenger":
        return "annoyed"
    if mode == "reflective":
        return "reflective"
    if mode == "listener":
        return "calm"
    return "calm"


def _mood_to_palette(mood: str | None) -> str:
    mapping = {
        "calm": "calm-blue",
        "happy": "warm-pink",
        "love": "warm-pink",
        "focused": "focus-cyan",
        "reflective": "reflective-indigo",
        "sad": "reflective-indigo",
        "stressed": "calm-teal",
        "anxious": "calm-teal",
        "annoyed": "muted-amber",
        "angry": "muted-amber",
    }
    return mapping.get(mood or "", "calm-blue")


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
    """Load only the latest chat window for Claude.

    Long-running Main Chat can have hundreds of messages. Loading all of them
    before trim_history() makes every send slower. We fetch the newest messages
    first, limit at the database, then reverse so Claude still receives
    oldest-first order within the active window.
    """
    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("messages")
            .select("role, content, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(CHAT_HISTORY_LOAD_LIMIT)
            .execute()
        )
    )

    rows = list(reversed(result.data or []))
    return [{"role": m["role"], "content": m["content"]} for m in rows]


@router.post("/chat")
async def chat(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    # M31D — one lightweight facade per turn. At this phase it owns only
    # WorkingMemoryState lifecycle and cognitive-trace delegation.
    _cognitive_runtime = cognitive_runtime.create_cognitive_runtime(
        trace_logging_enabled=settings.COGNITIVE_TRACE_LOG,
        trace_preview_policy=settings.COGNITIVE_TRACE_PREVIEW_POLICY,
        logger=log,
    )

    # === Parallel phase 1: transport work + one cognitive source fan-in ===
    (
        convo_result,
        user_message_id,
        cognitive_sources,
        attachment_rows,
    ) = await asyncio.gather(
        _check_ownership(
            supabase,
            body.conversation_id,
            user_id,
        ),
        _save_user_message(
            supabase,
            body.conversation_id,
            body.message,
        ),
        _cognitive_runtime.retrieve_turn_context_sources(
            user_id=user_id,
            user_message=body.message,
            conversation_id=body.conversation_id,
        ),
        asyncio.to_thread(
            lambda: attachments.fetch_for_user(
                user_id=user_id,
                attachment_ids=body.attachment_ids,
            )
        ),
    )

    context = cognitive_sources.life_context
    memory_assembly = cognitive_sources.memory_assembly
    detected_mode = cognitive_sources.detected_mode
    companion_settings_row = (
        cognitive_sources.companion_settings_row
    )
    current_mood = cognitive_sources.current_mood
    user_mood_ctx = (
        cognitive_sources.user_mood_context
    )
    latest_briefing_for_prompt = (
        cognitive_sources.latest_briefing_for_prompt
    )

    if not convo_result or not convo_result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    legacy_memories = memory_assembly.legacy_memories
    related_summaries = memory_assembly.related_summaries

    # Link attachments to the saved user message (still pending until now).
    if attachment_rows:
        await asyncio.to_thread(
            lambda: attachments.link_to_message(
                user_id=user_id,
                attachment_ids=[r["id"] for r in attachment_rows],
                message_id=user_message_id,
            )
        )

    # Assistant display name now comes from companion_settings, not identity.
    assistant_rename = _extract_assistant_name(body.message)
    if assistant_rename:
        # Persist rename via companion service. Background task — user shouldn't
        # wait on it.
        add_safe_background_task(background_tasks, 
            companion.update_settings,
            user_id,
            assistant_name=assistant_rename,
        )
        assistant_name = assistant_rename
    else:
        assistant_name = companion_settings_row.get("assistant_name") or "Assistant"

    preferences = (companion_settings_row or {}).get("preferences") or {}
    assistant_mode = (
        str(preferences.get("assistant_mode") or "life_companion").lower().strip()
        if isinstance(preferences, dict)
        else "life_companion"
    )
    if assistant_mode not in {"life_companion", "chief_of_staff"}:
        assistant_mode = "life_companion"

    assistant_mode_execution = (
        await _cognitive_runtime.execute_assistant_mode_command(
            user_id=user_id,
            user_message=body.message,
            previous_mode=assistant_mode,
        )
    )

    if assistant_mode_execution:
        assistant_text = (
            assistant_mode_execution
            .assistant_text
        )

        return StreamingResponse(
            _stream_static_assistant_response(
                assistant_text=assistant_text,
                assistant_name=assistant_name,
                detected_mode=detected_mode,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": (
                    "no-cache, no-transform"
                ),
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
            background=background_tasks,
        )

    chronology_context = (
        await _cognitive_runtime.retrieve_conversation_chronology_context(
            user_id=user_id,
            query_text=body.message,
        )
    )

    history_started_at = time.perf_counter()

    # === Phase 2: recent history window (must be after save) ===
    messages = await _load_history(supabase, body.conversation_id)
    messages = trim_history(messages)
    history_elapsed_ms = round((time.perf_counter() - history_started_at) * 1000, 1)

    comeback_affect_decision = await _cognitive_runtime.evaluate_comeback_affect(
        user_id=user_id,
        conversation_id=body.conversation_id,
        user_message=body.message,
        companion_settings_row=companion_settings_row,
        assistant_mode=assistant_mode,
        assistant_name=assistant_name,
        user_mood_context=user_mood_ctx,
    )

    # M31E-FINAL — foreground executive routing belongs to CognitiveRuntime.
    calendar_execution = (
        await _cognitive_runtime.execute_calendar_turn(
            user_id=user_id,
            conversation_id=body.conversation_id,
            user_message=body.message,
            client_context=body.client_context,
            recent_messages=messages,
            assistant_mode=assistant_mode,
        )
    )

    if calendar_execution.receipt_text:
        return StreamingResponse(
            _stream_static_assistant_response(
                assistant_text=(
                    calendar_execution
                    .receipt_text
                ),
                assistant_name=assistant_name,
                detected_mode=detected_mode,
                assistant_mode=assistant_mode,
                conversation_id=(
                    body.conversation_id
                ),
                calendar_snapshot_dirty=(
                    calendar_execution
                    .receipt_snapshot_dirty
                ),
                calendar_receipt_source=(
                    calendar_execution
                    .receipt_source
                ),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": (
                    "no-cache, no-transform"
                ),
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
            background=background_tasks,
        )

    is_calendar_draft_action_turn = (
        calendar_execution
        .is_draft_action_turn
    )

    calendar_action_result = (
        calendar_execution
        .action_result
    )

    calendar_confirmation_result = (
        calendar_execution
        .confirmation_result
    )

    calendar_action_snapshot_dirty = (
        calendar_execution
        .action_snapshot_dirty
    )

    # M31E-FINAL — complete cognitive turn context + model input preparation.
    style_profile_id = (
        convo_result.data.get(
            "style_profile_id"
        )
    )

    generation_context = (
        await _cognitive_runtime.prepare_generation_context(
            body=body,
            user_id=user_id,
            context=context,
            chronology_context=chronology_context,
            assistant_mode=assistant_mode,
            assistant_name=assistant_name,
            assistant_rename=assistant_rename,
            current_mood=current_mood,
            user_mood_ctx=user_mood_ctx,
            latest_briefing_for_prompt=(
                latest_briefing_for_prompt
            ),
            comeback_affect_decision=(
                comeback_affect_decision
            ),
            messages=messages,
            companion_settings_row=(
                companion_settings_row
            ),
            detected_mode=detected_mode,
            style_profile_id=style_profile_id,
            calendar_action_result=(
                calendar_action_result
            ),
            is_calendar_draft_action_turn=(
                is_calendar_draft_action_turn
            ),
            legacy_memories=legacy_memories,
            related_summaries=related_summaries,
            memory_assembly=memory_assembly,
            turn_ref=user_message_id,
            logger=timing_log,
        )
    )

    volatile_context = (
        generation_context
        .volatile_context
    )

    packed_memory_context = (
        generation_context
        .packed_memory_context
    )

    pending_calendar_confirmation_context = (
        generation_context
        .pending_calendar_confirmation_context
    )

    is_calendar_candidate_turn = (
        generation_context
        .is_calendar_candidate_turn
    )

    style_audit = (
        generation_context
        .style_audit
    )

    companion_audit = (
        generation_context
        .companion_audit
    )

    system_blocks = (
        generation_context
        .system_blocks
    )

    timing_log.info(
        "chat: user=%s %s",
        user_id[:8],
        memory.build_retrieval_diagnostics(legacy_memories, related_summaries),
    )

    timing_log.info(
        "chat: user=%s context_keys=%s legacy_mems=%d related_summaries=%d history_len=%d history_ms=%.1f attachments=%d mode=%s style=%s %s",
        user_id[:8],
        list(context.keys()),
        len(legacy_memories),
        len(related_summaries),
        len(messages),
        history_elapsed_ms,
        len(attachment_rows),
        detected_mode,
        style_audit,
        companion_audit,
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

    # M31C — one immutable, request-scoped snapshot of state that the
    # current chat runtime has already produced. It is intentionally not
    # consumed by prompt construction, response generation, policy, or
    # persistence in M31C.
    _working_memory_state = _cognitive_runtime.build_working_memory(
        user_ref=user_id,
        conversation_ref=body.conversation_id,
        turn_ref=user_message_id,
        history_message_count=len(messages),
        is_first_message=is_first_message,
        history_load_latency_ms=history_elapsed_ms,
        assistant_mode=assistant_mode,
        detected_mode=detected_mode,
        companion_settings_row=companion_settings_row,
        current_mood=current_mood,
        user_mood_context=user_mood_ctx,
        client_context=body.client_context,
        memory_assembly=memory_assembly,
        packed_memory_context=packed_memory_context,
        calendar_draft_action_turn=is_calendar_draft_action_turn,
        calendar_candidate_turn=is_calendar_candidate_turn,
        calendar_action_result=calendar_action_result,
        calendar_confirmation_result=calendar_confirmation_result,
        calendar_candidate_result=None,
        calendar_snapshot_dirty=bool(
            calendar_action_snapshot_dirty
            or (
                calendar_confirmation_result
                and calendar_confirmation_result.get("executed")
            )
        ),
        attachment_rows=attachment_rows,
        life_context_keys=(
            tuple(context.keys())
            if isinstance(context, dict)
            else ()
        ),
        chronology_context_present=bool(
            chronology_context
        ),
        pending_calendar_context_present=bool(
            pending_calendar_confirmation_context
        ),
        latest_briefing_present=bool(
            latest_briefing_for_prompt
        ),
        volatile_context_chars=len(
            volatile_context
        ),
    )

    _metacognitive_finalization = (
        _cognitive_runtime.finalize_metacognitive_turn(
            working_state=_working_memory_state,
            legacy_memories=legacy_memories,
            user_message=body.message,
            recent_messages=messages,
            turn_ref=user_message_id,
            conversation_ref=body.conversation_id,
            user_ref=user_id,
            assistant_mode=assistant_mode,
            companion_settings_row=companion_settings_row,
            comeback_affect_decision=(
                comeback_affect_decision
            ),
            packed_memory_context=(
                packed_memory_context
            ),
            memory_retrieval_diagnostics=(
                memory_assembly
                .memory_retrieval_diagnostics
            ),
        )
    )

    for _runtime_directive in (
        _metacognitive_finalization.prompt_directive,
        _metacognitive_finalization.attention_prompt_directive,
    ):
        if _runtime_directive:
            system_blocks = [
                *system_blocks,
                {
                    "type": "text",
                    "text": _runtime_directive,
                },
            ]

    return StreamingResponse(
        _stream_claude_response(
            user_id=user_id,
            conversation_id=body.conversation_id,
            messages=messages,
            system_blocks=system_blocks,
            user_message=body.message,
            client_context=body.client_context,
            background_tasks=background_tasks,
            is_first_message=is_first_message,
            detected_mode=detected_mode,
            assistant_name=assistant_name,
            user_mood_context=user_mood_ctx,
            assistant_mode=assistant_mode,
            calendar_action_turn=is_calendar_draft_action_turn,
            calendar_action_snapshot_dirty=calendar_action_snapshot_dirty,
            comeback_affect_decision=comeback_affect_decision,
            metacognitive_response_posture=(
                _metacognitive_finalization
                .decision
                .response_posture
            ),
            metacognitive_projection_posture=(
                _metacognitive_finalization
                .decision
                .durable_projection_posture
            ),
            metacognitive_allow_background_inference=(
                _metacognitive_finalization
                .decision
                .allow_background_inference
            ),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
        background=background_tasks,
    )










async def _stream_static_assistant_response(
    *,
    assistant_text: str,
    assistant_name: str,
    detected_mode: str | None = None,
    assistant_mode: str = "life_companion",
    conversation_id: str | None = None,
    calendar_snapshot_dirty: bool = False,
    calendar_receipt_source: str | None = None,
) -> AsyncIterator[str]:
    """Stream a deterministic assistant response without calling Claude."""
    mood = _mode_to_mood(detected_mode)
    meta_event = {
        "type": "meta",
        "mode": detected_mode or "assistant_mode_command",
        "assistant_mode": assistant_mode,
        "pacing": _mode_to_pacing(detected_mode),
        "mood": mood,
        "background_palette_hint": _mood_to_palette(mood),
        "assistant_name": assistant_name,
    }
    if calendar_receipt_source:
        meta_event["calendar_receipt_source"] = calendar_receipt_source
    yield f"data: {json.dumps(meta_event)}\n\n"
    yield f"data: {json.dumps({'type': 'delta', 'text': assistant_text})}\n\n"

    if assistant_text and conversation_id:
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

    if calendar_snapshot_dirty:
        yield f"data: {json.dumps({'type': 'meta', 'calendar_snapshot_dirty': True})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def _stream_claude_response(
    *,
    user_id: str,
    conversation_id: str,
    messages: list[dict],
    system_blocks: list[dict],
    user_message: str,
    client_context: dict | None = None,
    background_tasks: BackgroundTasks,
    is_first_message: bool,
    detected_mode: str | None = None,
    assistant_name: str = "Assistant",
    user_mood_context=None,
    assistant_mode: str = "life_companion",
    calendar_action_turn: bool = False,
    calendar_action_snapshot_dirty: bool = False,
    comeback_affect_decision: dict | None = None,
    metacognitive_response_posture: str = "proceed",
    metacognitive_projection_posture: str = "eligible",
    metacognitive_allow_background_inference: bool = True,
) -> AsyncIterator[str]:
    claude = get_claude()
    supabase = get_supabase()
    assistant_text = ""
    stream_started_at = time.perf_counter()
    first_token_logged = False

    mood = _mode_to_mood(detected_mode)
    meta_event = {
        "type": "meta",
        "mode": detected_mode or "unknown",
        "assistant_mode": assistant_mode,
        "pacing": _mode_to_pacing(detected_mode),
        "mood": mood,
        "background_palette_hint": _mood_to_palette(mood),
        "assistant_name": assistant_name,
    }
    yield f"data: {json.dumps(meta_event)}\n\n"
    try:
        async with claude.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_blocks,
            messages=messages,
        ) as stream:
            async for text_chunk in stream.text_stream:
                if not first_token_logged:
                    first_token_logged = True
                    timing_log.info(
                        "chat_timing: user=%s conversation=%s first_token_ms=%.1f history_len=%d",
                        user_id[:8],
                        conversation_id[:8],
                        (time.perf_counter() - stream_started_at) * 1000,
                        len(messages),
                    )

                assistant_text += text_chunk
                yield f"data: {json.dumps({'type': 'delta', 'text': text_chunk})}\n\n"
    except Exception:  # noqa: BLE001
        log.exception(
            "chat: streaming failed user=%s conversation=%s",
            user_id[:8],
            conversation_id[:8],
        )
        friendly_name = assistant_name.strip() if assistant_name else "Aliyya"
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "error",
                    "message": f"Maaf, respons {friendly_name} sempat terputus. Coba kirim lagi ya.",
                }
            )
            + "\n\n"
        )
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

        if (
            comeback_affect_decision
            and comeback_affect_decision.get(
                "expression_policy"
            ) == "one_short_warm_line"
        ):
            add_safe_background_task(
                background_tasks,
                companion_comeback_affect.mark_used,
                user_id,
                comeback_affect_decision,
            )

    extraction_decision = background_extraction_gate.decide(
        user_message=user_message,
        assistant_response=assistant_text,
        recent_messages=[
            *messages,
            {"role": "assistant", "content": assistant_text},
        ],
        is_first_message=is_first_message,
    )

    # Legacy memory extraction is now gated because memory_intelligence is the
    # primary structured extractor. This prevents duplicate durable memories.
    if (
        metacognitive_allow_background_inference
        and extraction_decision.run_legacy_memory
    ):
        add_safe_background_task(background_tasks, 
            memory.extract_and_save,
            user_id=user_id,
            conversation_id=conversation_id,
            recent_messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_text},
            ],
        )

    # Structured memory intelligence — identity/preferences/routines/dates/etc.
    if extraction_decision.run_memory_intelligence:
        add_safe_background_task(background_tasks, 
            memory_intelligence.extract_and_persist,
            user_id=user_id,
            conversation_id=conversation_id,
            recent_messages=[
                *messages,
                {"role": "assistant", "content": assistant_text},
            ],
            projection_posture=(
                metacognitive_projection_posture
            ),
        )

    # Mood-memory feedback — only when debugging/frustration/support-style signal exists.
    if (
        metacognitive_allow_background_inference
        and extraction_decision.run_mood_memory_feedback
    ):
        add_safe_background_task(background_tasks, 
            mood_memory_feedback.extract_and_persist,
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_text,
            user_mood_context=user_mood_context,
        )

    # Relationship memory — only when user gives interaction-style or Aliyya-specific signal.
    if (
        metacognitive_allow_background_inference
        and extraction_decision.run_relationship_memory
    ):
        add_safe_background_task(background_tasks, 
            relationship_memory.extract_and_persist,
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_text,
        )

    # Goal intelligence — only on goal-like turns. Suggestions still require confirmation.
    if (
        metacognitive_allow_background_inference
        and extraction_decision.run_goal_intelligence
    ):
        add_safe_background_task(background_tasks, 
            goal_intelligence.extract_and_persist,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_response=assistant_text,
        )

    # A direct update/delete turn has already been handled authoritatively.
    # Do not also route it as confirmation for an unrelated pending suggestion.
    if not calendar_action_turn:
        add_safe_background_task(
            background_tasks,
            calendar_confirmation_actions.apply_calendar_confirmation_decision,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            client_context=client_context,
            recent_messages=[
                *messages,
                {"role": "assistant", "content": assistant_text},
            ],
        )

    should_schedule_proactive_nudge = (
        not calendar_action_turn
        and metacognitive_allow_background_inference
        and proactive_nudges.should_attempt_proactive_nudge(
            user_message
        )
    )
    if should_schedule_proactive_nudge:
        add_safe_background_task(background_tasks, 
            proactive_nudges.schedule_from_chat,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            client_context=client_context,
            assistant_response=assistant_text,
        )

    # Calendar update/delete actions were already executed before streaming.
    # Keep this flag only to suppress candidate extraction for the same turn.
    should_apply_calendar_draft_action = calendar_action_turn

    # Direct Google Calendar create from chat — only when the user explicitly asks for Google Calendar.
    should_create_google_calendar_event = calendar_draft_actions.is_google_calendar_create_request(
        user_message
    )
    if should_create_google_calendar_event:
        add_safe_background_task(background_tasks, 
            calendar_draft_actions.create_google_calendar_event_from_chat,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            client_context=client_context,
            recent_messages=[
                *messages,
                {"role": "assistant", "content": assistant_text},
            ],
        )

    # Calendar candidate extraction — deterministic/Haiku-assisted, review-first, never syncs directly.
    should_extract_calendar_candidate = (
        metacognitive_allow_background_inference
        and not should_schedule_proactive_nudge
        and not should_apply_calendar_draft_action
        and not should_create_google_calendar_event
        and not calendar_candidate_extractor.is_public_situational_update(user_message)
        and (
            extraction_decision.run_calendar_candidate_extraction
            or calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(user_message)
        )
    )
    if should_extract_calendar_candidate:
        add_safe_background_task(background_tasks, 
            calendar_candidate_extractor.extract_and_persist,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            client_context=client_context,
            recent_messages=[
                *messages,
                {"role": "assistant", "content": assistant_text},
            ],
        )

    calendar_snapshot_dirty = bool(
        calendar_action_snapshot_dirty
        or should_create_google_calendar_event
        or should_extract_calendar_candidate
    )
    if calendar_snapshot_dirty:
        yield f"data: {json.dumps({'type': 'meta', 'calendar_snapshot_dirty': True})}\n\n"


    # Background conversation-summary update. Idempotent — only runs Haiku
    # if the conversation has grown ≥N messages since last summarize.
    add_safe_background_task(background_tasks, 
        conversation_summary.summarize_conversation,
        conversation_id=conversation_id,
    )

    # Background title generation on first message
    if is_first_message and assistant_text:
        add_safe_background_task(background_tasks, 
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
