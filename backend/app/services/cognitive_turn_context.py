"""M31E-FINAL cognitive turn context assembly.

This module owns read-only turn-context assembly and model-input preparation.

It deliberately does not own:
- HTTP/FastAPI response handling;
- Claude provider invocation or SSE streaming;
- memory retrieval/ranking algorithms;
- Calendar mutation implementations;
- durable-memory persistence algorithms.

CognitiveRuntime delegates orchestration here while underlying services remain
authoritative for their own algorithms and persistence.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from app.services import (
    calendar_candidate_extractor,
    calendar_confirmation_actions,
    calendar_draft_actions,
    capability_registry,
    chat_style_directive,
    chat_time_helpers,
    companion,
    companion_comeback_affect,
    companion_mode,
    interaction_preferences,
    response_texture,
    temporal_grounding,
)
from app.services.deterministic_profile import (
    render_profile_runtime_context,
)
from app.services.prompt_builder import (
    get_base_prompt,
    render_client_time_context,
    render_context,
)
from app.services.supabase_client import safe_execute
from app.services.user_mood_prompt import (
    render_user_mood_block,
)


@dataclass(frozen=True)
class CognitiveTurnContextAssembly:
    volatile_context: str
    packed_memory_context: Any
    pending_calendar_confirmation_context: str | None
    is_calendar_candidate_turn: bool
    style_audit: str
    companion_audit: str
    system_blocks: list[dict[str, Any]]


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


def is_briefing_discussion_request(message: str | None) -> bool:
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


async def retrieve_latest_briefing_for_prompt(user_id: str) -> dict | None:
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


async def assemble_turn_context(
    *,
    body: Any,
    user_id: str,
    context: dict[str, Any],
    chronology_context: str | None,
    assistant_mode: str,
    assistant_name: str,
    assistant_rename: str | None,
    current_mood: dict[str, Any] | None,
    user_mood_ctx: Any,
    latest_briefing_for_prompt: dict[str, Any] | None,
    comeback_affect_decision: Any,
    messages: list[dict[str, Any]],
    companion_settings_row: dict[str, Any],
    detected_mode: str | None,
    style_profile_id: str | None,
    calendar_action_result: dict[str, Any] | None,
    is_calendar_draft_action_turn: bool,
    pack_memory_context: Callable[[], Any],
    record_trace: Callable[[Any], None],
) -> CognitiveTurnContextAssembly:
    """Assemble the complete per-turn model context without invoking Claude."""

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
    time_sensitive_calculation_block = chat_time_helpers.render_time_sensitive_calculation_block(
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

    comeback_affect_block = companion_comeback_affect.render_prompt_block(
        comeback_affect_decision
    )
    if comeback_affect_block:
        volatile_context += "\n\n" + comeback_affect_block

    response_texture_block = response_texture.render_response_texture_block(
        user_message=body.message,
        messages=messages,
        companion_settings_row=companion_settings_row,
        current_mood=current_mood,
        user_mood_context=user_mood_ctx,
    )
    if response_texture_block:
        volatile_context += "\n\n" + response_texture_block

    packed_memory_context = pack_memory_context()
    if packed_memory_context.text:
        volatile_context += "\n\n" + packed_memory_context.text

    record_trace(packed_memory_context)

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
    if style_profile_id:
        style_block = await asyncio.to_thread(
            lambda: chat_style_directive.fetch_style_directive(user_id, style_profile_id)
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


    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": get_base_prompt(
                assistant_mode
            ),
            "cache_control": {
                "type": "ephemeral",
            },
        }
    ]

    if volatile_context:
        system_blocks.append(
            {
                "type": "text",
                "text": volatile_context,
            }
        )

    return CognitiveTurnContextAssembly(
        volatile_context=volatile_context,
        packed_memory_context=packed_memory_context,
        pending_calendar_confirmation_context=(
            pending_calendar_confirmation_context
        ),
        is_calendar_candidate_turn=(
            is_calendar_candidate_turn
        ),
        style_audit=style_audit,
        companion_audit=companion_audit,
        system_blocks=system_blocks,
    )
