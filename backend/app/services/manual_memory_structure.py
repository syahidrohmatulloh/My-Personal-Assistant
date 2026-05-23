"""Manual memory auto-structuring.

User-facing UX should only require the user to write what Aliyya should
remember. The backend is responsible for organizing it into:
- category
- structured_field
- structured_value

Guarantee:
Every manual memory returns non-empty category, structured_field, and
structured_value.

Design:
- Deterministic and conservative.
- Does not call an LLM.
- Generic English "I like ..." is NOT enough to classify as preferences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


DEFAULT_CATEGORY = "other"
DEFAULT_FIELD = "manual_memory"
MAX_VALUE_CHARS = 300

ALLOWED_CATEGORIES = {
    "identity",
    "important_dates",
    "preferences",
    "relationships",
    "routines",
    "goals",
    "constraints",
    "other",
}


@dataclass(frozen=True)
class StructuredManualMemory:
    category: str
    structured_field: str
    structured_value: str


def auto_structure_manual_memory(
    *,
    content: str,
    category: str | None = None,
    structured_field: str | None = None,
    structured_value: str | None = None,
) -> StructuredManualMemory:
    """Return category/key/value for a manually added memory.

    Backend guarantee:
    - category is always non-empty
    - structured_field is always non-empty
    - structured_value is always non-empty
    """
    text = _compact(content)

    explicit_field = _clean_field(structured_field)
    explicit_value = _clean_value_or_none(structured_value)

    if explicit_field and explicit_value:
        return StructuredManualMemory(
            category=_clean_category(category),
            structured_field=explicit_field,
            structured_value=explicit_value,
        )

    if explicit_field and not explicit_value:
        return StructuredManualMemory(
            category=_clean_category(category),
            structured_field=explicit_field,
            structured_value=_clean_value(text),
        )

    if not text:
        return StructuredManualMemory(
            category=_clean_category(category),
            structured_field=DEFAULT_FIELD,
            structured_value="empty_memory",
        )

    specific = _detect_specific_memory(text)
    if specific:
        return specific

    detected_category = _detect_category(text)
    final_category = detected_category or _clean_category(category)

    return StructuredManualMemory(
        category=final_category,
        structured_field=DEFAULT_FIELD,
        structured_value=_clean_value(text),
    )


def _detect_specific_memory(text: str) -> StructuredManualMemory | None:
    low = text.lower()

    timezone = _detect_timezone(text)
    if timezone:
        return StructuredManualMemory("identity", "timezone", timezone)

    # Avoided names must be checked before preferred names because:
    # "jangan panggil saya pak" contains "panggil saya".
    avoided_name = _detect_avoided_name(text)
    if avoided_name:
        return StructuredManualMemory("preferences", "avoid_calling_user", avoided_name)

    preferred_name = _detect_preferred_name(text)
    if preferred_name:
        return StructuredManualMemory("identity", "preferred_name", preferred_name)

    birthday = _detect_birthday(text)
    if birthday:
        return StructuredManualMemory("important_dates", "birthday", birthday)

    assistant_name = _detect_assistant_name(text)
    if assistant_name:
        return StructuredManualMemory("preferences", "assistant_name", assistant_name)

    if _has_any(
        low,
        [
            "jangan incremental",
            "jangan nebak",
            "jangan asal",
            "hati-hati",
            "menyeluruh",
            "root cause",
            "comprehensive",
            "careful patch",
            "complete patch",
        ],
    ):
        return StructuredManualMemory(
            "relationships",
            "interaction_preference",
            _clean_value(text),
        )

    if _has_any(
        low,
        [
            "ui",
            "ux",
            "vibes",
            "theme-aware",
            "dark mode",
            "light mode",
            "mobile",
            "sidebar",
            "kontras",
            "contrast",
            "glass",
        ],
    ):
        return StructuredManualMemory(
            "preferences",
            "ui_preference",
            _clean_value(text),
        )

    if _has_any(
        low,
        [
            "my goal",
            "goal saya",
            "target saya",
            "ingin mencapai",
            "mau mencapai",
            "i want to build",
            "saya ingin membangun",
        ],
    ):
        return StructuredManualMemory(
            "goals",
            "user_goal",
            _clean_value(text),
        )

    if _has_any(
        low,
        [
            "setiap pagi",
            "setiap malam",
            "tiap hari",
            "every morning",
            "every night",
            "daily routine",
            "rutinitas",
        ],
    ):
        return StructuredManualMemory(
            "routines",
            "routine",
            _clean_value(text),
        )

    if _has_any(
        low,
        [
            "tidak boleh",
            "jangan",
            "do not",
            "don't",
            "never",
            "avoid",
        ],
    ):
        return StructuredManualMemory(
            "constraints",
            "constraint",
            _clean_value(text),
        )

    if _has_any(
        low,
        [
            "wife",
            "istri",
            "husband",
            "suami",
            "daughter",
            "anak",
            "mother",
            "ayah",
            "ibu",
            "friend",
            "teman",
            "colleague",
            "rekan kerja",
        ],
    ):
        return StructuredManualMemory(
            "relationships",
            "relationship_context",
            _clean_value(text),
        )

    preference_field = _detect_clear_preference_field(text)
    if preference_field:
        return StructuredManualMemory(
            "preferences",
            preference_field,
            _clean_value(text),
        )

    return None


def _detect_clear_preference_field(text: str) -> str | None:
    """Detect clear, stable preference statements.

    This intentionally avoids generic English "I like ..." so ordinary memories
    such as "I like quiet afternoons" remain category=other/manual_memory.
    """
    low = text.lower()

    communication_patterns = [
        "i prefer concise answers",
        "i prefer direct answers",
        "i prefer short answers",
        "please use a warm but direct tone",
        "warm but direct tone",
        "tone",
        "communication style",
        "gaya komunikasi",
        "jawaban yang langsung",
        "step by step",
    ]
    if _has_any(low, communication_patterns):
        return "communication_preference"

    clear_preference_patterns = [
        "i prefer",
        "my preference",
        "i would rather",
        "please use",
        "please don't",
        "lebih suka",
        "saya lebih suka",
        "aku lebih suka",
        "saya suka kalau",
        "aku suka kalau",
        "gue suka kalau",
        "gw suka kalau",
    ]
    if _has_any(low, clear_preference_patterns):
        return "general_preference"

    return None


def _detect_category(text: str) -> str | None:
    """Conservatively infer category.

    Generic English "I like ..." intentionally falls back to "other".
    """
    low = text.lower()

    if _has_any(low, ["birthday", "ulang tahun", "tanggal lahir", "anniversary", "hari jadi"]):
        return "important_dates"

    if _has_any(low, ["wife", "istri", "daughter", "anak", "family", "keluarga", "friend", "teman", "colleague", "rekan kerja"]):
        return "relationships"

    if _has_any(low, ["my goal", "goal saya", "target saya", "ingin mencapai", "mau mencapai"]):
        return "goals"

    if _has_any(low, ["daily routine", "rutinitas", "setiap pagi", "setiap malam", "tiap hari", "every morning", "every night"]):
        return "routines"

    if _has_any(low, ["cannot", "can't", "tidak bisa", "tidak boleh", "jangan", "never", "avoid", "don't", "do not"]):
        return "constraints"

    if _has_any(low, ["timezone", "time zone", "zona waktu", "location", "lokasi", "role", "pekerjaan"]):
        return "identity"

    clear_preference_patterns = [
        "i prefer",
        "my preference",
        "i would rather",
        "please use",
        "please don't",
        "tone",
        "style",
        "communication style",
        "lebih suka",
        "saya lebih suka",
        "aku lebih suka",
        "saya suka kalau",
        "aku suka kalau",
        "gue suka kalau",
        "gw suka kalau",
    ]
    if _has_any(low, clear_preference_patterns):
        return "preferences"

    return None


def _detect_timezone(text: str) -> str | None:
    patterns = [
        r"\b(?:timezone|time zone)\s*(?:is|=|:)?\s*([A-Za-z_]+/[A-Za-z_]+)",
        r"\b(?:zona waktu|timezone|time zone)\s*(?:saya|ku)?\s*(?:adalah|=|:)?\s*([A-Za-z_]+/[A-Za-z_]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_value(match.group(1), limit=80)

    low = text.lower()
    if "asia/jakarta" in low:
        return "Asia/Jakarta"
    if "gmt+7" in low or "utc+7" in low or "wib" in low:
        return "Asia/Jakarta"

    return None


def _detect_preferred_name(text: str) -> str | None:
    patterns = [
        r"\bcall me\s+([A-Za-z0-9 _.'-]{2,40})",
        r"\bpanggil aku\s+([A-Za-z0-9 _.'-]{2,40})",
        r"\bpanggil saya\s+([A-Za-z0-9 _.'-]{2,40})",
        r"\bmy nickname is\s+([A-Za-z0-9 _.'-]{2,40})",
        r"\bnama panggilan saya\s+([A-Za-z0-9 _.'-]{2,40})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_name_like_value(match.group(1))

    return None


def _detect_avoided_name(text: str) -> str | None:
    patterns = [
        r"\bdon't call me\s+([A-Za-z0-9 _.'-]{2,40})",
        r"\bdo not call me\s+([A-Za-z0-9 _.'-]{2,40})",
        r"\bjangan panggil aku\s+([A-Za-z0-9 _.'-]{2,40})",
        r"\bjangan panggil saya\s+([A-Za-z0-9 _.'-]{2,40})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_name_like_value(match.group(1))

    return None


def _detect_birthday(text: str) -> str | None:
    patterns = [
        r"\b(?:my birthday is|birthday is)\s+(.{2,60})",
        r"\b(?:ulang tahunku|ulang tahun saya|tanggal lahir saya|saya lahir tanggal)\s+(.{2,60})",
        r"\b(?:lahir tanggal)\s+(.{2,60})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_value(match.group(1).strip(" ."), limit=80)

    return None


def _detect_assistant_name(text: str) -> str | None:
    low = text.lower()
    if "assistant" not in low and "asisten" not in low:
        return None

    patterns = [
        r"\b(?:assistant|asisten)\s+(?:name|nama)\s*(?:is|adalah|=|:)?\s*([A-Za-z0-9 _.'-]{2,40})",
        r"\bnama\s+(?:assistant|asisten)\s*(?:is|adalah|=|:)?\s*([A-Za-z0-9 _.'-]{2,40})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_name_like_value(match.group(1))

    if "aliyya" in low:
        return "Aliyya"

    return None


def _clean_category(value: str | None) -> str:
    category = _compact(value or "").lower()
    return category if category in ALLOWED_CATEGORIES else DEFAULT_CATEGORY


def _clean_field(value: str | None) -> str | None:
    compact = _compact(value or "").lower()
    if not compact:
        return None

    compact = re.sub(r"[^a-z0-9]+", "_", compact).strip("_")
    if not compact:
        return None

    return compact[:80]


def _clean_value_or_none(value: str | None) -> str | None:
    compact = _compact(value or "")
    if not compact:
        return None
    return _clean_value(compact)


def _clean_value(value: str | None, *, limit: int = MAX_VALUE_CHARS) -> str:
    compact = _compact(value or "")
    if not compact:
        return "unknown"

    if len(compact) <= limit:
        return compact

    return compact[: limit - 1].rstrip() + "…"


def _clean_name_like_value(value: str) -> str:
    cleaned = _clean_value(value, limit=60)
    cleaned = re.split(
        r"\b(?:please|thanks|thank you|ya|dong|hehe|haha|instead|lagi)\b",
        cleaned,
        flags=re.IGNORECASE,
    )[0]
    return cleaned.strip(" .,;:") or "unknown"


def _compact(value: str) -> str:
    return " ".join(str(value or "").split())


def _has_any(text: str, terms: list[str]) -> bool:
    """Return true when any term is present.

    Short technical terms like "ui" or "ux" must match as whole words only.
    Without this, "quiet" accidentally matches "ui".
    """
    for term in terms:
        normalized = term.lower().strip()
        if not normalized:
            continue

        if len(normalized) <= 3 and normalized.isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text):
                return True
            continue

        if normalized in text:
            return True

    return False



_original_detect_assistant_name_explicit_phrase_guard = _detect_assistant_name


def _detect_assistant_name(text: str) -> str | None:
    from app.services import name_normalization

    strict_name = name_normalization._extract_strict_assistant_name_from_text(text)
    if strict_name:
        return strict_name

    detected = _original_detect_assistant_name_explicit_phrase_guard(text)
    if detected and name_normalization.message_explicitly_renames_assistant(text):
        return name_normalization.normalize_assistant_name(detected)

    return None
