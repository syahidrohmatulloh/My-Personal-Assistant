"""Prompt builder — assembles the system prompt for the chat agent.

Render priorities (top of context = top of attention):
  1. Identity (rendered as prose, not JSON)
  2. Active goals
  3. Important people
  4. Recent emotional state (aggregated if many entries, itemized if few)
  5. Recent life events
  6. Self-reflections (rendered as private hints, not facts to repeat)

Tone enforcement lives in BASE_PROMPT — anti-repetition, no memory-dumping,
language matching, name use.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python <3.9 unsupported anyway
    ZoneInfo = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base system prompt — tone enforcement
# ---------------------------------------------------------------------------

BASE_PROMPT = """You are a personal AI assistant for one specific person.

Your role mixes chief-of-staff (organizing, summarizing, helping with \
decisions) with companion (emotionally aware, attentive, supportive).

# Conduct rules — absolute

- Observe, don't perform. Notice patterns; don't narrate them dramatically.
- Reference what the user has actually told you. Don't invent context.
- Treat self-reported facts as truth. Treat inferred facts as hypotheses to \
hedge ("you've seemed...", "is it fair to say...") not as facts to assert.
- Be useful first, warm second. Not warm at the cost of useful.
- When the user is in a hard moment, prioritize presence over advice. \
Ask what they need before suggesting.
- Never claim to "understand" the user beyond observable evidence.
- Never act as a therapist, doctor, or licensed professional. Suggest \
appropriate human help when topics warrant it.

# Use of stored context — strict

- The context below is yours for grounding, not for performance. Don't \
recite it back. Don't summarize what you know about the user unless they \
explicitly ask.
- Don't re-acknowledge stable facts ("I see you're a founder…") at the \
start of replies. The user knows you know.
- If the user contradicts something stored, the user's current message \
is the authority. Note the contradiction silently; don't argue.
- Don't reference dates from the stored emotional state unless the user \
asks about a specific time. Trends matter; daily ledgers are noise.

# Language

- Match the user's language. If they message in Indonesian, reply in \
Indonesian. If they mix languages, mirror the mix.

# Formatting

- Use markdown when it aids clarity. Don't over-format casual chat.
- Keep replies proportionate to the question. Short questions get short \
answers."""


# ---------------------------------------------------------------------------
# Identity prose — replaces raw JSON dump
# ---------------------------------------------------------------------------

def _profile_to_prose(profile: dict[str, Any]) -> str:
    """Render the identity profile as natural prose.

    Avoids dumping JSON braces. Keeps the model's attention on the meaning,
    not the structure.
    """
    parts: list[str] = []

    name = profile.get("name")
    location = profile.get("location")
    work = profile.get("work") or {}
    role = work.get("role") if isinstance(work, dict) else None
    industry = work.get("industry") if isinstance(work, dict) else None

    # Opening sentence — name, role, location.
    intro_bits: list[str] = []
    if name:
        intro_bits.append(name)
    if role:
        intro_bits.append(f"is a {role}" + (f" in {industry}" if industry else ""))
    elif industry:
        intro_bits.append(f"works in {industry}")
    if location:
        intro_bits.append(f"based in {location}")
    if intro_bits:
        # Join naturally: "Syahid is a founder in AI based in Jakarta."
        if len(intro_bits) == 1:
            parts.append(intro_bits[0] + ".")
        else:
            parts.append(" ".join(intro_bits) + ".")

    # Values
    values = profile.get("values")
    if isinstance(values, list) and values:
        parts.append(f"Values: {', '.join(str(v) for v in values)}.")

    # Communication preference
    comm = profile.get("communication_preferences") or {}
    tone = comm.get("tone") if isinstance(comm, dict) else None
    if tone:
        parts.append(f"Prefers communication that is: {tone}.")

    return " ".join(parts)


def _user_timezone(profile: dict[str, Any]) -> Any:
    """Return a tzinfo from the profile, or UTC fallback.

    Identity stores timezone as profile.timezone (IANA string).
    """
    tz_name = profile.get("timezone") if isinstance(profile, dict) else None
    if tz_name and ZoneInfo is not None:
        try:
            return ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            return timezone.utc
    return timezone.utc


def _format_local_date(iso_string: str, tz: Any) -> str:
    """Take a UTC ISO datetime string, render as YYYY-MM-DD in user's tz."""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return iso_string[:10]


# ---------------------------------------------------------------------------
# Adaptive emotional tone directive
#
# Reads recent self-reported state. If a clear pattern is present (high stress,
# low mood, high energy), emits a short directive telling Claude how to modulate
# THIS conversation. Quiet on neutral states — we don't want to inject noise
# every turn when the user is fine.
# ---------------------------------------------------------------------------


def _emotional_directive(mood_log: list[dict]) -> str | None:
    """Return a directive string for adaptive tone, or None if no clear signal.

    Looks at SELF-REPORTED entries from the last ~3 days. Inferred data is
    too low-confidence to drive tone changes — we don't want to assume.
    """
    if not mood_log:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    recent: list[dict] = []
    for m in mood_log:
        if m.get("source") != "self_report":
            continue
        observed = m.get("observed_at")
        if not observed:
            continue
        try:
            dt = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt >= cutoff:
            recent.append(m)

    # Need at least 2 data points to call something a "pattern" — otherwise
    # we're overinterpreting a single bad day.
    if len(recent) < 2:
        return None

    def _avg(field: str) -> float | None:
        vals = [e[field] for e in recent if e.get(field) is not None]
        return statistics.mean(vals) if vals else None

    mood = _avg("mood")
    energy = _avg("energy")
    stress = _avg("stress")

    # High stress dominates — even if mood is OK, if stress is high, calm down.
    if stress is not None and stress >= 2:
        return (
            "## Conversational tone for this turn\n"
            "The user's recent self-reported stress is elevated. For this conversation:\n"
            "- Keep replies shorter than usual. Don't overload with options or steps.\n"
            "- Lead with acknowledgment before suggestions.\n"
            "- Avoid asking multiple questions in one reply.\n"
            "- Speak as you would to someone who is tired — calmly, without urgency."
        )

    # Low mood — gentler register, validate before reasoning.
    if mood is not None and mood <= -2:
        return (
            "## Conversational tone for this turn\n"
            "The user's recent self-reported mood has been low. For this conversation:\n"
            "- Lead with presence, not problem-solving.\n"
            "- Don't try to cheer them up. Don't minimize.\n"
            "- Keep replies short and unforced.\n"
            "- If they want to vent, let them. Ask what they need before suggesting."
        )

    # High energy + positive mood — match the velocity, sharpen up.
    if (mood is not None and mood >= 2) and (energy is not None and energy >= 2):
        return (
            "## Conversational tone for this turn\n"
            "The user's recent self-reported state is energized and positive. For this conversation:\n"
            "- Match their pace. Be direct, sharp, ambitious.\n"
            "- Skip excessive caveats. They're ready to act.\n"
            "- If they're brainstorming, brainstorm with them — don't hold back."
        )

    return None


# ---------------------------------------------------------------------------
# Mood aggregation
# ---------------------------------------------------------------------------

def _render_mood(mood_log: list[dict], tz: Any) -> str:
    """Render mood as a trend summary + a few recent self-reported entries.

    When there are many entries, a daily ledger becomes noise. We render:
      - an aggregate trend (avg + range) over the window
      - up to 3 most recent self-reported entries with notes
      - inferred entries are summarized as a count, not itemized
    """
    if not mood_log:
        return ""

    self_reports = [m for m in mood_log if m.get("source") == "self_report"]
    inferred = [m for m in mood_log if m.get("source") != "self_report"]

    lines = ["## Recent emotional state (last 2 weeks)"]

    def _stat(field: str, entries: list[dict]) -> str | None:
        vals = [e[field] for e in entries if e.get(field) is not None]
        if not vals:
            return None
        avg = statistics.mean(vals)
        return f"{field} avg {avg:+.1f}"

    if self_reports:
        trend_bits = [
            s for s in (_stat("mood", self_reports), _stat("energy", self_reports), _stat("stress", self_reports)) if s
        ]
        if trend_bits:
            lines.append(
                f"Self-reported trend ({len(self_reports)} entries): {', '.join(trend_bits)}"
            )

        # Show only the 3 most recent self-reports verbatim — and only their notes,
        # not the numeric ledger. Notes are higher-signal than scales.
        recent_with_notes = [m for m in self_reports[:5] if m.get("note")][:3]
        if recent_with_notes:
            lines.append("Recent self-reported notes:")
            for m in recent_with_notes:
                date = _format_local_date(m["observed_at"], tz)
                lines.append(f"- {date}: {m['note']}")

    if inferred:
        lines.append(
            f"({len(inferred)} additional inferred observations on file — "
            f"treat as low-confidence hypotheses, not facts.)"
        )

    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Client local time context
# ---------------------------------------------------------------------------

def _format_utc_offset_label(offset_minutes: Any) -> str | None:
    try:
        minutes = int(offset_minutes)
    except Exception:  # noqa: BLE001
        return None
    sign = "+" if minutes >= 0 else "-"
    absolute = abs(minutes)
    hours = absolute // 60
    mins = absolute % 60
    if mins == 0:
        return f"GMT{sign}{hours}"
    return f"GMT{sign}{hours}:{mins:02d}"


def render_client_time_context(
    client_context: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
) -> str:
    """Render browser-provided time context for the current turn.

    Browser local time is the source of truth for greetings and time-sensitive
    wording. Server time is intentionally not used because the backend may run
    in UTC or another region.
    """
    ctx = client_context or {}
    profile = profile or {}

    timezone_name = ctx.get("timezone") or profile.get("timezone")
    local_time = ctx.get("local_time")
    locale = ctx.get("locale")
    offset_label = _format_utc_offset_label(ctx.get("utc_offset_minutes"))
    captured_at_utc = ctx.get("captured_at_utc")

    if not timezone_name and not local_time and not offset_label:
        return ""

    lines = [
        "## User local time — source of truth for this turn",
        "Use the browser/client local time below for greetings, date references, countdowns, and time-sensitive answers.",
        "Do NOT infer the current time from server time, UTC, logs, or model knowledge unless the user explicitly asks for UTC/server time.",
    ]
    if timezone_name:
        lines.append(f"- User local timezone: {timezone_name}")
    if local_time:
        lines.append(f"- User local time now: {local_time}")
    if offset_label:
        lines.append(f"- UTC offset: {offset_label}")
    if locale:
        lines.append(f"- Browser locale: {locale}")
    if captured_at_utc:
        lines.append(f"- Captured at UTC: {captured_at_utc} (debug only; do not prefer over local time)")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_context(context: dict[str, Any]) -> str:
    """Render the life model as a compact, hierarchical block.

    Order is the retrieval hierarchy:
    identity > goals > people > mood > events > self-reflections.
    """
    if not context:
        return ""

    identity = context.get("identity") or {}
    profile = identity.get("profile") or {}
    tz = _user_timezone(profile)

    sections: list[str] = []

    # 1. Identity — prose, not JSON.
    prose = _profile_to_prose(profile) if profile else ""
    narrative = identity.get("narrative")
    if prose or narrative:
        block = ["## About this user"]
        if prose:
            block.append(prose)
        if narrative:
            block.append(narrative)
        sections.append("\n".join(block))

    # 2. Active goals — include latest check-in (momentum + note) where available.
    goals = context.get("active_goals") or []
    if goals:
        lines = ["## Active goals"]
        for g in goals[:8]:
            target = f" — target {g['target_date']}" if g.get("target_date") else ""
            lines.append(f"- [{g['horizon']}] {g['title']}{target}")
            check_in = g.get("latest_check_in") or {}
            if check_in:
                momentum = check_in.get("momentum")
                note = check_in.get("note")
                bits = []
                if momentum is not None:
                    bits.append(f"momentum {momentum:+d}")
                if note:
                    # Keep check-in note short so prompt stays compact.
                    snippet = note if len(note) <= 120 else note[:117] + "…"
                    bits.append(snippet)
                if bits:
                    lines.append(f"  · latest check-in: {' — '.join(bits)}")
        sections.append("\n".join(lines))

    # 3. Important people — include up to 3 recent notes per person.
    people = context.get("important_people") or []
    if people:
        lines = ["## People who matter most"]
        for p in people[:10]:
            rel = f" ({p['relationship']})" if p.get("relationship") else ""
            lines.append(f"- {p['name']}{rel}")
            notes = p.get("recent_notes") or []
            for n in notes[:3]:
                content = n.get("content") or ""
                if not content:
                    continue
                kind = n.get("kind") or "note"
                snippet = content if len(content) <= 140 else content[:137] + "…"
                lines.append(f"  · [{kind}] {snippet}")
        sections.append("\n".join(lines))

    # 4. Mood — aggregated.
    mood_block = _render_mood(context.get("recent_mood") or [], tz)
    if mood_block:
        sections.append(mood_block)

    # 5. Recent life events.
    events = context.get("recent_events") or []
    if events:
        lines = ["## Recent life events (last 90 days)"]
        for e in events[:8]:
            lines.append(f"- {e['happened_on']}: [{e['category']}] {e['title']}")
        sections.append("\n".join(lines))

    # 6. Self-reflections — rendered as private hints, not facts to repeat.
    reflections = context.get("recent_self_reflections") or []
    if reflections:
        lines = [
            "## Private behavioral notes (for your own behavior — do NOT recite these back to the user)"
        ]
        for r in reflections[:5]:
            lines.append(f"- [{r['kind']}] {r['content']}")
        sections.append("\n".join(lines))

    # 7. Adaptive emotional directive — last technical instruction.
    # If recent self-reported state shows a pattern, tell Claude how to modulate.
    directive = _emotional_directive(context.get("recent_mood") or [])
    if directive:
        sections.append(directive)

    # 8. Name reinforcement — final friendly note.
    name = profile.get("name") if isinstance(profile, dict) else None
    if name:
        sections.append(
            f"## Addressing the user\nUse their name naturally where it fits: **{name}**. "
            f"Don't overuse it — once in a while is warmer than every reply."
        )

    if not sections:
        return ""
    return "\n\n".join(sections)


def build_system_prompt(context: dict[str, Any]) -> str:
    """Combine the base prompt with rendered life-model context."""
    rendered = render_context(context)
    if not rendered:
        return BASE_PROMPT
    return f"{BASE_PROMPT}\n\n---\n\n{rendered}"


# ---------------------------------------------------------------------------
# History trimming
# ---------------------------------------------------------------------------

HISTORY_CHAR_BUDGET = 6000


def trim_history(messages: list[dict]) -> list[dict]:
    """Keep recent turns within budget. Older turns become a synthetic note."""
    total = sum(len(m.get("content", "")) for m in messages)
    if total <= HISTORY_CHAR_BUDGET:
        return messages

    kept: list[dict] = []
    running = 0
    for m in reversed(messages):
        content_len = len(m.get("content", ""))
        if running + content_len > HISTORY_CHAR_BUDGET:
            break
        kept.insert(0, m)
        running += content_len

    dropped = len(messages) - len(kept)
    if dropped == 0:
        return messages

    summary = {
        "role": "user",
        "content": (
            f"[Earlier in this conversation, you exchanged {dropped} messages "
            f"not shown here. Continue naturally from the recent context below.]"
        ),
    }
    if kept and kept[0]["role"] == "assistant":
        kept = kept[1:]
    return [summary] + kept
