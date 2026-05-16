"""Style extraction.

Given parsed transcript lines (or a plain text blob), pick a target sender
and ask Haiku to extract a structured style profile.

We never persist the transcript itself. After analyze returns the profile,
the caller discards the input.

Output is validated by Pydantic — so even if Haiku hallucinates extra
fields, we only persist what matches our schema.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.claude import get_claude
from app.services.style_parser import ParsedLine, SourceType

log = logging.getLogger(__name__)


# Maximum transcript size we'll send to Haiku. Larger = more context = better
# extraction, but more cost and tokens. 12k chars ~ 3000 tokens ~ enough.
_MAX_TRANSCRIPT_CHARS = 12_000

# Minimum messages from the target before we'll attempt extraction. Below
# this, the profile would be guesswork.
_MIN_TARGET_MESSAGES = 3


class StyleProfile(BaseModel):
    """Validated style profile. Every field is required so Haiku can't omit
    things, but most are free-form strings (we trust the model's prose)."""

    display_name: str = Field(min_length=1, max_length=80)
    dominant_language: str = Field(min_length=1, max_length=40)
    language_mixing: str = Field(max_length=120)

    formality_level: str = Field(max_length=40)
    warmth_level: str = Field(max_length=40)
    directness_level: str = Field(max_length=40)

    humor_style: str = Field(max_length=120)
    emoji_usage: str = Field(max_length=120)
    average_reply_length: str = Field(max_length=80)

    greeting_style: str = Field(max_length=120)
    closing_style: str = Field(max_length=120)
    conflict_style: str = Field(max_length=120)
    support_style: str = Field(max_length=120)
    decision_making_style: str = Field(max_length=120)

    common_phrases: list[str] = Field(default_factory=list, max_length=10)
    do_not_copy: list[str] = Field(default_factory=list, max_length=10)

    # Compact prose directive (~50-80 tokens) for the system prompt.
    compact_directive: str = Field(min_length=20, max_length=500)


EXTRACTOR_SYSTEM_PROMPT = """You analyze chat messages from ONE specific person \
and extract their communication style. Output strict JSON only.

# Output schema (ALL keys required, even if value is "unclear" or [])

{
  "display_name": "the person's name as it appears",
  "dominant_language": "English | Indonesian | Mandarin | mixed | ...",
  "language_mixing": "describe pattern if mixed, e.g. 'Indonesian base with English tech terms'",
  "formality_level": "very casual | casual | neutral | formal | very formal",
  "warmth_level": "cold | reserved | neutral | warm | very warm",
  "directness_level": "very indirect | indirect | balanced | direct | blunt",
  "humor_style": "describe in <12 words",
  "emoji_usage": "none | rare | occasional | frequent | heavy — and which kinds",
  "average_reply_length": "very short (<5 words) | short | medium | long | varies",
  "greeting_style": "how they open — quote one example",
  "closing_style": "how they close — quote one example or 'no consistent closing'",
  "conflict_style": "how they handle disagreement",
  "support_style": "how they comfort/support others",
  "decision_making_style": "how they reason or commit",
  "common_phrases": ["up to 8 phrases they repeat — VERBATIM short snippets only, no full sentences"],
  "do_not_copy": ["sensitive content the assistant must NEVER reproduce — names, secrets, private details, intimate references"],
  "compact_directive": "ONE prose sentence the assistant will read each turn. Describe the style WITHOUT naming the person. Example: 'Casual Indonesian-English mix, short replies, warm but teasing tone, sparing emoji, practical reassurance, decisions made by listing pros then deciding.'"
}

# Rules

- Analyze ONLY the target person's messages — ignore the other party's style.
- "common_phrases" must be short snippets actually present in the transcript. \
NOT made up. If you can't find any, return [].
- "do_not_copy" identifies content the assistant must avoid reproducing: \
private names, romantic/intimate references, secrets, anything sensitive. \
Be conservative — when in doubt, include it.
- "compact_directive" is the most important field. It will be injected into \
the assistant's system prompt. Write it as STYLE guidance, never as identity \
("be like Anna"). Use phrases like "casual tone, short replies, warm but \
teasing", NOT "talk like Anna".
- If the transcript is too thin or unclear to determine a field, use "unclear" \
for strings or [] for lists.

Output ONLY the JSON object. No prose, no markdown fences, no commentary."""


async def extract_style(
    *,
    source_type: SourceType,
    parsed_lines: list[ParsedLine],
    raw_text: str,
    target_sender: str | None = None,
) -> tuple[StyleProfile | None, int]:
    """Extract a style profile from parsed lines (or raw text if parsing failed).

    Returns (profile_or_none, sample_count).
    sample_count = number of messages from the target sender that contributed.
    """
    # Decide what to send Haiku, and how many target messages we have.
    if parsed_lines:
        target = target_sender or _pick_target_sender(parsed_lines)
        if not target:
            return None, 0

        target_lines = [(s, t) for s, t in parsed_lines if s == target]
        if len(target_lines) < _MIN_TARGET_MESSAGES:
            log.info(
                "style extract: target '%s' has only %d msgs, below threshold",
                target,
                len(target_lines),
            )
            return None, len(target_lines)

        # Compose transcript chunk. We send both speakers because context
        # matters (we want to see how the target responds to what), but
        # clearly label the target.
        transcript = _format_transcript(parsed_lines, target, _MAX_TRANSCRIPT_CHARS)
        sample_count = len(target_lines)
    else:
        # Plain text fallback. No sender labels — extractor treats it as
        # one person's writing samples.
        transcript = (
            f"Treat the following as a single person's writing samples (no \
labeled sender available). Target name: {target_sender or 'Unknown'}.\n\n"
            + raw_text[:_MAX_TRANSCRIPT_CHARS]
        )
        sample_count = max(1, len(raw_text) // 80)  # rough estimate

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            system=EXTRACTOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
    except Exception as exc:
        log.warning("style extract: Haiku failed: %s", exc)
        return None, sample_count

    block = next((b for b in response.content if b.type == "text"), None)
    if not block:
        return None, sample_count
    raw = block.text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    try:
        parsed_json = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("style extract: bad JSON: %s; raw=%r", exc, raw[:200])
        return None, sample_count

    try:
        profile = StyleProfile.model_validate(parsed_json)
    except ValidationError as exc:
        log.warning("style extract: schema mismatch: %s", exc)
        return None, sample_count

    return profile, sample_count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pick_target_sender(parsed_lines: list[ParsedLine]) -> str | None:
    """Pick the sender with the most messages. Heuristic — the "target" is
    usually the other party, but with two people we don't know which is the
    user. We let the user override via target_sender parameter."""
    if not parsed_lines:
        return None
    counter = Counter(s for s, _ in parsed_lines)
    if not counter:
        return None
    # Most frequent. If tied, returns the first encountered alphabetically.
    return counter.most_common(1)[0][0]


def _format_transcript(
    parsed_lines: list[ParsedLine], target: str, max_chars: int
) -> str:
    """Render the transcript with target messages clearly marked."""
    header = f"TARGET PERSON: {target}\n\nTranscript (analyze ONLY the TARGET's messages):\n\n"
    body_parts: list[str] = []
    used = len(header)
    for sender, text in parsed_lines:
        prefix = "TARGET" if sender == target else "OTHER"
        line = f"[{prefix}] {sender}: {text}\n"
        if used + len(line) > max_chars:
            body_parts.append("[transcript truncated]\n")
            break
        body_parts.append(line)
        used += len(line)
    return header + "".join(body_parts)
