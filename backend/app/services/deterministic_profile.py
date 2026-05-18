"""Deterministic profile rendering for the system prompt.

The LLM is bad at arithmetic that depends on the current date — especially
calculating someone's age. This service does it in Python and feeds the
result to the prompt as a fact.

Inputs:
  - user_identity row (from life_model.get_identity)
  - ui_context dict from the chat request (carries local_time_iso, timezone)

Output: a small markdown block injected into the system prompt's volatile
context, like:

    Deterministic user profile context:
    - User canonical birthday (ISO): 1995-01-07
    - User current age: 31 (computed from browser local date 2026-05-18)
    - Use computed age as source of truth. Do not recalculate.
    - When mentioning the birthday to the user, render as "7 Januari 1995"
      if replying in Indonesian, "January 7, 1995" if in English.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any


# Indonesian month names → number
_MONTHS_ID = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "agu": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12,
}

# English month names → number
_MONTHS_EN = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_MONTH_NAMES_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
_MONTH_NAMES_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    return {}


def parse_client_local_date(client_context: Any) -> date | None:
    """Extract YYYY-MM-DD from ui_context.

    Tries these keys in order:
      - local_date (explicit date string)
      - local_time_iso (full ISO datetime from frontend — common case)
      - local_time (alt name some clients use)

    Returns None if no parseable value.
    """
    ctx = _as_dict(client_context)
    raw = ctx.get("local_date") or ctx.get("local_time_iso") or ctx.get("local_time")
    if not isinstance(raw, str) or len(raw) < 10:
        return None

    # Try direct ISO date parse (YYYY-MM-DD or full ISO datetime).
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        pass

    # Last resort: regex for any YYYY-MM-DD.
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def parse_birthdate(value: Any) -> date | None:
    """Parse a birthday value in many formats. Returns None if year missing.

    Supports:
      - ISO: '1995-01-07'
      - '7 Januari 1995' / '7 January 1995'
      - 'January 7, 1995' / 'January 7th 1995'
      - '7-1-1995' / '07/01/1995' (assumes DMY for ambiguous cases)
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    # ISO first
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        pass

    lower = raw.lower().replace(",", " ")

    # "7 Januari 1995" / "7 January 1995"
    match = re.search(r"\b(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})\b", lower)
    if match:
        day = int(match.group(1))
        month = _MONTHS_ID.get(match.group(2)) or _MONTHS_EN.get(match.group(2))
        year = int(match.group(3))
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # "January 7 1995" / "January 7th, 1995"
    match = re.search(r"\b([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})\b", lower)
    if match:
        month = _MONTHS_EN.get(match.group(1)) or _MONTHS_ID.get(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # "07-01-1995" / "7/1/1995" — assume DMY (Indonesian convention)
    match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", lower)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            pass

    return None


def calculate_age(birthdate: date, on_date: date) -> int:
    age = on_date.year - birthdate.year
    if (on_date.month, on_date.day) < (birthdate.month, birthdate.day):
        age -= 1
    return age


def format_birthday(birthday: date) -> dict[str, str]:
    """Return localized human-readable strings for the prompt to use."""
    return {
        "id": f"{birthday.day} {_MONTH_NAMES_ID[birthday.month - 1]} {birthday.year}",
        "en": f"{_MONTH_NAMES_EN[birthday.month - 1]} {birthday.day}, {birthday.year}",
        "iso": birthday.isoformat(),
    }


def render_profile_runtime_context(identity_row: Any, client_context: Any) -> str:
    """Build the prompt block. Returns '' if no birthday signal.

    The block tells Claude:
      - the ISO canonical value (for internal reasoning)
      - the human-readable forms in Indonesian + English (for output)
      - the deterministic computed age (no LLM math)
      - hard rule: don't recalculate age
    """
    identity = _as_dict(identity_row)
    profile = _as_dict(identity.get("profile"))

    birthday_raw = (
        profile.get("birthday")
        or profile.get("birthdate")
        or profile.get("date_of_birth")
        or profile.get("dob")
    )
    if not birthday_raw:
        return ""

    birthday = parse_birthdate(birthday_raw)
    local_date = parse_client_local_date(client_context)

    lines: list[str] = []

    if birthday and local_date:
        age = calculate_age(birthday, local_date)
        fmt = format_birthday(birthday)
        lines.extend([
            f"User canonical birthday (ISO): {fmt['iso']}",
            f"User current age: {age} (computed from browser local date {local_date.isoformat()})",
            f"When mentioning the birthday in Indonesian, say: \"{fmt['id']}\"",
            f"When mentioning the birthday in English, say: \"{fmt['en']}\"",
            "Use this computed age as source of truth. Do NOT recalculate or infer the user's age yourself.",
        ])
    elif birthday and not local_date:
        fmt = format_birthday(birthday)
        lines.extend([
            f"User canonical birthday (ISO): {fmt['iso']}",
            f"When mentioning in Indonesian: \"{fmt['id']}\"; in English: \"{fmt['en']}\".",
            "Browser local date is missing — do not state the user's current age.",
        ])
    else:
        # Couldn't parse — fall back to the raw value so prompt isn't empty.
        lines.append(f"User birthday (raw, unparsed): {birthday_raw}")
        lines.append("Year or format unparsable — do not state the user's age.")

    return "## Deterministic user profile\n" + "\n".join(f"- {line}" for line in lines)
