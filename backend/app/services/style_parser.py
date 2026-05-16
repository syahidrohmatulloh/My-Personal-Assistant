"""Chat transcript parsers.

Sniff the format from the first ~20 non-empty lines, then dispatch to the
appropriate parser. Output is a list of (sender, text) tuples — timestamps
discarded since the extractor only cares about who said what.

Designed to be conservative: if parsing produces zero or near-zero turns, the
caller falls back to treating the whole input as one "plain" blob, which the
extractor can still analyze with lower confidence.

Supported formats:
  - WhatsApp export (iOS or Android, English or Indonesian locale headers)
  - Telegram export (text format, not JSON — the JSON export is harder and
    rarely used by end users who copy-paste)
  - Plain text — falls through to "single blob with no sender split"
"""

from __future__ import annotations

import logging
import re
from typing import Literal

log = logging.getLogger(__name__)


SourceType = Literal["whatsapp", "telegram", "plain", "pasted"]
ParsedLine = tuple[str, str]  # (sender, text)


# ---------------------------------------------------------------------------
# WhatsApp
#
# Examples of leading line formats we want to handle:
#   [9/5/24, 10:23:14 PM] John Doe: Hi there
#   [09/05/2024, 22:23] John Doe: Hi
#   9/5/24, 10:23 PM - John Doe: Hi
#   05/09/24, 22.23 - John Doe: Hi
#
# We use a permissive regex that handles dash vs bracket, comma + period,
# 12h/24h, AM/PM. Continuation lines (no leading date) belong to the prior
# message.
# ---------------------------------------------------------------------------

_WHATSAPP_LINE = re.compile(
    r"""
    ^
    \[?                              # optional opening bracket
    \s*\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}   # date
    [,\s]+                           # comma or space separator
    \d{1,2}[:\.]\d{2}(?:[:\.]\d{2})? # time hh:mm or hh:mm:ss
    (?:\s?[APap][Mm])?               # optional AM/PM
    \s*\]?                           # optional closing bracket
    \s*[-\u2013]?\s*                 # optional dash separator
    (?P<sender>[^:]{1,80})           # sender name (anything up to colon, capped)
    :\s                              # colon + space
    (?P<text>.*)                     # rest of line
    $
    """,
    re.VERBOSE,
)


def _is_whatsapp(sample: list[str]) -> bool:
    matched = sum(1 for line in sample if _WHATSAPP_LINE.match(line))
    return matched >= 3


def _parse_whatsapp(text: str) -> list[ParsedLine]:
    out: list[ParsedLine] = []
    current_sender: str | None = None
    current_buffer: list[str] = []

    def flush() -> None:
        if current_sender is not None and current_buffer:
            content = " ".join(current_buffer).strip()
            if content:
                out.append((current_sender, content))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _WHATSAPP_LINE.match(line)
        if m:
            # New message — flush prior.
            flush()
            current_sender = m.group("sender").strip()
            current_buffer = [m.group("text")]
        else:
            # Continuation of previous message.
            if current_sender is not None:
                current_buffer.append(line)
    flush()
    return _filter_system_lines(out)


# ---------------------------------------------------------------------------
# Telegram text export
#
# Telegram's "Save as Text" export looks roughly like:
#
#   John Doe, [Sep 5, 2024 at 10:23:14 PM]
#   Hi there
#   How are you
#
#   Jane Doe, [Sep 5, 2024 at 10:24:00 PM]
#   Doing well
#
# i.e. header line with sender + bracketed date, then 1+ message lines, then
# a blank line, then the next header.
# ---------------------------------------------------------------------------

_TELEGRAM_HEADER = re.compile(
    r"^(?P<sender>.{1,80}?),\s*\[(?P<date>[^\]]+)\]\s*$"
)


def _is_telegram(sample: list[str]) -> bool:
    matched = sum(1 for line in sample if _TELEGRAM_HEADER.match(line))
    return matched >= 2


def _parse_telegram(text: str) -> list[ParsedLine]:
    out: list[ParsedLine] = []
    current_sender: str | None = None
    current_buffer: list[str] = []

    def flush() -> None:
        if current_sender is not None and current_buffer:
            content = " ".join(current_buffer).strip()
            if content:
                out.append((current_sender, content))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        m = _TELEGRAM_HEADER.match(line)
        if m:
            flush()
            current_sender = m.group("sender").strip()
            current_buffer = []
        elif line and current_sender is not None:
            current_buffer.append(line)
        # blank lines just end the current paragraph; flush only on header
    flush()
    return _filter_system_lines(out)


# ---------------------------------------------------------------------------
# System line filter — strips noise the parsers shouldn't return
# ---------------------------------------------------------------------------

_SYSTEM_KEYWORDS = (
    "messages and calls are end-to-end encrypted",
    "<media omitted>",
    "<attached:",
    "image omitted",
    "video omitted",
    "audio omitted",
    "sticker omitted",
    "this message was deleted",
    "deleted this message",
    "missed voice call",
    "missed video call",
)


def _filter_system_lines(parsed: list[ParsedLine]) -> list[ParsedLine]:
    out: list[ParsedLine] = []
    for sender, text in parsed:
        lo = text.lower().strip()
        if any(kw in lo for kw in _SYSTEM_KEYWORDS):
            continue
        if not lo:
            continue
        out.append((sender, text))
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_transcript(text: str) -> tuple[SourceType, list[ParsedLine]]:
    """Detect format and parse. Returns (source_type, parsed_lines).

    If parsing yields fewer than 4 distinct messages, returns ('plain', [])
    so the caller treats the input as an unstructured blob.
    """
    if not text or not text.strip():
        return "pasted", []

    sample = [
        ln.strip()
        for ln in text.splitlines()[:50]
        if ln.strip()
    ]

    if _is_whatsapp(sample):
        parsed = _parse_whatsapp(text)
        if len(parsed) >= 4:
            return "whatsapp", parsed

    if _is_telegram(sample):
        parsed = _parse_telegram(text)
        if len(parsed) >= 4:
            return "telegram", parsed

    return "plain", []
