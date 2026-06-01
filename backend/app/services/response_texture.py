"""Response texture policy.

Keeps expressive style natural without hardcoding specific emoji choices.
The model may choose symbols naturally, but this service controls frequency,
repetition, and situational appropriateness.
"""

from __future__ import annotations

import unicodedata
from typing import Any


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _is_emoji_like_symbol(ch: str) -> bool:
    """Detect emoji-like symbols without hardcoding actual emoji.

    This intentionally avoids a fixed emoji list. It uses Unicode metadata so
    any symbol used by recent assistant replies can be treated as repetition
    signal.
    """
    if not ch or ch.isspace():
        return False

    category = unicodedata.category(ch)
    name = unicodedata.name(ch, "")

    if category == "So":
        return True

    # Covers some pictographic symbols and dingbats without enumerating them.
    symbol_words = (
        "FACE",
        "HEART",
        "HAND",
        "SPARKLES",
        "MUSCLE",
        "FIRE",
        "STAR",
        "SUN",
        "MOON",
        "FLOWER",
        "PARTY",
        "THUMBS",
    )
    return category.startswith("S") and any(word in name for word in symbol_words)


def _recent_assistant_symbols(messages: list[dict], *, limit_messages: int = 8) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    assistant_messages = [
        m for m in messages[-limit_messages:] if m.get("role") == "assistant"
    ]

    for message in assistant_messages:
        content = message.get("content")
        if not isinstance(content, str):
            continue

        for ch in content:
            if _is_emoji_like_symbol(ch) and ch not in seen:
                symbols.append(ch)
                seen.add(ch)

    return symbols[:12]


def _assistant_emoji_turn_count(messages: list[dict], *, limit_messages: int = 4) -> int:
    count = 0
    assistant_messages = [
        m for m in messages[-limit_messages:] if m.get("role") == "assistant"
    ]

    for message in assistant_messages:
        content = message.get("content")
        if isinstance(content, str) and any(_is_emoji_like_symbol(ch) for ch in content):
            count += 1

    return count


def _is_serious_or_professional(user_message: str) -> bool:
    lower = user_message.lower()
    serious_terms = (
        "meeting",
        "rapat",
        "debitur",
        "nasabah",
        "komite",
        "deadline",
        "risk",
        "kredit",
        "bank",
        "urgent",
        "serius",
        "formal",
        "kerja",
        "client",
        "dokumen",
        "analisa",
        "presentasi",
    )
    return any(term in lower for term in serious_terms)


def _is_affectionate_or_light(user_message: str) -> bool:
    lower = user_message.lower()
    affectionate_terms = (
        "sayang",
        "beb",
        "peluk",
        "hug",
        "hehe",
        "huhu",
        "capek",
        "kangen",
        "lucu",
        "imut",
        "manja",
    )
    return any(term in lower for term in affectionate_terms)


def _get_user_mood_label(user_mood_context: Any) -> str:
    if not isinstance(user_mood_context, dict):
        return ""

    candidates = (
        user_mood_context.get("label"),
        user_mood_context.get("mood"),
        user_mood_context.get("state"),
        user_mood_context.get("primary_mood"),
    )

    for candidate in candidates:
        text = _as_text(candidate)
        if text:
            return text.lower()

    return ""


def _get_companion_mood_label(current_mood: Any) -> str:
    if not isinstance(current_mood, dict):
        return ""

    candidates = (
        current_mood.get("mood"),
        current_mood.get("state"),
        current_mood.get("label"),
        current_mood.get("emotion"),
    )

    for candidate in candidates:
        text = _as_text(candidate)
        if text:
            return text.lower()

    return ""


def render_response_texture_block(
    *,
    user_message: str | None,
    messages: list[dict],
    companion_settings_row: dict | None,
    current_mood: dict | None,
    user_mood_context: dict | None,
) -> str:
    """Return a compact style-control block for this turn.

    The block controls emoji frequency dynamically. It does not prescribe a
    fixed emoji list. The model may choose its own expression only when the
    situation calls for it.
    """
    text = _as_text(user_message)
    companion_settings_row = companion_settings_row or {}

    companion_mode = _as_text(companion_settings_row.get("companion_mode")).lower()
    preferences = companion_settings_row.get("preferences") or {}
    assistant_mode = (
        str(preferences.get("assistant_mode") or "life_companion").lower().strip()
        if isinstance(preferences, dict)
        else "life_companion"
    )
    is_chief_of_staff = assistant_mode == "chief_of_staff"
    user_mood = _get_user_mood_label(user_mood_context)
    companion_mood = _get_companion_mood_label(current_mood)

    recent_symbols = _recent_assistant_symbols(messages)
    recent_emoji_turns = _assistant_emoji_turn_count(messages)

    serious = _is_serious_or_professional(text)
    affectionate = _is_affectionate_or_light(text)

    max_symbols = 0
    reason = "default restraint"

    if is_chief_of_staff:
        max_symbols = 0
        reason = "chief_of_staff mode — structured, emoji-free professionalism"
    elif serious:
        max_symbols = 0
        reason = "professional or time-sensitive context"
    elif recent_emoji_turns >= 2:
        max_symbols = 0
        reason = "recent replies already used emoji-like symbols often"
    elif companion_mode in {"partner", "affectionate"} or affectionate:
        max_symbols = 1
        reason = "warm or affectionate context"
    elif user_mood in {"tired", "sad", "stressed", "anxious"}:
        max_symbols = 1
        reason = "gentle emotional support"
    elif companion_mood in {"playful", "warm", "affectionate"}:
        max_symbols = 1
        reason = "assistant mood allows light warmth"

    recent_line = (
        "- Recently used emoji-like symbols to avoid repeating: "
        + " ".join(recent_symbols)
        if recent_symbols
        else "- Recently used emoji-like symbols to avoid repeating: none detected"
    )

    return "\n".join(
        [
            "## Response texture and emoji control — high priority",
            f"- Emoji-like symbol budget for this reply: at most {max_symbols}.",
            f"- Reason: {reason}.",
            "- Do not use emoji-like symbols in every message.",
            "- If the budget is 0, use words for warmth instead of emoji-like symbols.",
            "- If the budget is 1, choose only if it truly fits the user's mood, assistant mood, and conversation situation.",
            "- Do not repeat the same emoji-like symbol across nearby replies.",
            "- Do not force a cheerful symbol into serious, work, deadline, finance, or meeting-related replies.",
            "- Never use emoji as a habit or signature.",
            "- Vary emotional expression through wording, pacing, and sentence shape, not repeated symbols.",
            recent_line,
        ]
    )
