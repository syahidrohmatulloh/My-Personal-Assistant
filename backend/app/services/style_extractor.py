"""Style extraction.

Given parsed transcript lines (or a plain text blob), pick a target sender
and ask Haiku to extract a structured style profile.

We never persist the transcript itself. After analyze returns the profile,
the caller discards the input.

Output is validated by Pydantic — so even if Haiku hallucinates extra
fields, we only persist what matches our schema.

Sampling strategy:
- Auto-tune the chars budget based on transcript size (12k for thin
  inputs, 30k for rich ones).
- For parsed transcripts: stratify into beginning / middle / end chunks
  so we capture greetings, ongoing rhythm, and closings.
- Always prioritize target messages.
- For unparsed (plain) inputs: same 3-chunk split on raw text.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.claude import get_claude
from app.services.style_parser import ParsedLine, SourceType, is_likely_user

log = logging.getLogger(__name__)


# Hard caps. The frontend also enforces 5MB at upload; the backend re-checks.
MAX_UPLOAD_CHARS = 5_000_000

# LLM input ceilings — auto-tuned per request between these bounds.
_LLM_MIN_CHARS = 12_000
_LLM_MAX_CHARS = 30_000

# Minimum target messages before we'll attempt extraction.
_MIN_TARGET_MESSAGES = 3


class StyleProfile(BaseModel):
    """Validated style profile. Constraints are generous — we'd rather store
    a slightly verbose profile than reject Haiku's output entirely. Truncation
    happens in a validator below."""

class StyleProfile(BaseModel):
    """Rich style profile (v2). Extraction focuses on actionable patterns
    Claude can imitate, plus literal verbatim snippets ("exemplars") that
    anchor the texture in the system prompt.

    v1 profiles had abstract scales like warmth_level: "warm" — Claude
    couldn't act on those. v2 fields describe concrete behaviors and carry
    actual short snippets from the source person.
    """

    # Schema version. Older profiles (no schema_version) are v1 and the
    # prompt builder renders them differently. Newer profiles are v2.
    schema_version: int = Field(default=2)

    display_name: str = Field(min_length=1, max_length=200)
    dominant_language: str = Field(min_length=1, max_length=120)
    language_mixing: str = Field(default="", max_length=400)

    # === Conversational rhythm ===
    # How messages are SHAPED on the screen — fragmentation, length, pacing
    message_shape: str = Field(default="", max_length=500)
    # e.g. "Sends 2-4 short messages back to back, fragmented mid-thought"

    sentence_style: str = Field(default="", max_length=500)
    # e.g. "Incomplete sentences, drops subjects, runs words together"

    punctuation_habits: str = Field(default="", max_length=400)
    # e.g. "Rarely uses periods. Multiple exclamation marks for emphasis.
    #       Uses '..' instead of '...'. Lowercase always."

    # === Linguistic texture ===
    fillers_and_softeners: str = Field(default="", max_length=400)
    # e.g. "Heavy use of 'sih', 'kan', 'yaa', 'kok'. English filler: 'like'."

    capitalization: str = Field(default="", max_length=200)
    # e.g. "All lowercase always" or "Sentence case, no all-caps"

    emoji_pattern: str = Field(default="", max_length=400)
    # e.g. "Rare. Only 😭 for self-deprecation, 🥹 for affection."

    # === Emotional texture ===
    affection_style: str = Field(default="", max_length=400)
    # e.g. "Subtle. Uses 'beb' or 'sayang' once per conversation, not more."

    teasing_style: str = Field(default="", max_length=400)
    # e.g. "Gentle teasing followed by reassurance within 2 messages."

    support_style: str = Field(default="", max_length=400)
    # e.g. "Practical first ('udah makan?'), emotional second."

    closing_style: str = Field(default="", max_length=300)
    # e.g. "Trails off without closing. Or short 'ok ttyl'."

    # === Conversational asymmetry ===
    initiation_pattern: str = Field(default="", max_length=300)
    # e.g. "Often initiates with a question or observation, not greeting"

    response_tendency: str = Field(default="", max_length=300)
    # e.g. "Reacts more than initiates. Mirrors the other person's energy."

    # === Exemplars — LITERAL verbatim snippets from the source ===
    # These are the texture anchors that make imitation recognizable.
    # Each: a short message exactly as the source person wrote it.
    exemplars: list[str] = Field(default_factory=list, max_length=15)

    # Common short phrases/fillers extracted verbatim (separate from exemplars
    # because phrases are 1-3 words, exemplars are whole short messages).
    common_phrases: list[str] = Field(default_factory=list, max_length=20)

    # Content the assistant must NEVER reproduce — sensitive names, secrets,
    # intimate references. Extractor errs on the side of including more.
    do_not_copy: list[str] = Field(default_factory=list, max_length=20)

    # Compact actionable directive — used at every chat turn.
    compact_directive: str = Field(min_length=10, max_length=1200)


EXTRACTOR_SYSTEM_PROMPT = """You analyze chat messages from ONE specific person and extract their communication style as actionable patterns + literal short snippets. Output strict JSON only.

# CRITICAL: This is for an AI assistant to IMITATE conversational TEXTURE, not impersonate identity. Extract patterns that make their texting recognizable: rhythm, fragmentation, fillers, punctuation. Avoid extracting full sentences or personal content.

# Output schema (ALL keys required)

{
  "schema_version": 2,
  "display_name": "the person's name as it appears in the transcript",
  "dominant_language": "Indonesian | English | Mandarin | mixed | etc",
  "language_mixing": "if mixed: WHERE switching happens. e.g. 'Indonesian base; English for tech terms or jokes; switches to Indonesian when emotional'. Else: 'monolingual'",

  "message_shape": "How they SHAPE messages on screen. Fragmented across multiple messages? Single long blocks? Examples: 'Sends 2-4 short messages back to back instead of one paragraph', 'One long message per turn', 'Mixes: short for quick reaction, long when explaining'",

  "sentence_style": "Complete vs fragmented sentences. Subject drops. Run-ons. e.g. 'Drops subjects often (\\"udah makan?\\" instead of \\"kamu udah makan?\\"). Incomplete sentences. Conversational fragments.'",

  "punctuation_habits": "Period usage, exclamations, ellipses, repeated letters. e.g. 'Rarely uses periods. Doubles or triples letters for emphasis (\\"okayy\\", \\"hmmmm\\"). Uses \\"..\\" instead of \\"...\\". One exclamation max.'",

  "fillers_and_softeners": "VERBATIM list of fillers/particles they actually use. e.g. 'sih, kan, yaa, kok, deh, dong, lah'. English: 'like, lol, lmao, idk'. Quote exactly as written.",

  "capitalization": "e.g. 'All lowercase always' | 'Sentence case' | 'Starts capitalized then drops mid-sentence'",

  "emoji_pattern": "Which emojis specifically, how often, what context. e.g. 'Almost none. Occasional 😭 for embarrassment, 🥹 for affection. Never uses 👍 or 🙏'",

  "affection_style": "How they show warmth. e.g. 'Subtle. Uses nickname \\"beb\\" or \\"sayang\\" once per conversation. Asks practical care questions (\\"udah makan?\\", \\"jangan lupa istirahat\\")'",

  "teasing_style": "Do they tease? How? e.g. 'Gentle teasing then reassurance: \\"haha gaje\\" → \\"becanda yaa\\"' or 'Not a teaser, mostly earnest'",

  "support_style": "How they comfort. e.g. 'Practical first (\\"udah makan?\\"), emotional acknowledgment second. Avoids advice-giving.'",

  "closing_style": "How they end conversations. e.g. 'Trails off, no formal closing. Or just \\"ok ttyl 👋\\"' | 'No consistent closing'",

  "initiation_pattern": "How they OPEN conversations. e.g. 'Direct question or observation, no \\"hi\\" first' | 'Always greets first with \\"hey\\"'",

  "response_tendency": "Initiator vs reactor. Match energy or set energy? e.g. 'Reacts more than initiates. Matches the other person's energy and length.'",

  "exemplars": [
    "5-12 SHORT messages quoted EXACTLY as the person wrote them. Pick variety: a short reaction, a longer explanation, a fragment, an affectionate one, a teasing one, a question. KEEP THEM SHORT (under 80 chars each). Do NOT pick messages with private details, full names of other people, specific dates, or intimate content."
  ],

  "common_phrases": [
    "Short verbatim fillers/phrases they repeat. 1-3 words each. e.g. ['sih', 'wkwk', 'iya gpp', 'kayak gitu']"
  ],

  "do_not_copy": [
    "Private/sensitive content the assistant must NEVER reproduce. Specific personal names (other than target's display name), pet names, addresses, contacts, intimate references, secrets, anything that would be weird to hear from an AI. Be conservative."
  ],

  "compact_directive": "A 60-150 word directive the assistant reads every turn. Be SPECIFIC and ACTIONABLE. Quote the actual fillers, mention the actual punctuation habits, describe the actual cadence. Example structure: 'Send fragmented short messages (2-3 per turn) rather than one block. All lowercase. Rarely use periods, sometimes use \\"..\\". Mix Indonesian base with English for tech or jokes. Use fillers: sih, yaa, kok, wkwk. Affection through practical care questions (\\"udah makan?\\"), not declarations. Tease gently then reassure within the same exchange. Match the other person's energy rather than setting your own. Trail off rather than closing formally.'"
}

# Hard rules

- VERBATIM means VERBATIM. Quote exactly as the person wrote (typos, lowercase, repeated letters preserved).
- Exemplars MUST be from the transcript. Do not generate examples. If uncertain, use empty array.
- Exemplars MUST be short standalone messages (under 80 chars). Skip anything with private content.
- do_not_copy: include third-party names mentioned in messages, location names, anything intimate, anything specific that would be unsettling for an AI to reference.
- compact_directive is THE most important field. It is read every chat turn. Make it specific, quote actual fillers/patterns, describe actual cadence — not abstract levels.
- If the transcript is thin/unclear for a field, use "" for strings or [] for lists. Don't invent.

Output ONLY the JSON object. No prose, no markdown fences."""


async def extract_style(
    *,
    source_type: SourceType,
    parsed_lines: list[ParsedLine],
    raw_text: str,
    target_sender: str | None = None,
    user_name: str | None = None,
    user_aliases: list[str] | None = None,
    user_email: str | None = None,
) -> tuple[StyleProfile | None, int, list[str]]:
    """Extract a style profile from parsed lines (or raw text if parsing failed).

    Returns (profile_or_none, sample_count, warnings).
    sample_count = number of messages from the target sender.
    warnings    = list of strings for the UI to surface (e.g. "looks like
                  your own writing").
    """
    warnings: list[str] = []

    # Decide what to send Haiku.
    if parsed_lines:
        # Pick target: explicit > non-user-most-active > most-active fallback.
        target = target_sender or _pick_target_sender(
            parsed_lines,
            user_name=user_name,
            user_aliases=user_aliases,
            user_email=user_email,
        )
        if not target:
            return None, 0, ["No senders detected in transcript"]

        # Warn if the picked target itself looks like the user.
        if is_likely_user(
            target,
            user_name=user_name,
            user_aliases=user_aliases,
            user_email=user_email,
        ):
            warnings.append(
                "The selected sender looks like your own messages. This will analyze "
                "your own writing style, which may not be what you want."
            )

        target_lines = [(s, t) for s, t in parsed_lines if s == target]
        if len(target_lines) < _MIN_TARGET_MESSAGES:
            log.info(
                "style extract: target '%s' has only %d msgs, below threshold",
                target,
                len(target_lines),
            )
            warnings.append(
                f"Only {len(target_lines)} messages from '{target}' — not enough to extract a reliable style."
            )
            return None, len(target_lines), warnings

        # Auto-tune chars budget based on transcript richness.
        budget = _auto_budget(
            target_msg_count=len(target_lines),
            total_chars=sum(len(t) for _, t in parsed_lines),
        )
        transcript = _build_stratified_sample(
            parsed_lines, target=target, max_chars=budget
        )
        sample_count = len(target_lines)

        # Sparse-target signal: enough to extract, but flag low confidence.
        if len(target_lines) < 15:
            warnings.append(
                f"Only {len(target_lines)} messages analyzed — extracted style may be less reliable."
            )
    else:
        # Plain text fallback: split raw text into begin/mid/end.
        budget = _auto_budget(target_msg_count=0, total_chars=len(raw_text))
        transcript = _build_plain_sample(raw_text, max_chars=budget, target_name=target_sender)
        sample_count = max(1, len(raw_text) // 80)
        warnings.append(
            "Transcript format wasn't recognized as WhatsApp or Telegram — analyzing as plain text."
        )

    log.info(
        "style extract: sending %d chars to Haiku (target=%s, sample_count=%d)",
        len(transcript),
        target_sender or "auto",
        sample_count,
    )

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=4000,
            system=EXTRACTOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
    except Exception as exc:
        # Distinguish timeout from other errors for the user.
        msg = f"Style analysis failed: {exc.__class__.__name__}"
        log.warning("style extract: Haiku failed: %s", exc, exc_info=True)
        warnings.append(msg)
        return None, sample_count, warnings

    block = next((b for b in response.content if b.type == "text"), None)
    if not block:
        log.warning("style extract: no text block in response; stop_reason=%s", getattr(response, "stop_reason", "?"))
        warnings.append("Style analysis returned no result. Try a shorter transcript.")
        return None, sample_count, warnings
    raw = block.text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    # If Haiku response was truncated by max_tokens, the JSON is incomplete.
    # Log this explicitly so we can spot it in Fly logs.
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "max_tokens":
        log.warning(
            "style extract: response was truncated at max_tokens=3000. raw_tail=%r",
            raw[-200:],
        )

    try:
        parsed_json = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("style extract: bad JSON: %s; raw=%r", exc, raw[:500])
        warnings.append(
            "Could not parse style analysis. The transcript may be too complex — try with a smaller sample."
        )
        return None, sample_count, warnings

    # Pre-validate: trim oversized fields so we don't lose the whole profile
    # to a single over-long string.
    parsed_json = _trim_profile_fields(parsed_json)

    try:
        profile = StyleProfile.model_validate(parsed_json)
    except ValidationError as exc:
        # Log full detail so we can see which field failed.
        log.warning(
            "style extract: schema mismatch. errors=%s; keys=%s",
            exc.errors()[:5],
            list(parsed_json.keys()) if isinstance(parsed_json, dict) else "n/a",
        )
        warnings.append(
            f"Style analysis was incomplete ({len(exc.errors())} field issue(s)). "
            "Try analyzing a different sender or a smaller portion of the transcript."
        )
        return None, sample_count, warnings

    return profile, sample_count, warnings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FIELD_CAPS: dict[str, int] = {
    "display_name": 200,
    "dominant_language": 120,
    "language_mixing": 400,
    "message_shape": 500,
    "sentence_style": 500,
    "punctuation_habits": 400,
    "fillers_and_softeners": 400,
    "capitalization": 200,
    "emoji_pattern": 400,
    "affection_style": 400,
    "teasing_style": 400,
    "support_style": 400,
    "closing_style": 300,
    "initiation_pattern": 300,
    "response_tendency": 300,
    "compact_directive": 1200,
}

# Required string fields that get a default if Haiku omits them.
_REQUIRED_STRING_DEFAULTS: dict[str, str] = {
    "language_mixing": "monolingual",
    "message_shape": "unclear",
    "sentence_style": "unclear",
    "punctuation_habits": "unclear",
    "fillers_and_softeners": "unclear",
    "capitalization": "unclear",
    "emoji_pattern": "unclear",
    "affection_style": "unclear",
    "teasing_style": "unclear",
    "support_style": "unclear",
    "closing_style": "unclear",
    "initiation_pattern": "unclear",
    "response_tendency": "unclear",
}


def _trim_profile_fields(d: dict) -> dict:
    """Trim string fields to their schema caps and fill missing defaults.

    Without this, a single Haiku field overflow blows up the whole profile.
    """
    if not isinstance(d, dict):
        return d

    out = dict(d)

    # Truncate strings
    for key, cap in _FIELD_CAPS.items():
        v = out.get(key)
        if isinstance(v, str) and len(v) > cap:
            out[key] = v[: cap - 1].rstrip() + "…"

    # Fill missing string defaults
    for key, default in _REQUIRED_STRING_DEFAULTS.items():
        if not out.get(key):
            out[key] = default

    # Cap list fields. Exemplars allow longer per-item (full short messages);
    # other lists are short phrases.
    list_specs = {
        "exemplars": (15, 200),         # max items, max chars per item
        "common_phrases": (20, 80),
        "do_not_copy": (20, 200),
    }
    for key, (max_items, max_chars) in list_specs.items():
        v = out.get(key)
        if isinstance(v, list):
            cleaned: list[str] = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    cleaned.append(item[:max_chars])
            out[key] = cleaned[:max_items]
        elif v is None:
            out[key] = []

    return out


def _auto_budget(*, target_msg_count: int, total_chars: int) -> int:
    """Pick LLM input size.

    Heuristic — small for thin inputs, larger for rich ones. Reasoning:
    short transcripts already fit in 12k; long ones need 30k to retain
    breadth of signal after stratified sampling.
    """
    # Plain-text path (no target_msg_count): scale on total chars only.
    if target_msg_count == 0:
        if total_chars <= 8_000:
            return _LLM_MIN_CHARS
        if total_chars >= 40_000:
            return _LLM_MAX_CHARS
        # Linear in between.
        span = _LLM_MAX_CHARS - _LLM_MIN_CHARS
        progress = (total_chars - 8_000) / (40_000 - 8_000)
        return int(_LLM_MIN_CHARS + span * progress)

    # Parsed path: scale on target message count primarily.
    if target_msg_count <= 20 and total_chars <= 8_000:
        return _LLM_MIN_CHARS
    if target_msg_count >= 50 or total_chars >= 40_000:
        return _LLM_MAX_CHARS
    # Linear in between (weight count > chars).
    span = _LLM_MAX_CHARS - _LLM_MIN_CHARS
    progress = max(
        (target_msg_count - 20) / 30,
        (total_chars - 8_000) / (40_000 - 8_000),
    )
    return int(_LLM_MIN_CHARS + span * max(0.0, min(1.0, progress)))


def _pick_target_sender(
    parsed_lines: list[ParsedLine],
    *,
    user_name: str | None = None,
    user_aliases: list[str] | None = None,
    user_email: str | None = None,
) -> str | None:
    """Pick the most-active sender that does NOT look like the current user.

    Fallback to overall most-active if every sender looks like the user.
    """
    if not parsed_lines:
        return None
    counter = Counter(s for s, _ in parsed_lines)
    if not counter:
        return None

    ordered = counter.most_common()
    # First pass: skip likely-user senders.
    for name, _ in ordered:
        if not is_likely_user(
            name,
            user_name=user_name,
            user_aliases=user_aliases,
            user_email=user_email,
        ):
            return name
    # All look like user — return the most-active one with a warning upstream.
    return ordered[0][0]


def _build_stratified_sample(
    parsed_lines: list[ParsedLine], *, target: str, max_chars: int
) -> str:
    """Build a sample with beginning / middle / end slices.

    Within each slice we include both target and other senders (other senders
    give Claude conversational context — needed to read tone).
    """
    header = (
        f"TARGET PERSON: {target}\n\n"
        f"Transcript excerpts (analyze ONLY the TARGET's messages — OTHER "
        f"messages are context). Excerpts come from beginning, middle, and "
        f"recent portions of the conversation.\n\n"
    )

    total = len(parsed_lines)
    if total == 0:
        return header

    # Budget allocation: 30% beginning, 30% middle, 40% end (recent style
    # weights more in present-day extraction).
    budget = max_chars - len(header)
    chunk_budget = (int(budget * 0.30), int(budget * 0.30), int(budget * 0.40))

    # Slice boundaries.
    third = max(1, total // 3)
    slices = [
        ("Beginning", parsed_lines[:third]),
        ("Middle", parsed_lines[third : 2 * third]),
        ("Recent", parsed_lines[2 * third :]),
    ]

    body_parts: list[str] = []
    for (label, lines), budget_chars in zip(slices, chunk_budget):
        if not lines or budget_chars <= 0:
            continue
        body_parts.append(f"--- {label} ---\n")
        used = 0
        for sender, text in lines:
            prefix = "TARGET" if sender == target else "OTHER"
            line = f"[{prefix}] {sender}: {text}\n"
            if used + len(line) > budget_chars:
                break
            body_parts.append(line)
            used += len(line)
        body_parts.append("\n")

    return header + "".join(body_parts)


def _build_plain_sample(text: str, *, max_chars: int, target_name: str | None) -> str:
    """Sample a plain text blob from beginning / middle / end."""
    header = (
        f"Treat the following as a single person's writing samples "
        f"(no labeled sender available). Target name: {target_name or 'Unknown'}.\n"
        f"Excerpts are from different sections of the transcript.\n\n"
    )

    budget = max_chars - len(header)
    if len(text) <= budget:
        return header + text

    third = budget // 3
    n = len(text)
    return (
        header
        + "--- Beginning ---\n"
        + text[:third]
        + "\n\n--- Middle ---\n"
        + text[n // 2 - third // 2 : n // 2 + third // 2]
        + "\n\n--- Recent ---\n"
        + text[-third:]
    )
