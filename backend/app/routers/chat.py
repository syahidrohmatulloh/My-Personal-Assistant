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
    conversation_chronology,
    capability_registry,
    attachments,
    companion,
    companion_mode,
    conversation_summary,
    life_model,
    memory,
    memory_intelligence,
    proactive_nudges,
    name_normalization,
    temporal_grounding,
    background_extraction_gate,
    goal_intelligence,
    mood_memory_feedback,
    relationship_memory,
    response_texture,
    interaction_preferences,
    user_mood,
)
from app.services.user_mood_prompt import render_user_mood_block
from app.services.deterministic_profile import render_profile_runtime_context
from app.services.claude import get_claude
from app.services.prompt_builder import (
    BASE_PROMPT,
    get_base_prompt,
    render_client_time_context,
    render_context,
    trim_history,
)
from app.services.supabase_client import get_supabase, safe_execute
from app.services.safe_background import add_safe_background_task
from app.services.assistant_mode_commands import (
    detect_assistant_mode_command,
    render_mode_command_confirmation,
)

log = logging.getLogger(__name__)
timing_log = logging.getLogger("uvicorn.error")
CHAT_HISTORY_LOAD_LIMIT = 80

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


def _context_to_dict(value: object) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else None
    if hasattr(value, "dict"):
        dumped = value.dict(exclude_none=True)
        return dumped if isinstance(dumped, dict) else None
    return None


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


async def _safe_life_model_context(user_id: str, *, mood_days: int = 14) -> dict:
    try:
        context = await life_model.get_context(user_id, mood_days=mood_days)
        return context if isinstance(context, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("life_model.get_context failed user=%s: %s", user_id[:8], exc)
        return {}


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



def _parse_client_local_time(raw_client_context: dict | None) -> tuple[datetime | None, str | None]:
    if not isinstance(raw_client_context, dict):
        return None, None

    local_time = str(raw_client_context.get("local_time") or "").strip()
    timezone = str(raw_client_context.get("timezone") or "").strip() or None

    if not local_time:
        return None, timezone

    # Frontend sends stable browser-local format: YYYY-MM-DD HH:mm:ss.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(local_time[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S"), timezone
        except ValueError:
            continue

    return None, timezone


def _interpret_hour_with_period(hour: int, period: str | None, now: datetime) -> int:
    period = (period or "").lower().strip()

    if period in {"pagi", "morning"}:
        if hour == 12:
            return 0
        return hour

    if period in {"siang", "afternoon"}:
        if hour == 12:
            return 12
        return hour + 12 if 1 <= hour <= 4 else hour

    if period in {"sore", "evening"}:
        if hour == 12:
            return 12
        return hour + 12 if 1 <= hour <= 7 else hour

    if period in {"malam", "night"}:
        if hour == 12:
            return 0
        return hour + 12 if 1 <= hour <= 11 else hour

    # No explicit period: choose the nearest plausible upcoming time today.
    # This handles Indonesian shorthand like "jam 5" when current time is 15:00
    # by interpreting it as 17:00, not 05:00 tomorrow.
    if 1 <= hour <= 11:
        am_candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        pm_candidate = now.replace(hour=hour + 12, minute=0, second=0, microsecond=0)

        if am_candidate >= now:
            return hour
        if pm_candidate >= now:
            return hour + 12

    return hour


def _extract_mentioned_times(message: str | None, now: datetime) -> list[dict]:
    if not message:
        return []

    text = message.lower()
    results: list[dict] = []

    # Examples:
    # - jam 5 sore
    # - jam 1 siang
    # - jam 12.30
    # - pukul 17:00
    pattern = re.compile(
        r"\b(?:jam|pukul)\s*([0-2]?\d)(?:[:.]([0-5]\d))?\s*(pagi|siang|sore|malam|morning|afternoon|evening|night)?\b",
        re.IGNORECASE,
    )

    for match in pattern.finditer(text):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)

        if hour > 23 or minute > 59:
            continue

        interpreted_hour = _interpret_hour_with_period(hour, period, now)
        if interpreted_hour > 23:
            continue

        target = now.replace(
            hour=interpreted_hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        # If already passed by more than 30 minutes, assume next day.
        if target < now - timedelta(minutes=30):
            target = target + timedelta(days=1)

        delta = target - now
        total_minutes = round(delta.total_seconds() / 60)

        if total_minutes >= 0:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            if hours and minutes:
                remaining = f"{hours} jam {minutes} menit"
            elif hours:
                remaining = f"{hours} jam"
            else:
                remaining = f"{minutes} menit"
        else:
            remaining = f"sudah lewat sekitar {abs(total_minutes)} menit"

        results.append(
            {
                "phrase": match.group(0),
                "interpreted_time": target.strftime("%Y-%m-%d %H:%M"),
                "remaining": remaining,
                "minutes_remaining": total_minutes,
            }
        )

    return results[:3]


def _is_time_sensitive_message(message: str | None) -> bool:
    if not message:
        return False

    lower = message.lower()
    keywords = (
        "jam",
        "pukul",
        "meeting",
        "rapat",
        "jadwal",
        "deadline",
        "nanti",
        "sore",
        "siang",
        "malam",
        "pagi",
        "berapa lama",
        "berapa jam",
        "berapa menit",
        "sebentar lagi",
        "otw",
    )
    return any(keyword in lower for keyword in keywords)


def _render_time_sensitive_calculation_block(
    user_message: str | None,
    raw_client_context: dict | None,
) -> str | None:
    if not _is_time_sensitive_message(user_message):
        return None

    now, timezone = _parse_client_local_time(raw_client_context)
    if not now:
        return None

    mentioned_times = _extract_mentioned_times(user_message, now)

    lines = [
        "## Deterministic local-time calculation — highest priority",
        f"- Browser local time now: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        + (f" ({timezone})" if timezone else ""),
        "- Use this calculated local time for any schedule/deadline/meeting reasoning in this turn.",
        "- Do not override this with memory, chat history, server time, or model guess.",
    ]

    if mentioned_times:
        lines.append("- Mentioned time calculations:")
        for item in mentioned_times:
            lines.append(
                f"  - User phrase '{item['phrase']}' => {item['interpreted_time']}"
                f"; remaining from browser local time: {item['remaining']}."
            )

    lines.append(
        "- When replying, if timing matters, state the calculation naturally and briefly."
    )

    return "\n".join(lines)


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
        _safe_life_model_context(user_id, mood_days=14),
        memory.retrieve_relevant(user_id, body.message, limit=12),
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

    assistant_mode_command = detect_assistant_mode_command(body.message)
    if assistant_mode_command:
        new_mode = assistant_mode_command.target_mode
        await companion.update_settings(user_id, assistant_mode=new_mode)

        assistant_text = render_mode_command_confirmation(
            assistant_mode_command,
            previous_mode=assistant_mode,  # type: ignore[arg-type]
        )

        await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("messages")
                .insert(
                    {
                        "conversation_id": body.conversation_id,
                        "role": "assistant",
                        "content": assistant_text,
                    }
                )
                .execute()
            )
        )

        return StreamingResponse(
            _stream_static_assistant_response(
                assistant_text=assistant_text,
                assistant_name=assistant_name,
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

    chronology_context = await conversation_chronology.build_context_if_relevant(
        user_id=user_id,
        query_text=body.message,
    )

    history_started_at = time.perf_counter()

    # === Phase 2: recent history window (must be after save) ===
    messages = await _load_history(supabase, body.conversation_id)
    messages = trim_history(messages)
    history_elapsed_ms = round((time.perf_counter() - history_started_at) * 1000, 1)

    # Calendar update/delete actions must complete before Claude writes the
    # user-facing response. The result below becomes authoritative prompt
    # context, so success wording always follows actual persistence.
    is_calendar_draft_action_turn = (
        calendar_draft_actions.is_calendar_draft_action_request(
            body.message
        )
    )
    calendar_action_result: dict[str, Any] | None = None

    if is_calendar_draft_action_turn:
        try:
            calendar_action_result = (
                await calendar_draft_actions.apply_chat_calendar_draft_action(
                    user_id=user_id,
                    conversation_id=body.conversation_id,
                    user_message=body.message,
                    client_context=body.client_context,
                    recent_messages=messages,
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "chat: authoritative calendar action failed "
                "user=%s conversation=%s error_type=%s",
                user_id[:8],
                body.conversation_id[:8],
                type(exc).__name__,
            )
            calendar_action_result = {
                "attempted": True,
                "success": False,
                "updated": False,
                "deleted": False,
                "action": "unknown",
                "source": "unknown",
                "reason": "calendar_action_exception",
            }

    calendar_action_success = (
        calendar_draft_actions.calendar_action_succeeded(
            calendar_action_result
        )
    )
    calendar_action_reason = str(
        (calendar_action_result or {}).get("reason") or ""
    )
    calendar_action_snapshot_dirty = bool(
        calendar_action_success
        or calendar_action_reason
        in {
            "local_update_after_google_patch_failed",
            "local_archive_after_google_delete_failed",
        }
    )

    calendar_address_term = await _load_calendar_address_term(
        user_id=user_id,
        assistant_mode=assistant_mode,
    )

    calendar_action_receipt = (
        calendar_draft_actions.render_calendar_action_user_receipt(
            calendar_action_result,
            address_term=calendar_address_term,
        )
    )
    if is_calendar_draft_action_turn and calendar_action_receipt:
        return StreamingResponse(
            _stream_static_assistant_response(
                assistant_text=calendar_action_receipt,
                assistant_name=assistant_name,
                detected_mode=detected_mode,
                assistant_mode=assistant_mode,
                conversation_id=body.conversation_id,
                calendar_snapshot_dirty=calendar_action_snapshot_dirty,
                calendar_receipt_source="deterministic_calendar_action",
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
            background=background_tasks,
        )

    if not is_calendar_draft_action_turn:
        calendar_confirmation_result = (
            await calendar_confirmation_actions.apply_calendar_confirmation_decision(
                user_id=user_id,
                conversation_id=body.conversation_id,
                user_message=body.message,
                client_context=body.client_context,
                recent_messages=messages,
            )
        )
        calendar_confirmation_receipt = (
            calendar_confirmation_actions.render_calendar_confirmation_user_receipt(
                calendar_confirmation_result,
                address_term=calendar_address_term,
            )
        )
        if calendar_confirmation_receipt:
            return StreamingResponse(
                _stream_static_assistant_response(
                    assistant_text=calendar_confirmation_receipt,
                    assistant_name=assistant_name,
                    detected_mode=detected_mode,
                    assistant_mode=assistant_mode,
                    conversation_id=body.conversation_id,
                    calendar_snapshot_dirty=bool(
                        calendar_confirmation_result.get("executed")
                    ),
                    calendar_receipt_source="deterministic_calendar_confirmation",
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
                background=background_tasks,
            )

    calendar_candidate_hard_gate = (
        not is_calendar_draft_action_turn
        and not calendar_draft_actions.is_google_calendar_create_request(body.message)
        and _should_hard_gate_calendar_candidate(body.message)
    )
    if calendar_candidate_hard_gate:
        calendar_candidate_result = (
            await calendar_candidate_extractor.extract_and_persist(
                user_id=user_id,
                conversation_id=body.conversation_id,
                user_message=body.message,
                client_context=body.client_context,
                recent_messages=messages,
            )
        )
        calendar_candidate_preview = (
            calendar_candidate_extractor.render_calendar_candidate_preview(
                calendar_candidate_result,
                address_term=calendar_address_term,
            )
        )
        if not calendar_candidate_preview:
            calendar_candidate_preview = _render_calendar_hard_gate_clarification(
                address_term=calendar_address_term,
            )

        return StreamingResponse(
            _stream_static_assistant_response(
                assistant_text=calendar_candidate_preview,
                assistant_name=assistant_name,
                detected_mode=detected_mode,
                assistant_mode=assistant_mode,
                conversation_id=body.conversation_id,
                calendar_snapshot_dirty=bool(
                    calendar_candidate_result.get("saved")
                ),
                calendar_receipt_source=(
                    "deterministic_candidate_preview"
                    if calendar_candidate_result.get("candidate")
                    else "deterministic_calendar_clarification"
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

    if (
        not is_calendar_draft_action_turn
        and calendar_draft_actions.is_google_calendar_create_request(body.message)
    ):
        google_create_result = (
            await calendar_draft_actions.create_google_calendar_event_from_chat(
                user_id=user_id,
                conversation_id=body.conversation_id,
                user_message=body.message,
                client_context=body.client_context,
                recent_messages=messages,
            )
        )

        if str(google_create_result.get("reason") or "") in {
            "no_confident_draft",
            "missing_required_fields",
        }:
            latest_local_google_sync_result = (
                await calendar_draft_actions.sync_latest_confirmed_local_event_to_google_from_chat(
                    user_id=user_id,
                    conversation_id=body.conversation_id,
                    user_message=body.message,
                )
            )
            latest_local_google_sync_receipt = (
                calendar_draft_actions.render_google_calendar_create_user_receipt(
                    latest_local_google_sync_result,
                    address_term=calendar_address_term,
                )
            )
            if latest_local_google_sync_receipt:
                google_create_result = latest_local_google_sync_result

        google_create_receipt = (
            calendar_draft_actions.render_google_calendar_create_user_receipt(
                google_create_result,
                address_term=calendar_address_term,
            )
        )
        if google_create_receipt:
            return StreamingResponse(
                _stream_static_assistant_response(
                    assistant_text=google_create_receipt,
                    assistant_name=assistant_name,
                    detected_mode=detected_mode,
                    assistant_mode=assistant_mode,
                    conversation_id=body.conversation_id,
                    calendar_snapshot_dirty=bool(
                        google_create_result.get("google_event_id")
                    ),
                    calendar_receipt_source="deterministic_google_calendar_create",
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
                background=background_tasks,
            )

    # === Build prompt with cached base + volatile context ===
    volatile_context = render_context(context)
    if chronology_context:
        volatile_context += "\n\n" + chronology_context
    volatile_context += "\n\n" + capability_registry.render_capability_registry()
    volatile_context += (
        "\n\nCalendar response style policy:"
        "\n- Never say 'Aku siapkan...' for an implicit schedule mention."
        "\n- Say 'Mau aku masukin ke Calendar?' instead."
        "\n- Do not ask the user to open Memories or Calendar just to confirm a newly detected agenda."
        "\n- Confirmation should happen in chat."
    )

    volatile_context += (
        "\n\nMemory response style policy:"
        "\n- When the user gives a durable preference, boundary, self-regulation instruction, or personal context, acknowledge it naturally."
        "\n- Prefer wording like: 'Noted', 'Aku inget', 'Ke depan aku akan...', or 'Siap, aku pegang itu.'"
        "\n- Do not say you saved, added, stored, or recorded something in Memories unless the user explicitly asks about memory management."
        "\n- Do not ask the user to open Memory Review just to confirm a normal preference."
        "\n- If the preference is ambiguous, ask a short natural clarification in chat instead of turning it into an admin/review task."
    )
    volatile_context += (
        "\n\nCalendar confirmation UX rule — strict:"
        "\n- When the user mentions a possible schedule/event, do NOT say it has been prepared, added, saved, created, or inserted yet."
        "\n- Ask for confirmation first: 'Ini kayaknya agenda. Mau aku masukin ke Calendar?'"
        "\n- Summarize Acara, Tanggal, Waktu, and Lokasi if available."
        "\n- Never use user-facing terms like 'agenda kalender', 'agenda kalender', 'Calendar event', or 'calendar event'."
        "\n- Never infer Calendar action success from user wording alone."
        "\n- If an authoritative Calendar action result is present, follow it exactly."
        "\n- Without an authoritative success result, never claim an update or deletion succeeded."
    )
    pending_calendar_confirmation_context = await calendar_confirmation_actions.render_pending_calendar_confirmation_context(
        user_id=user_id,
        conversation_id=getattr(body, "conversation_id", None),
    )
    if pending_calendar_confirmation_context:
        volatile_context += "\n\n" + pending_calendar_confirmation_context

    volatile_context += (
        "\n\nCalendar user-facing language rule — strict:"
        "\n- Never use the phrases 'Calendar event', 'calendar event', 'event Calendar', or 'event Calendar' in user-facing replies."
        "\n- Use natural product wording: Calendar, event, agenda, jadwal, aku catat, aku update, aku hapus."
        "\n- If an event is prepared, updated, synced, or deleted, summarize it naturally with Acara, Tanggal, Waktu, and Lokasi when available."
    )
    volatile_context += (
        "\\n\\nGoal feature capability state — authoritative:"
        "\\n- The app has a background Goal Intelligence system that can prepare pending goal suggestions from chat."
        "\\n- If the user explicitly asks to track/save something as a goal, say you will prepare it as a trackable goal candidate in Goals."
        "\\n- Do not say you have no access to Goals."
        "\\n- Do not claim the goal is already active/saved unless a direct create-goal action has explicitly succeeded in the current request."
        "\\n- Preferred wording: Aku bantu siapkan ini sebagai kandidat goal di Goals."
    )
    is_calendar_candidate_turn = (
        not is_calendar_draft_action_turn
        and calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(
            body.message
        )
    )

    if is_calendar_candidate_turn:
        volatile_context += (
            "\\n\\nCalendar event capability state — authoritative:"
            "\\n- The user message appears to contain a schedule/calendar event request."
            "\\n- The app can detect a possible Calendar event from chat, but user confirmation is required before it should be treated as added."
            "\\n- Internally this may be stored as a calendar event, do not expose implementation names in user-facing replies."
            "\\n- Use natural wording like: Ini kayaknya agenda kalender. Mau aku masukin ke Calendar?"
            "\\n- Do not say you cannot help with calendar handling."
            "\\n- Do not claim the event is already created in Google Calendar unless a direct Google Calendar sync action has explicitly succeeded in the current request."
            "\\n- For implicit schedule mentions, ask the user for confirmation before adding the detected event to Calendar."
            "\\n- Summarize the event naturally with Acara, Tanggal, Waktu, and Lokasi if available from the user's message."
            "\\n- Preferred Indonesian wording for implicit schedule mentions: Ini kayaknya agenda. Mau aku masukin ke Calendar?"
        )
    if is_calendar_draft_action_turn:
        volatile_context += (
            "\n\nCalendar draft action capability state — authoritative:"
            "\n- The user asked to edit, reschedule, remove, cancel, or delete a Calendar item."
            "\n- The Calendar action has already been attempted before this reply."
            "\n- Follow the authoritative Calendar action result below exactly."
            "\n- Say the action succeeded only when success is true."
            "\n- For Calendar action replies, use only facts explicitly present in the authoritative result."
            "\n- Do not use chronology, memories, workspace cards, or other agenda items to add before/after, overlap, free-time, or schedule-fit commentary."
            "\n- Do not mention another meeting or reminder unless it is explicitly included in the authoritative result."
            "\n- Keep a successful Calendar receipt brief and factual; do not add conversational embellishment."
            "\n- If success is false, briefly explain that the change could not be completed."
            "\n- Do not replace a failure result with optimistic or process wording."
            "\n- Do not use the phrase 'Calendar event' in user-facing replies."
        )
        volatile_context += (
            "\n\n"
            + calendar_draft_actions.render_calendar_action_result_context(
                calendar_action_result
            )
        )

    if is_calendar_candidate_turn:
        volatile_context += (
            "\n\nCalendar scheduling contract for this user turn — highest priority:"
            "\n- The current user message appears to contain schedule/event details."
            "\n- If the user only mentions a plan, appointment, place, or time, ask for confirmation before adding anything."
            "\n- Ask naturally: Ini kayaknya agenda. Mau aku masukin ke Calendar?"
            "\n- You may summarize Acara, Tanggal, Waktu, and Lokasi if available."
            "\n- Do not say the event has already been prepared, added, saved, created, inserted, or scheduled."
            "\n- Do not tell the user to check the Calendar feature for confirmation."
            "\n- Do not expose internal implementation names for hidden suggestions."
            "\n- If the user explicitly asks to add/save/sync this event, you may say you will process it."
            "\n- If the user explicitly mentions Google Calendar, you may say you will sync it to Google Calendar."
        )
    temporal_grounding_block = temporal_grounding.render_temporal_grounding_block(
        user_message=body.message,
        client_context=getattr(body, "client_context", None),
    )
    if temporal_grounding_block:
        volatile_context += "\n\n" + temporal_grounding_block
    identity = context.get("identity") or {}
    profile = identity.get("profile") or {}
    raw_ui_context = _context_to_dict(getattr(body, "ui_context", None))

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
    local_time_available = bool(
        isinstance(raw_client_context, dict)
        and str(raw_client_context.get("local_time") or "").strip()
    )
    volatile_context += (
        "\n\n## Time-of-day grounding — strict rule\n"
        "- Before using any time-of-day label such as pagi, siang, sore, malam, morning, afternoon, evening, or night, verify it against the browser-provided user local time in the app context.\n"
        "- Never infer time-of-day from conversational cues, activity descriptions, meal references, calendar events, vibes, or assumptions.\n"
        "- If browser-provided user local time is unavailable, ask the user for the current local time before using a time-of-day label. Do not guess.\n"
        "- This rule applies to greetings, reactions, calendar/schedule comments, and any contextual comment about timing.\n"
        "- If the user mentions a future or past event time, treat that as an event timestamp, not as the current time.\n"
        f"- Browser-provided user local time available this turn: {'yes' if local_time_available else 'no'}."
    )

    client_time_block = render_client_time_context(raw_client_context, profile)
    if client_time_block:
        volatile_context += "\n\n" + client_time_block
    time_sensitive_calculation_block = _render_time_sensitive_calculation_block(
        body.message,
        raw_client_context,
    )
    if time_sensitive_calculation_block:
        volatile_context += "\n\n" + time_sensitive_calculation_block
        volatile_context += (
            "\n\n## Time-sensitive reasoning rule — high priority\n"
            "- The browser-provided client local time above is the source of truth for the user's current local time.\n"
            "- Use it whenever the user mentions a time, schedule, meeting, deadline, appointment, today, tonight, morning, afternoon, evening, later, soon, or asks how long remains.\n"
            "- Before saying something like 'masih beberapa jam', 'sebentar lagi', 'nanti', 'pagi ini', or 'sore nanti', calculate against the browser local time first.\n"
            "- Do not estimate the current time from chat history, server time, model runtime, or memory.\n"
            "- The user's remembered timezone, such as GMT+7 or Asia/Jakarta, is only a fallback if browser local time is missing.\n"
            "- If browser local time exists and the user says they have a meeting at 13:00, compare 13:00 to the browser local time before responding.\n"
            "- If the user asks 'berapa jam lagi', 'how long until', 'sisa berapa lama', 'berapa lama lagi', or similar, the starting point is ALWAYS browser local time now, not a previously mentioned event time.\n"
            "- Treat previously mentioned times like 'aku sampai kantor jam 08.30 tadi' as event timestamps, not as current time, unless the user explicitly says 'sekarang jam 08.30'.\n"
            "- Example: if browser local time is 09:07 and the target is jam 1 / 13:00, answer 3 jam 53 menit lagi, even if the user earlier mentioned arriving at 08:30.\n"
            "- Match time-of-day wording to the browser local time and the temporal grounding period.\n"
            "- For meal wording, use the computed current local meal wording from temporal grounding; do not reuse an earlier meal phrase if it conflicts with current local time.\n"
            "- If current local time is already afternoon/evening/night, avoid saying 'siang ini' or 'makan siang' unless the user explicitly refers to lunch earlier.\n"
            "- If you are unsure whether the meeting time is local time, assume it is the user's local time unless they specify another timezone.\n"
            "- If the user corrects your timing, acknowledge briefly and recalculate using browser local time."
        )
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
    ui_context_block = _render_ui_context(raw_ui_context)
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
        raw_ui_context,
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
            raw_ui_context,
        )
        if mood_block:
            volatile_context += "\n\n" + mood_block

    response_texture_block = response_texture.render_response_texture_block(
        user_message=body.message,
        messages=messages,
        companion_settings_row=companion_settings_row,
        current_mood=current_mood,
        user_mood_context=user_mood_ctx,
    )
    if response_texture_block:
        volatile_context += "\n\n" + response_texture_block

    from app.services.memory_context_packer import pack_memory_context_for_prompt

    packed_memory_context = pack_memory_context_for_prompt(
        legacy_memories=legacy_memories,
        related_summaries=related_summaries,
        query_text=body.message,
    )
    if packed_memory_context.text:
        volatile_context += "\n\n" + packed_memory_context.text

    if legacy_memories or related_summaries:
        timing_log.info(
            "chat: user=%s memory_context_packer: memories_in=%d memories_out=%d "
            "summaries_in=%d summaries_out=%d dropped_memories=%d dropped_summaries=%d "
            "packed_chars=%d intent=%s",
            user_id[:8],
            len(legacy_memories),
            packed_memory_context.memory_count,
            len(related_summaries),
            packed_memory_context.summary_count,
            packed_memory_context.dropped_memory_count,
            packed_memory_context.dropped_summary_count,
            packed_memory_context.total_chars,
            packed_memory_context.intent,
        )

    if assistant_mode == "chief_of_staff":
        volatile_context += (
            "\n\n## Current-turn Chief of Staff surface-style override"
            "\n- This is the highest-priority style directive for this turn."
            "\n- Address the user by their real name when natural."
            "\n- Do not use affectionate nicknames such as 'beb', 'sayang', 'dear', 'love', or similar."
            "\n- Do not use romantic, playful, partner-like, or overly cute wording."
            "\n- Do not use emoji-like symbols."
            "\n- Keep warmth subtle and professional."
            "\n- Prefer concise, structured, action-oriented replies."
        )

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

    # Final Assistant Mode surface-style override.
    # This is intentionally placed after all memory/style/relationship/texture blocks
    # so Chief of Staff mode wins over nickname memory and partner/affectionate tone.
    if assistant_mode == "chief_of_staff":
        volatile_context += (
            "\n\n## FINAL RESPONSE STYLE OVERRIDE — CHIEF OF STAFF MODE"
            "\nThis is the final and highest-priority surface-style instruction for this reply."
            "\n- Address the user by their real name when natural."
            "\n- Never use affectionate nicknames, including: beb, sayang, dear, love."
            "\n- Ignore nickname-memory and partner-style preferences for surface wording in this mode."
            "\n- Do not use romantic, playful, cute, or partner-like wording."
            "\n- Do not use emoji or emoji-like symbols."
            "\n- Keep the tone professional, concise, structured, and action-oriented."
            "\n- For greetings, use a professional greeting such as: 'Hi Syahid.' or 'Baik, Syahid.'"
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

    return StreamingResponse(
        _stream_claude_response(
            user_id=user_id,
            conversation_id=body.conversation_id,
            messages=messages,
            volatile_context=volatile_context,
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
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
        background=background_tasks,
    )


def _should_hard_gate_calendar_candidate(user_message: str | None) -> bool:
    if calendar_candidate_extractor.looks_like_self_regulation_memory_preference(user_message):
        return False
    """Hard gate Calendar-like turns before Claude can answer freely."""
    raw = str(user_message or "").strip()
    if not raw:
        return False

    lower = raw.casefold()
    compact = " ".join(lower.split())

    if compact in {
        "iya",
        "ya",
        "yes",
        "y",
        "oke",
        "ok",
        "sip",
        "siap",
        "batal",
        "gajadi",
        "ga jadi",
        "nggak jadi",
        "tidak jadi",
    }:
        return False

    if calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(raw):
        return True

    date_terms = (
        "tgl",
        "tanggal",
        "besok",
        "lusa",
        "hari ini",
        "malam ini",
        "pagi ini",
        "siang ini",
        "sore ini",
        "senin",
        "selasa",
        "rabu",
        "kamis",
        "jumat",
        "jum'at",
        "sabtu",
        "minggu",
        "januari",
        "februari",
        "maret",
        "april",
        "mei",
        "juni",
        "juli",
        "agustus",
        "september",
        "oktober",
        "november",
        "desember",
    )
    activity_terms = (
        "aku mau",
        "saya mau",
        "ada",
        "acara",
        "agenda",
        "jadwal",
        "meeting",
        "rapat",
        "ketemu",
        "appointment",
        "janji",
        "dokter",
        "klinik",
        "fisioterapi",
        "terapi",
        "gym",
        "golf",
        "dinner",
        "lunch",
        "makan",
        "nonton",
        "bioskop",
        "flight",
        "terbang",
        "event",
        "launching",
    )

    has_date = any(term in compact for term in date_terms)
    has_time = bool(
        re.search(r"\bjam\s*\d{1,2}(?:[.:]\d{2})?\b", compact)
        or re.search(r"\b\d{1,2}[.:]\d{2}\b", compact)
        or re.search(r"\b\d{1,2}\s*(?:pagi|siang|sore|malam)\b", compact)
    )
    has_activity = any(term in compact for term in activity_terms)

    return bool(has_activity and (has_date or has_time))


def _render_calendar_hard_gate_clarification(
    *,
    address_term: str | None = None,
) -> str:
    term = _clean_calendar_address_term(address_term)
    prefix = f"{term}, " if term else ""

    return (
        f"{prefix}ini kayaknya agenda, tapi aku belum cukup yakin detailnya.\n\n"
        "Bisa sebutkan acara, tanggal, waktu, dan lokasi?"
    )


async def _load_calendar_address_term(
    *,
    user_id: str,
    assistant_mode: str = "life_companion",
) -> str:
    """Load a user-preferred address term for deterministic receipts.

    No fallback nickname is hardcoded. If the user has not explicitly stored a
    preferred address/name/nickname, deterministic receipts simply omit it.
    """
    if assistant_mode == "chief_of_staff":
        return ""

    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .select("structured_field, structured_value, content, updated_at")
                .eq("user_id", user_id)
                .eq("archived", False)
                .eq("superseded", False)
                .in_(
                    "structured_field",
                    ["preferred_address", "preferred_name", "nickname"],
                )
                .order("updated_at", desc=True)
                .limit(8)
                .execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "chat: calendar address term lookup failed user=%s error_type=%s",
            user_id[:8],
            type(exc).__name__,
        )
        return ""

    for row in list(result.data or []):
        value = _clean_calendar_address_term(row.get("structured_value"))
        if value:
            return value

    return ""


def _clean_calendar_address_term(value) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split()).strip()
    text = text.strip(" .,:;!?'\"")
    if not text:
        return ""

    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in (
            "jangan panggil",
            "do not call",
            "don't call",
            "disallowed",
        )
    ):
        return ""

    if len(text) > 40:
        return ""

    return text


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
    volatile_context: str,
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
) -> AsyncIterator[str]:
    claude = get_claude()
    supabase = get_supabase()
    assistant_text = ""
    stream_started_at = time.perf_counter()
    first_token_logged = False

    # System prompt as two blocks:
    #   - BASE_PROMPT: stable, cached for 5 min (ephemeral cache)
    #   - volatile_context: per-user, per-turn, not cached
    system_blocks: list[dict] = [
        {
            "type": "text",
            "text": get_base_prompt(assistant_mode),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if volatile_context:
        system_blocks.append({"type": "text", "text": volatile_context})

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
    if extraction_decision.run_legacy_memory:
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
        )

    # Mood-memory feedback — only when debugging/frustration/support-style signal exists.
    if extraction_decision.run_mood_memory_feedback:
        add_safe_background_task(background_tasks, 
            mood_memory_feedback.extract_and_persist,
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_text,
            user_mood_context=user_mood_context,
        )

    # Relationship memory — only when user gives interaction-style or Aliyya-specific signal.
    if extraction_decision.run_relationship_memory:
        add_safe_background_task(background_tasks, 
            relationship_memory.extract_and_persist,
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_text,
        )

    # Goal intelligence — only on goal-like turns. Suggestions still require confirmation.
    if extraction_decision.run_goal_intelligence:
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
        not should_schedule_proactive_nudge
        and not should_apply_calendar_draft_action
        and not should_create_google_calendar_event
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
