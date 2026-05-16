"""Companion mode detection.

For each substantive user message, we classify what kind of response the user
needs. The result becomes a short directive injected into the system prompt —
not shown to the user, just shapes Claude's reply style.

Modes:
  - strategist  : user wants planning, structure, execution help
  - listener    : user wants presence and validation, NOT advice
  - motivator   : user is stuck or sluggish, needs energy/momentum
  - challenger  : user has a distortion or impulsive plan that deserves pushback
  - reflective  : user is processing patterns, wants help noticing things
  - practical   : user wants a direct answer to a concrete question

We default to `practical` when ambiguous — practical is safe, the other modes
have stronger stylistic implications and we don't want to misfire.

Latency budget: ~500ms via Haiku. To stay under budget we:
  - Skip detection for very short messages ("ok", "thanks") — return None
  - Use minimal max_tokens (5) — only need one word back
  - Use a tight, structured prompt to keep token count low
"""

from __future__ import annotations

import logging
from typing import Literal

from app.services.claude import get_claude

log = logging.getLogger(__name__)


Mode = Literal["strategist", "listener", "motivator", "challenger", "reflective", "practical"]
ALL_MODES: tuple[Mode, ...] = (
    "strategist",
    "listener",
    "motivator",
    "challenger",
    "reflective",
    "practical",
)


# Mode directives — injected into the system prompt when a mode is detected.
# Kept compact (~30-50 tokens each). Listed in same order as modes for review.
_MODE_DIRECTIVES: dict[Mode, str] = {
    "strategist": (
        "The user appears to want planning or execution help. Be structured. "
        "Offer concrete steps or options. Don't lead with emotion — they want "
        "to think clearly."
    ),
    "listener": (
        "The user appears to want presence, not advice. Validate first. Don't "
        "solve. Don't list options. Reflect back what they're saying briefly, "
        "then ask if they want input — don't assume."
    ),
    "motivator": (
        "The user sounds stuck or sluggish. Be brief, energizing, and concrete. "
        "Skip caveats. One clear next action beats a balanced analysis here."
    ),
    "challenger": (
        "The user's framing seems off — possibly a distortion, impulse, or "
        "self-defeating frame. Push back honestly and respectfully. Don't "
        "validate before challenging. Be direct, not preachy."
    ),
    "reflective": (
        "The user seems to be processing a pattern or seeking self-awareness. "
        "Ask one focused question rather than giving answers. Hold space for "
        "their thinking. Don't rush to conclusions."
    ),
    "practical": (
        "The user wants a concrete answer. Be direct. Skip emotional framing "
        "unless it's relevant. Lead with the answer, then context."
    ),
}


# Skip detection on trivially short messages — they're sapaan, ack, or noise.
_MIN_CHARS_FOR_DETECTION = 30

# Keywords that obviously map to "practical" without needing Haiku.
# Short-circuit saves a network call.
_PRACTICAL_HINTS = (
    "apa itu",
    "what is",
    "how do i",
    "bagaimana cara",
    "jam berapa",
    "what time",
    "what's the",
)


CLASSIFIER_SYSTEM = """You classify a user's message to a personal AI assistant into ONE mode.

Choose the SINGLE best fit:

- strategist  : user wants planning, structure, decisions, execution
- listener    : user is venting, sharing emotion, wants presence (NOT advice)
- motivator   : user is stuck, demotivated, needs activation
- challenger  : user has a distorted, impulsive, or self-defeating frame that deserves honest pushback
- reflective  : user is exploring their own patterns, asking self-aware questions
- practical   : user is asking a concrete question with a clear answer

Default to "practical" if ambiguous.

Output ONE word, lowercase. Nothing else."""


async def detect_mode(*, user_message: str, recent_assistant_text: str | None = None) -> Mode | None:
    """Classify the user's intent. Returns None on skip/failure.

    `recent_assistant_text` is the previous assistant turn (if any) — gives the
    classifier context like "user said 'yes' after I asked a question, so they
    likely want strategist". We don't pass full history — that's overkill.
    """
    text = user_message.strip()
    if len(text) < _MIN_CHARS_FOR_DETECTION:
        return None

    lower = text.lower()
    if any(hint in lower for hint in _PRACTICAL_HINTS):
        return "practical"

    # Compose the prompt. Keep it minimal.
    parts: list[str] = []
    if recent_assistant_text:
        snippet = recent_assistant_text[:300]
        parts.append(f"(Your previous reply was: \"{snippet}\")\n")
    parts.append(f"User says: {text[:800]}")
    user_content = "\n".join(parts)

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            system=CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:
        log.warning("mode detection: Haiku failed: %s", exc)
        return None

    block = next((b for b in response.content if b.type == "text"), None)
    if not block:
        return None
    raw = block.text.strip().lower().split()[0] if block.text.strip() else ""
    raw = raw.rstrip(".,!?")

    if raw not in ALL_MODES:
        log.info("mode detection: unrecognized output %r — falling back to None", raw)
        return None

    return raw  # type: ignore[return-value]


def directive_for(mode: Mode | None) -> str | None:
    """Return the directive string for the prompt builder to inject."""
    if mode is None:
        return None
    body = _MODE_DIRECTIVES.get(mode)
    if not body:
        return None
    return f"## Mode for this turn: {mode}\n{body}"
