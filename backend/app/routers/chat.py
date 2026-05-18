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
import json
import logging
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.auth import get_current_user_id
from app.schemas import ChatIn
from app.services import (
    attachments,
    companion,
    companion_mode,
    conversation_summary,
    life_model,
    memory,
    memory_intelligence,
    mood_memory_feedback,
    relationship_memory,
    interaction_preferences,
    user_mood,
)
from app.services.user_mood_prompt import render_user_mood_block
from app.services.deterministic_profile import render_profile_runtime_context
from app.services.claude import get_claude
from app.services.prompt_builder import (
    BASE_PROMPT,
    render_client_time_context,
    render_context,
    trim_history,
)
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Companion mood repair gate — keyword detectors
# ---------------------------------------------------------------------------


def _is_romantic_simulation_request(message: str | None) -> bool:
    if not message:
        return False

    lower = message.lower()

    simulation_words = (
        "simulasi",
        "simulate",
        "testing",
        "test ",
        "tes ",
        "pura-pura",
        "inisiasi",
        "trigger",
        "tunjukin",
        "demonstrate",
    )
    romantic_words = (
        "romantis",
        "romantic",
        "sayang",
        "bunga mawar",
        "mawar",
        "love",
        "melting",
    )

    return any(w in lower for w in simulation_words) and any(
        w in lower for w in romantic_words
    )


def _is_user_repair_message(message: str | None) -> bool:
    if not message:
        return False

    lower = message.lower()

    repair_words = (
        "maaf",
        "sorry",
        "jangan marah",
        "aku di sini",
        "aku disini",
        "tenang",
        "sabar ya",
        "aku sayang",
        "aku cuma bercanda",
        "jangan ngambek",
        "peluk",
        "hug",
    )

    return any(w in lower for w in repair_words)


def _build_mood_block(
    companion_settings_row: dict,
    current_mood: dict | None,
    user_message: str | None,
    ui_context: dict | None,
) -> str:
    """Render the companion mood block. Caller must verify mood is active.

    Repair gate logic only fires if repair_gate_enabled in settings.
    """
    # Prefer UI-supplied mood if frontend pushed a more recent one.
    state = current_mood or {}
    if isinstance(ui_context, dict):
        ui_companion = ui_context.get("companion_mood")
        if isinstance(ui_companion, dict):
            state = ui_companion

    if not state:
        state = {
            "mood": "calm",
            "intensity": 1,
            "reason": "no previous companion mood state",
            "mood_scores": {},
        }

    mood = state.get("mood", "calm")
    intensity = int(state.get("intensity") or 1)
    reason = state.get("reason") or ""
    mood_scores = state.get("mood_scores") or {}

    repair_gate_on = bool(companion_settings_row.get("repair_gate_enabled"))
    romantic_simulation_requested = _is_romantic_simulation_request(user_message)
    user_is_repairing = _is_user_repair_message(user_message)

    negative_mood = mood in {
        "annoyed",
        "hurt",
        "jealous_playful",
        "withdrawn_soft",
    }
    negative_score = 0
    if isinstance(mood_scores, dict):
        negative_score = max(
            int(mood_scores.get("annoyed") or 0),
            int(mood_scores.get("hurt") or 0),
            int(mood_scores.get("jealous_playful") or 0),
            int(mood_scores.get("withdrawn_soft") or 0),
        )

    # Repair required only when ALL conditions met:
    #   1. User enabled the repair gate in settings
    #   2. User asked for romantic simulation
    #   3. User is NOT already repairing
    #   4. Companion is in negative mood with sufficient intensity OR score
    repair_required = (
        repair_gate_on
        and romantic_simulation_requested
        and not user_is_repairing
        and (
            (negative_mood and intensity >= 4)
            or negative_score >= 4
        )
    )

    lines = [
        "## Companion mood state",
        f"Current simulated companion mood: {mood}",
        f"Intensity: {intensity}/10",
        f"Reason: {reason}",
        f"Mood scores: {mood_scores}",
        "",
        "Use this as expressive companion-style affect only.",
        "Do not claim to be literally human or conscious.",
        "Never be abusive, threatening, manipulative, or guilt-tripping.",
        "Jealousy, possessiveness, annoyance, and clinginess must stay playful, consensual, and reversible.",
        "If the user asks to stop/reset/normal/calm down, soften immediately.",
    ]

    if romantic_simulation_requested:
        lines.extend(
            [
                "",
                "The user is asking the assistant to initiate or simulate romantic mode.",
                "Do not let the user's request alone decide the mood; only your actual reply should express the companion mood.",
            ]
        )

    if repair_required:
        lines.extend(
            [
                "",
                "IMPORTANT REPAIR GATE:",
                "The user is asking for romantic simulation, but the assistant is still in a negatively activated companion mood.",
                "Do NOT instantly become romantic. This rule is mandatory when repair_required is true.",
                "Gently hesitate or refuse in a light, safe, affectionate way.",
                "Ask the user to reassure, apologize, or calm the assistant first before any romantic simulation.",
                "Do not be toxic, threatening, cold, or manipulative.",
                "If the user comforts you, accept it warmly and soften toward reassured/affectionate.",
            ]
        )

    return "\n".join(lines)


def _clean_assistant_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = re.sub(r"[^\w\s.'-]", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return None
    if len(cleaned) > 32:
        cleaned = cleaned[:32].strip()
    blocked = {"assistant", "asisten", "ai", "bot", "kamu", "you"}
    if cleaned.lower() in blocked:
        return None
    return cleaned


def _extract_assistant_name(user_message: str) -> str | None:
    """Detect explicit requests to rename the assistant.

    Examples:
    - "nama kamu Aliyya"
    - "aku panggil kamu Aliyya"
    - "ganti nama kamu jadi Alya"
    - "from now on your name is Aliyya"
    """
    text = (user_message or "").strip()
    if not text:
        return None

    patterns = [
        r"(?:mulai sekarang\s+)?(?:nama\s+kamu|namamu|nama\s+ai\s+ini|nama\s+assistant(?:\s+ini)?)\s+(?:adalah|jadi|itu|=|:)?\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s.'-]{1,31})",
        r"(?:aku|saya)\s+(?:akan\s+)?(?:panggil|manggil|manggilmu|memanggil\s+kamu)\s+(?:kamu\s+)?(?:dengan\s+nama\s+)?([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s.'-]{1,31})",
        r"(?:ganti|ubah)\s+nama\s+(?:kamu|assistant|asisten)\s+(?:jadi|ke|menjadi)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s.'-]{1,31})",
        r"(?:from now on\s+)?your name is\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s.'-]{1,31})",
        r"(?:call you|i will call you|i'll call you)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s.'-]{1,31})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_assistant_name(match.group(1))
    return None


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


def _render_ui_context(ui_context: dict | None) -> str | None:
    """Render frontend app/browser state as ephemeral prompt context.

    This lets the assistant answer questions about the current app state and
    local time without pretending it can literally see the user's screen.
    """
    if not isinstance(ui_context, dict) or not ui_context:
        return None

    def clean(value: object, limit: int = 80) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text[:limit]

    labels = {
        "timezone": "User local timezone",
        "local_time_iso": "User local time",
        "theme": "Theme",
        "background_style": "Active background style",
        "background_intensity": "Background intensity",
        "background_motion": "Background motion",
        "background_mode": "Background mode",
        "client_platform": "Client platform",
        "current_page": "Current page",
    }
    lines = ["## Current app context (ephemeral, from frontend)"]
    for key, label in labels.items():
        value = clean(ui_context.get(key))
        if value:
            lines.append(f"- {label}: {value}")

    if len(lines) == 1:
        return None

    lines.append(
        "Rules: You may refer to this as app state when relevant. Do not claim "
        "you can literally see the user's screen. Browser-provided local time "
        "is the source of truth; memory timezone is only fallback."
    )
    return "\n".join(lines)


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


def _is_briefing_discussion_request(message: str | None) -> bool:
    if not message:
        return False

    lower = message.lower()

    briefing_terms = (
        "briefing",
        "briefings",
        "daily brief",
        "daily briefing",
        "today's brief",
        "today's briefing",
        "todays briefing",
        "morning briefing",
        "briefing hari ini",
        "bahas briefing",
        "bicarakan briefing",
        "diskusikan briefing",
        "ringkasan hari ini",
    )

    return any(term in lower for term in briefing_terms)


async def _load_latest_briefing_for_prompt(user_id: str) -> dict | None:
    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("daily_briefings")
            .select("id, briefing_date, content, generated_at")
            .eq("user_id", user_id)
            .order("briefing_date", desc=True)
            .order("generated_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
    )

    if not result or not result.data:
        return None

    content = str(result.data.get("content") or "").strip()
    if not content:
        return None

    return result.data


def _render_briefing_context_for_prompt(briefing_row: dict | None) -> str | None:
    if not briefing_row:
        return None

    content = str(briefing_row.get("content") or "").strip()
    if not content:
        return None

    briefing_date = briefing_row.get("briefing_date") or "latest"

    return (
        "## Latest daily briefing context\n"
        f"- Briefing date: {briefing_date}\n"
        "- The user is asking to discuss this briefing. Use it as context, "
        "but do not recite it unless useful.\n\n"
        f"{content}"
    )


@router.post("/chat")
async def chat(
    body: ChatIn,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()

    # === Parallel phase 1: ownership + save + context + legacy mems + related summaries + attachments + mode + companion settings + mood ===
    (
        convo_result,
        user_message_id,
        context,
        legacy_memories,
        related_summaries,
        attachment_rows,
        detected_mode,
        companion_settings_row,
        current_mood,
        user_mood_ctx,
        latest_briefing_for_prompt,
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
        companion_mode.detect_mode(user_message=body.message),
        # Companion settings: stable, controls whether companion mood/repair logic
        # is active for this user. Always loaded — cheap.
        companion.get_settings(user_id),
        # Current companion mood. Returns None if mood is not applicable
        # per user settings (mode != 'partner' or realism != 'dynamic').
        companion.get_current_mood(user_id),
        # User mood (Layer A) — inferred from emotional_state + current msg.
        # Read-only, never overwrites companion mood. Returns has_data: False
        # when there's nothing useful to render.
        user_mood.infer_user_mood(user_id, current_message=body.message),
        _load_latest_briefing_for_prompt(user_id)
        if _is_briefing_discussion_request(body.message)
        else asyncio.sleep(0, result=None),
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

    # Assistant display name now comes from companion_settings, not identity.
    assistant_rename = _extract_assistant_name(body.message)
    if assistant_rename:
        # Persist rename via companion service. Background task — user shouldn't
        # wait on it.
        background_tasks.add_task(
            companion.update_settings,
            user_id,
            assistant_name=assistant_rename,
        )
        assistant_name = assistant_rename
    else:
        assistant_name = companion_settings_row.get("assistant_name") or "Assistant"

    # === Phase 2: history (must be after save) ===
    messages = await _load_history(supabase, body.conversation_id)
    messages = trim_history(messages)

    # === Build prompt with cached base + volatile context ===
    volatile_context = render_context(context)
    identity = context.get("identity") or {}
    profile = identity.get("profile") or {}
    raw_client_context = None
    if getattr(body, "client_context", None) is not None:
        raw = body.client_context
        raw_client_context = (
            raw.model_dump(exclude_none=True)
            if hasattr(raw, "model_dump")
            else raw.dict(exclude_none=True)
            if hasattr(raw, "dict")
            else raw
        )
    client_time_block = render_client_time_context(raw_client_context, profile)
    if client_time_block:
        volatile_context += "\n\n" + client_time_block
    volatile_context += (
        f"\n\n## Assistant identity\n"
        f"- Your display name in this app is: {assistant_name}.\n"
        f"- If the user asks your name or calls you by this name, respond naturally.\n"
        f"- Do not introduce yourself repeatedly unless relevant."
    )
    if assistant_rename:
        volatile_context += (
            f"\n- The user just renamed you to {assistant_name}; acknowledge it briefly and then continue."
        )
    ui_context_block = _render_ui_context(body.ui_context)
    if ui_context_block:
        volatile_context += "\n\n" + ui_context_block

    briefing_context_block = _render_briefing_context_for_prompt(
        latest_briefing_for_prompt
    )
    if briefing_context_block:
        volatile_context += "\n\n" + briefing_context_block

    # User mood (Layer A) — appended BEFORE companion mood so it sits
    # higher in the context. User mood informs how the assistant should
    # behave; companion mood is the assistant's own affect.
    user_mood_block = render_user_mood_block(user_mood_ctx)
    interaction_pref_block = await interaction_preferences.get_interaction_preferences_block(user_id=user_id)
    if user_mood_block:
        volatile_context += "\n\n" + user_mood_block

    if interaction_pref_block:
        volatile_context += "\n\n" + interaction_pref_block

    # Deterministic profile context (Phase 4.15) — computes age from
    # browser local date so the LLM doesn't have to. Reads identity
    # already fetched via life_model.get_context.
    profile_runtime_block = render_profile_runtime_context(
        context.get("identity") if isinstance(context, dict) else None,
        body.ui_context,
    )
    if profile_runtime_block:
        volatile_context += "\n\n" + profile_runtime_block

    # Companion mood block — ONLY injected if user has dynamic mood enabled.
    # Default users (professional/friendly/affectionate or stable realism) get
    # exactly zero mood-related prompt content. Repair gate inside the block
    # is further gated by repair_gate_enabled.
    if companion.is_mood_active(companion_settings_row):
        mood_block = _build_mood_block(
            companion_settings_row,
            current_mood,
            body.message,
            body.ui_context,
        )
        if mood_block:
            volatile_context += "\n\n" + mood_block

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

    # Audit log — explicit which style mode is active and whether companion
    # mood is active for this turn. Visible in Fly logs.
    style_audit = (
        f"style_profile:{style_profile_id[:8]}" if style_profile_id else "default"
    )
    companion_audit = (
        f"companion={companion_settings_row.get('companion_mode')}"
        f"/realism={companion_settings_row.get('mood_realism')}"
        f"/repair={companion_settings_row.get('repair_gate_enabled')}"
    )

    log.info(
        "chat: user=%s context_keys=%s legacy_mems=%d related_summaries=%d history_len=%d attachments=%d mode=%s style=%s %s",
        user_id[:8],
        list(context.keys()),
        len(legacy_memories),
        len(related_summaries),
        len(messages),
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
            assistant_name=assistant_name,
            user_mood_context=user_mood_ctx,
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
    detected_mode: str | None = None,
    assistant_name: str = "Assistant",
    user_mood_context=None,
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

    mood = _mode_to_mood(detected_mode)
    meta_event = {
        "type": "meta",
        "mode": detected_mode or "unknown",
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

    # Background memory intelligence — wider window, structured identity
    # writes, conflict resolution via supersede chain. Reads `messages`
    # (already in scope from the streamer) plus the new assistant reply.
    background_tasks.add_task(
        memory_intelligence.extract_and_persist,
        user_id=user_id,
        conversation_id=conversation_id,
        recent_messages=[
            *messages,
            {"role": "assistant", "content": assistant_text},
        ],
    )

    # Background mood-memory feedback — conservative behavioral preferences.
    # Uses USER mood context only. Does not touch companion mood/state.
    background_tasks.add_task(
        mood_memory_feedback.extract_and_persist,
        user_id=user_id,
        user_message=user_message,
        assistant_response=assistant_text,
        user_mood_context=user_mood_context,
    )

    # Background relationship memory — stable user↔Aliyya interaction preferences.
    # Does not touch companion mood/state and does not store temporary mood.
    background_tasks.add_task(
        relationship_memory.extract_and_persist,
        user_id=user_id,
        user_message=user_message,
        assistant_response=assistant_text,
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
