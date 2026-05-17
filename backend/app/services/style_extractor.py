"""Style extraction.

Given parsed transcript lines (or a plain text blob), pick a target sender
and ask Haiku to extract a structured style profile.

We never persist the transcript itself. After analyze returns the profile,
the caller discards the input.

Phase 4.11b adds a deeper style layer. The first version only captured
abstract attributes (warmth, formality, emoji frequency). That is not enough
for recognizable chat style. Real texting style lives in cadence, message
shape, punctuation, filler words, emotional rhythm, and short behavioral
examples. This module now extracts those signals into JSONB without requiring
a database migration.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import settings
from app.services.claude import get_claude
from app.services.style_parser import ParsedLine, SourceType

log = logging.getLogger(__name__)


# Maximum transcript size we send to Haiku. Uploads can be much larger, but
# style analysis must stay bounded for cost/latency safety. These are env-backed
# via Settings so we can tune quality without code edits.
_DEFAULT_SAMPLE_CHARS = 80_000
_DEFAULT_MAX_SAMPLE_CHARS = 100_000

# Minimum messages from the target before we'll attempt extraction. Below
# this, the profile would be guesswork.
_MIN_TARGET_MESSAGES = 3

# For safety, behavioral examples are short. They are style anchors, not a
# transcript replay mechanism.
_MAX_EXEMPLAR_CHARS = 120
_MAX_EXEMPLARS_PER_BUCKET = 5


class StyleExemplars(BaseModel):
    """Short style anchors grouped by behavior.

    These are intentionally brief snippets. They help the main chat model
    mimic cadence and texture better than abstract labels do, while avoiding
    storage of long private transcript passages.
    """

    greeting: list[str] = Field(default_factory=list, max_length=5)
    casual_reaction: list[str] = Field(default_factory=list, max_length=5)
    teasing: list[str] = Field(default_factory=list, max_length=5)
    comforting: list[str] = Field(default_factory=list, max_length=5)
    affection: list[str] = Field(default_factory=list, max_length=5)
    question_style: list[str] = Field(default_factory=list, max_length=5)
    apology_or_repair: list[str] = Field(default_factory=list, max_length=5)
    encouragement: list[str] = Field(default_factory=list, max_length=5)
    goodbye: list[str] = Field(default_factory=list, max_length=5)
    fragmented_followup: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("*", mode="after")
    @classmethod
    def _clean_examples(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values or []:
            item = _sanitize_short_snippet(str(value))
            if item and item not in cleaned:
                cleaned.append(item)
            if len(cleaned) >= _MAX_EXEMPLARS_PER_BUCKET:
                break
        return cleaned


class PreferredRewrite(BaseModel):
    """User-supplied calibration: a generated phrase and a better target-like rewrite."""

    bad: str = Field(min_length=1, max_length=160)
    better: str = Field(min_length=1, max_length=160)

    @field_validator("bad", "better", mode="after")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return _sanitize_short_snippet(value, max_chars=160)


class StyleCalibration(BaseModel):
    """Human feedback that calibrates a style profile over time.

    This lives inside extracted_style JSONB to avoid a migration. It is not raw
    transcript storage; it is explicit user feedback about what sounds accurate
    or inaccurate.
    """

    positive_examples: list[str] = Field(default_factory=list, max_length=20)
    negative_examples: list[str] = Field(default_factory=list, max_length=20)
    preferred_rewrites: list[PreferredRewrite] = Field(default_factory=list, max_length=20)
    banned_phrases: list[str] = Field(default_factory=list, max_length=30)
    notes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("positive_examples", "negative_examples", "banned_phrases", "notes", mode="after")
    @classmethod
    def _clean_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values or []:
            item = _sanitize_short_snippet(str(value), max_chars=180)
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned


class StyleProfile(BaseModel):
    """Validated style profile.

    The legacy fields are preserved so existing frontend/database rows keep
    working. New fields capture deeper conversational texture for stronger
    style adaptation in chat.
    """

    # Legacy/high-level fields ------------------------------------------------
    display_name: str = Field(min_length=1, max_length=80)
    dominant_language: str = Field(min_length=1, max_length=40)
    language_mixing: str = Field(max_length=200)

    formality_level: str = Field(max_length=60)
    warmth_level: str = Field(max_length=60)
    directness_level: str = Field(max_length=60)

    humor_style: str = Field(max_length=200)
    emoji_usage: str = Field(max_length=200)
    average_reply_length: str = Field(max_length=120)

    greeting_style: str = Field(max_length=200)
    closing_style: str = Field(max_length=200)
    conflict_style: str = Field(max_length=220)
    support_style: str = Field(max_length=220)
    decision_making_style: str = Field(max_length=220)

    common_phrases: list[str] = Field(default_factory=list, max_length=10)
    do_not_copy: list[str] = Field(default_factory=list, max_length=10)

    # Deeper style fields -----------------------------------------------------
    cadence_signature: str = Field(default="unclear", max_length=500)
    message_shape: str = Field(default="unclear", max_length=500)
    punctuation_style: str = Field(default="unclear", max_length=350)
    linguistic_texture: list[str] = Field(default_factory=list, max_length=12)
    filler_words: list[str] = Field(default_factory=list, max_length=16)
    language_switching_behavior: str = Field(default="unclear", max_length=350)
    emotional_rhythm: str = Field(default="unclear", max_length=500)
    teasing_pattern: str = Field(default="unclear", max_length=350)
    reassurance_pattern: str = Field(default="unclear", max_length=350)
    question_style: str = Field(default="unclear", max_length=350)
    ai_polish_to_avoid: list[str] = Field(default_factory=list, max_length=10)
    exemplars: StyleExemplars = Field(default_factory=StyleExemplars)
    phrase_confidence: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    style_calibration: StyleCalibration = Field(default_factory=StyleCalibration)

    # Compact prose directive used by the chat prompt.
    compact_directive: str = Field(min_length=20, max_length=1200)

    @field_validator("common_phrases", "filler_words", "linguistic_texture", "ai_polish_to_avoid", mode="after")
    @classmethod
    def _clean_short_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values or []:
            item = _sanitize_short_snippet(str(value), max_chars=80)
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned

    @field_validator("do_not_copy", mode="after")
    @classmethod
    def _clean_avoid_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values or []:
            item = str(value).strip()
            if item and item not in cleaned:
                cleaned.append(item[:120])
        return cleaned


EXTRACTOR_SYSTEM_PROMPT = """You analyze chat messages from ONE specific target person \
and extract their texting style. Output strict JSON only.

The goal is NOT generic tone analysis. The goal is to capture the person's \
recognizable conversational texture: cadence, message shape, filler words, \
punctuation habits, emotional rhythm, and short style examples.

# Output schema (ALL keys required, even if value is "unclear" or [])

{
  "display_name": "the target person's name as it appears",
  "dominant_language": "English | Indonesian | Mandarin | mixed | ...",
  "language_mixing": "specific pattern, e.g. Indonesian base with English punchlines or work terms",

  "formality_level": "very casual | casual | neutral | formal | very formal",
  "warmth_level": "cold | reserved | neutral | warm | very warm",
  "directness_level": "very indirect | indirect | balanced | direct | blunt",

  "humor_style": "specific humor pattern in <20 words",
  "emoji_usage": "none | rare | occasional | frequent | heavy — include emoji types if clear",
  "average_reply_length": "very short | short | medium | long | varies — include message-burst tendency",

  "greeting_style": "how they open; mention style, not private content",
  "closing_style": "how they close or 'no consistent closing'",
  "conflict_style": "how they handle disagreement or tension",
  "support_style": "how they comfort/support others",
  "decision_making_style": "how they reason, commit, hedge, or decide",

  "common_phrases": ["up to 8 short snippets actually present; no full private sentences"],
  "phrase_confidence": [
    {"phrase": "short phrase actually present", "evidence_count": 3, "confidence": "high|medium|low"}
  ],
  "do_not_copy": ["private names, secrets, sensitive details, intimate references to avoid"],

  "cadence_signature": "how messages flow: bursty, fragmented, follow-ups, pauses, question density",
  "message_shape": "texting shape: one-liners, multi-line chunks, lowercase, repeated letters, etc.",
  "punctuation_style": "periods, commas, ellipses, exclamation, question marks, lowercase/caps habits",
  "linguistic_texture": ["up to 12 reusable style traits, not secrets"],
  "filler_words": ["short fillers/softeners actually present, e.g. sih, deh, yaa, wkwk"],
  "language_switching_behavior": "when/why they switch languages mid-message",
  "emotional_rhythm": "how they move between teasing, reassurance, concern, seriousness",
  "teasing_pattern": "specific teasing style or 'unclear'",
  "reassurance_pattern": "specific comfort/reassurance style or 'unclear'",
  "question_style": "how they ask questions: direct, stacked, softened, checking-in, etc.",
  "ai_polish_to_avoid": ["assistant-like habits to avoid when using this profile"],

  "exemplars": {
    "greeting": ["short non-sensitive snippets"],
    "casual_reaction": ["short non-sensitive snippets"],
    "teasing": ["short non-sensitive snippets"],
    "comforting": ["short non-sensitive snippets"],
    "affection": ["short non-sensitive snippets"],
    "question_style": ["short non-sensitive snippets"],
    "apology_or_repair": ["short non-sensitive snippets"],
    "encouragement": ["short non-sensitive snippets"],
    "goodbye": ["short non-sensitive snippets"],
    "fragmented_followup": ["short non-sensitive snippets"]
  },

  "style_calibration": {
    "positive_examples": [],
    "negative_examples": [],
    "preferred_rewrites": [],
    "banned_phrases": [],
    "notes": []
  },

  "compact_directive": "A strong style directive for future chat. Include cadence, fragmentation, punctuation, language switching, emotional rhythm, and anti-polish guidance. Never say to be or pretend to be the person."
}

# Rules

- Analyze ONLY messages marked TARGET. Ignore OTHER except as context.
- Do not summarize the relationship. Extract writing style only.
- Behavioral exemplars must be SHORT snippets actually present or very lightly anonymized.
- Never store or output secrets, phone numbers, addresses, exact long messages, or private details.
- If an exemplar contains a private name/detail, replace it with [name] or skip it.
- Do NOT invent common phrases. If uncertain, return [].
- For phrase_confidence, include only phrases observed in TARGET lines. evidence_count must reflect observed occurrences.
- The compact_directive is important. It should be stronger than generic tone labels. \
  It must tell the assistant HOW to shape messages: e.g. fragmented short bursts, \
  lowercase, softeners, teasing-then-reassurance, rarely uses periods.
- The compact_directive must not contain identity claims like "be Anna" or \
  "pretend to be Anna".
- If evidence is thin, use "unclear" and keep confidence implied by specificity.

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

        transcript = _format_representative_transcript(
            parsed_lines=parsed_lines,
            target=target,
            max_chars=_analysis_sample_chars(),
        )
        sample_count = len(target_lines)
    else:
        transcript = _format_plain_text_sample(
            raw_text=raw_text,
            target_sender=target_sender,
            max_chars=_analysis_sample_chars(),
        )
        sample_count = max(1, len(raw_text) // 80)  # rough estimate

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=3500,
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
        log.warning("style extract: bad JSON: %s; raw=%r", exc, raw[:400])
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


def _analysis_sample_chars() -> int:
    """Return bounded sample size for LLM style analysis.

    Uploads can be up to STYLE_ANALYSIS_UPLOAD_MAX_CHARS, but the actual LLM
    sample must stay within STYLE_ANALYSIS_MAX_CHARS. Defaults are chosen to
    improve imitation quality versus the old 30k limit while keeping cost safe.
    """
    requested = getattr(settings, "STYLE_ANALYSIS_SAMPLE_CHARS", _DEFAULT_SAMPLE_CHARS)
    hard_max = getattr(settings, "STYLE_ANALYSIS_MAX_CHARS", _DEFAULT_MAX_SAMPLE_CHARS)
    try:
        requested_i = int(requested)
        hard_max_i = int(hard_max)
    except Exception:
        return _DEFAULT_SAMPLE_CHARS
    return max(12_000, min(requested_i, hard_max_i))


def _pick_target_sender(parsed_lines: list[ParsedLine]) -> str | None:
    """Pick the sender with the most messages.

    Frontend should normally send target_sender, especially when the transcript
    includes the current user. This fallback is for curl/backward compatibility.
    """
    if not parsed_lines:
        return None
    counter = Counter(s for s, _ in parsed_lines)
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _format_representative_transcript(
    *, parsed_lines: list[ParsedLine], target: str, max_chars: int
) -> str:
    """Render a representative transcript sample.

    The old implementation used the first N characters, which often overfit to
    greetings and missed recent habits. This sampler keeps beginning/middle/end
    windows and gives extra budget to TARGET lines while preserving enough OTHER
    context for response style.
    """
    header = (
        f"TARGET PERSON: {target}\n\n"
        "Transcript sample (analyze ONLY TARGET messages).\n"
        "The sample is representative, not complete. Mimic style, not identity.\n\n"
    )
    budget = max_chars - len(header)
    if budget <= 1000:
        return header

    selected = _select_representative_lines(parsed_lines, target=target, max_lines=260)
    rendered = _render_lines(selected, target=target)

    if len(rendered) <= budget:
        return header + rendered

    # If still too long, prioritize target lines but keep nearby context marker.
    target_only = [(sender, text) for sender, text in selected if sender == target]
    rendered_target = _render_lines(target_only, target=target)
    if len(rendered_target) <= budget:
        return header + rendered_target + "\n[context omitted due to size]\n"

    return header + rendered_target[:budget] + "\n[transcript sampled/truncated]\n"


def _select_representative_lines(
    parsed_lines: list[ParsedLine], *, target: str, max_lines: int
) -> list[ParsedLine]:
    if len(parsed_lines) <= max_lines:
        return parsed_lines

    # Three timeline windows: early, middle, recent. Recent is slightly larger
    # because it often reflects the current communication style better.
    early_n = max_lines // 5
    mid_n = max_lines // 5
    recent_n = max_lines // 3

    mid_start = max(0, (len(parsed_lines) // 2) - (mid_n // 2))
    windows = [
        parsed_lines[:early_n],
        parsed_lines[mid_start : mid_start + mid_n],
        parsed_lines[-recent_n:],
    ]

    combined: list[ParsedLine] = []
    for window in windows:
        for line in window:
            if line not in combined:
                combined.append(line)

    # Balanced target-speaker samples. This matters more than raw character
    # count: style is revealed across situations (questions, teasing, support,
    # planning, short replies, long replies), not only in chronological order.
    target_lines = [(s, t) for s, t in parsed_lines if s == target]
    category_samples = _category_target_samples(target_lines, per_category=12)
    for line in category_samples:
        if line not in combined:
            combined.append(line)

    # If target is still underrepresented, add evenly spaced target messages.
    target_in_combined = sum(1 for s, _ in combined if s == target)
    desired_target = min(180, max(80, (max_lines * 2) // 3), len(target_lines))
    if target_in_combined < desired_target:
        additions = _evenly_spaced(target_lines, desired_target - target_in_combined)
        for line in additions:
            if line not in combined:
                combined.append(line)

    return combined[: max_lines + 120]


def _category_target_samples(target_lines: list[ParsedLine], *, per_category: int) -> list[ParsedLine]:
    buckets: dict[str, list[ParsedLine]] = {
        "short": [],
        "long": [],
        "question": [],
        "teasing_laugh": [],
        "support": [],
        "planning": [],
        "affection": [],
        "closing": [],
        "punctuation_texture": [],
    }
    for line in target_lines:
        _sender, text = line
        low = text.lower()
        compact = " ".join(low.split())

        if len(compact) <= 28:
            buckets["short"].append(line)
        if len(compact) >= 110:
            buckets["long"].append(line)
        if "?" in text or any(x in compact for x in ["apa", "siapa", "gimana", "kenapa", "jadi", "when", "where", "what"]):
            buckets["question"].append(line)
        if any(x in compact for x in ["wkwk", "haha", "hehe", "cie", "anj", "lol", "lmao"]):
            buckets["teasing_laugh"].append(line)
        if any(x in compact for x in ["jangan lupa", "istirahat", "semangat", "gapapa", "gpp", "take care", "tidur", "makan dulu"]):
            buckets["support"].append(line)
        if any(x in compact for x in ["jam", "nanti", "besok", "jadi", "meeting", "dinner", "makan", "where", "when"]):
            buckets["planning"].append(line)
        if any(x in compact for x in ["beb", "sayang", "dear", "love", "miss", "hid"]):
            buckets["affection"].append(line)
        if any(x in compact for x in ["ttyl", "bye", "dadah", "good night", "gn", "yauda", "yaudah"]):
            buckets["closing"].append(line)
        if any(x in text for x in ["😭", "😂", "🤣", "…", "...", "!!"]) or re.search(r"(\w){2,}", text):
            buckets["punctuation_texture"].append(line)

    selected: list[ParsedLine] = []
    for items in buckets.values():
        for line in _evenly_spaced(items, per_category):
            if line not in selected:
                selected.append(line)
    return selected


def _evenly_spaced(items: list[ParsedLine], count: int) -> list[ParsedLine]:
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return items
    step = (len(items) - 1) / max(1, count - 1)
    return [items[round(i * step)] for i in range(count)]


def _render_lines(lines: list[ParsedLine], *, target: str) -> str:
    out: list[str] = []
    for sender, text in lines:
        prefix = "TARGET" if sender == target else "OTHER"
        compact = " ".join(text.split())
        out.append(f"[{prefix}] {sender}: {compact}\n")
    return "".join(out)


def _format_plain_text_sample(*, raw_text: str, target_sender: str | None, max_chars: int) -> str:
    header = (
        "Treat the following as one person's writing samples. "
        f"Target name: {target_sender or 'Unknown'}.\n"
        "The sample may be partial. Extract style, cadence, and texture only.\n\n"
    )
    budget = max_chars - len(header)
    text = raw_text.strip()
    if len(text) <= budget:
        sample = text
    else:
        # beginning + middle + end beats first-N truncation for style.
        third = max(1, budget // 3)
        mid_start = max(0, (len(text) // 2) - (third // 2))
        sample = (
            text[:third]
            + "\n\n[...middle sample...]\n\n"
            + text[mid_start : mid_start + third]
            + "\n\n[...recent/end sample...]\n\n"
            + text[-third:]
        )
    return header + sample[:budget]


def _sanitize_short_snippet(value: str, *, max_chars: int = _MAX_EXEMPLAR_CHARS) -> str:
    """Remove obvious PII and keep snippet short.

    This is not a perfect anonymizer, but it prevents accidental storage of the
    most common sensitive tokens in exemplar fields. The extractor prompt also
    instructs the model to skip/anonymize private details.
    """
    text = " ".join(value.strip().split())
    if not text:
        return ""
    text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email]", text)
    text = re.sub(r"(?:\+?\d[\d\s().-]{7,}\d)", "[phone]", text)
    text = text.replace("\u200e", "").replace("\u200f", "")
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text
