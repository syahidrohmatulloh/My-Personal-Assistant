"""Generic role-based name normalization.

No user-specific or assistant-specific names are hardcoded here.
The code separates:
- user name: "nama saya X"
- assistant name: "nama assistant kamu Y"

It rejects role words as names and compares dynamically against the current
assistant name when available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitNames:
    user_name: str | None = None
    assistant_name: str | None = None


_ROLE_ONLY_WORDS = {
    "assistant",
    "asisten",
    "ai",
    "bot",
    "chatbot",
}

_LEADING_NON_NAME_WORDS = {
    "kamu",
    "mu",
    "saya",
    "aku",
    "adalah",
    "itu",
    "is",
    "named",
    "called",
    "bernama",
}


def _clean_raw_name(value: str | None) -> str | None:
    cleaned = " ".join(str(value or "").strip().split())
    if not cleaned:
        return None

    cleaned = re.sub(r"[.!?,;:]+$", "", cleaned).strip()
    if not cleaned:
        return None

    # If the model accidentally returns "kamu X", remove leading non-name tokens.
    # This is role/grammar cleanup, not hardcoded personal data.
    parts = cleaned.split()
    while len(parts) > 1 and parts[0].lower() in _LEADING_NON_NAME_WORDS:
        parts = parts[1:]
    cleaned = " ".join(parts).strip()
    cleaned = re.sub(r"[.!?,;:]+$", "", cleaned).strip()

    if not cleaned or len(cleaned) > 80:
        return None

    if cleaned.lower() in _ROLE_ONLY_WORDS:
        return None

    return cleaned


def normalize_assistant_name(value: str | None) -> str | None:
    return _clean_raw_name(value)


def normalize_user_name(
    value: str | None,
    *,
    current_assistant_name: str | None = None,
) -> str | None:
    cleaned = _clean_raw_name(value)
    if not cleaned:
        return None

    current_assistant = normalize_assistant_name(current_assistant_name)
    if current_assistant and cleaned.casefold() == current_assistant.casefold():
        return None

    return cleaned


def extract_explicit_names(text: str | None) -> ExplicitNames:
    raw = " ".join(str(text or "").strip().split())
    if not raw:
        return ExplicitNames()

    assistant_name = None
    user_name = None

    assistant_patterns = [
        r"\b(?:nama\s+(?:assistant|asisten|ai|bot)(?:\s+(?:kamu|mu))?)\s*(?:adalah|itu|is|=)?\s+([A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80})",
        r"\b(?:your\s+name|assistant\s+name|bot\s+name)\s*(?:is|=)?\s+([A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80})",
        r"\b(?:panggil\s+(?:kamu|assistant|asisten|ai|bot))\s+([A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80})",
    ]

    for pattern in assistant_patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            assistant_name = normalize_assistant_name(match.group(1))
            if assistant_name:
                break

    user_patterns = [
        r"\b(?:nama\s+(?:saya|aku))\s*(?:adalah|itu|is|=)?\s+([A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80})",
        r"\b(?:my\s+name\s+is|i\s+am|i'm)\s+([A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80})",
        r"\b(?:panggil\s+(?:saya|aku))\s+([A-Za-zÀ-ÖØ-öø-ÿ' -]{2,80})",
    ]

    for pattern in user_patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            user_name = normalize_user_name(match.group(1), current_assistant_name=assistant_name)
            if user_name:
                break

    return ExplicitNames(user_name=user_name, assistant_name=assistant_name)


def evidence_refers_to_assistant_name(evidence: list[str] | None, content: str | None = None) -> bool:
    blob = " ".join([*(evidence or []), str(content or "")]).lower()
    return bool(
        re.search(
            r"\b(nama\s+(assistant|asisten|ai|bot)|assistant\s+name|your\s+name|panggil\s+(kamu|assistant|asisten|ai|bot))\b",
            blob,
        )
    )



_EXPLICIT_ASSISTANT_RENAME_PATTERNS = (
    r"\b(?:nama\s+(?:kamu|mu))\s+(?:adalah|jadi|is|=|:)?\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9 _.'-]{2,80})",
    r"\b(?:ganti|ubah|set|change)\s+nama\s+(?:kamu|mu|assistant|asisten|ai|bot)\s+(?:jadi|ke|to|as|=|:)?\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9 _.'-]{2,80})",
    r"\b(?:mulai\s+sekarang|from\s+now\s+on)\s+nama\s+(?:kamu|mu|assistant|asisten|ai|bot)\s+(?:adalah|jadi|is|=|:)?\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9 _.'-]{2,80})",
    r"\b(?:your\s+name|assistant\s+name|bot\s+name|ai\s+name)\s*(?:is|=|:)?\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9 _.'-]{2,80})",
    r"\b(?:nama\s+(?:assistant|asisten|ai|bot)\s+(?:kamu|mu))\s+(?:adalah|jadi|is|=|:)?\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9 _.'-]{2,80})",
)


def _extract_strict_assistant_name_from_text(text: str | None) -> str | None:
    raw = str(text or "")
    for pattern in _EXPLICIT_ASSISTANT_RENAME_PATTERNS:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            value = normalize_assistant_name(match.group(1))
            if value:
                return value
    return None


def message_explicitly_renames_assistant(text: str | None) -> bool:
    return _extract_strict_assistant_name_from_text(text) is not None


_original_extract_explicit_names_assistant_name_phrase_guard = extract_explicit_names


def extract_explicit_names(
    text: str,
    current_assistant_name: str | None = None,
) -> ExplicitNames:
    names = _original_extract_explicit_names_assistant_name_phrase_guard(
        text,
        current_assistant_name=current_assistant_name,
    )
    strict_assistant_name = _extract_strict_assistant_name_from_text(text)
    if names.assistant_name and not strict_assistant_name:
        return ExplicitNames(user_name=names.user_name, assistant_name=None)
    if strict_assistant_name:
        return ExplicitNames(user_name=names.user_name, assistant_name=strict_assistant_name)
    return names


_original_evidence_refers_to_assistant_name_phrase_guard = evidence_refers_to_assistant_name


def evidence_refers_to_assistant_name(
    evidence: list[str] | None,
    content: str | None = None,
) -> bool:
    haystack = "\n".join([*(evidence or []), str(content or "")])
    return message_explicitly_renames_assistant(haystack)


# Final compatibility override:
# Some older versions of extract_explicit_names only accept (text), not
# (text, current_assistant_name=...). Keep the strict assistant rename rule
# without assuming the older function signature.
def extract_explicit_names(
    text: str,
    current_assistant_name: str | None = None,
) -> ExplicitNames:
    try:
        names = _original_extract_explicit_names_assistant_name_phrase_guard(text)
    except NameError:
        names = ExplicitNames(user_name=None, assistant_name=None)

    strict_assistant_name = _extract_strict_assistant_name_from_text(text)

    if strict_assistant_name:
        return ExplicitNames(
            user_name=getattr(names, "user_name", None),
            assistant_name=strict_assistant_name,
        )

    return ExplicitNames(
        user_name=getattr(names, "user_name", None),
        assistant_name=None,
    )

# Final assistant-name cleanup:
# Handles explicit rename phrases such as:
# - "nama kamu sekarang Andini" -> "Andini"
# - "nama kamu jadi Dina" -> "Dina"
# This runs after the existing normalizer so old behavior stays intact.
import re as _assistant_name_timeword_re

_original_normalize_assistant_name_strip_leading_timewords = normalize_assistant_name

def _strip_assistant_name_leading_timewords(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = str(value).strip()
    cleaned = _assistant_name_timeword_re.sub(
        r"^(?:sekarang|jadi|menjadi|adalah|namanya|itu)\s+",
        "",
        cleaned,
        flags=_assistant_name_timeword_re.IGNORECASE,
    ).strip(" .,:;!?\"'`")

    return cleaned or None

def normalize_assistant_name(value: str | None) -> str | None:
    cleaned = _original_normalize_assistant_name_strip_leading_timewords(value)
    stripped = _strip_assistant_name_leading_timewords(cleaned)
    if not stripped:
        return None
    return _original_normalize_assistant_name_strip_leading_timewords(stripped)
