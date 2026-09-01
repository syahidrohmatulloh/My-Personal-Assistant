from __future__ import annotations

import asyncio
import logging
import re

from app.services import calendar_candidate_extractor
from app.services.supabase_client import safe_execute


log = logging.getLogger(__name__)


def should_hard_gate_calendar_candidate(user_message: str | None) -> bool:
    if calendar_candidate_extractor.looks_like_self_regulation_memory_preference(user_message):
        return False
    """Hard gate Calendar-like turns before Claude can answer freely."""
    raw = str(user_message or "").strip()
    if not raw:
        return False

    lower = raw.casefold()
    compact = " ".join(lower.split())

    if calendar_candidate_extractor.is_calendar_absence_statement(raw):
        return False

    if compact in {
        "iya",
        "ya",
        "yes",
        "y",
        "oke",
        "ok",
        "sip",
        "siap",
        "batal",
        "gajadi",
        "ga jadi",
        "nggak jadi",
        "tidak jadi",
    }:
        return False

    if calendar_candidate_extractor.should_attempt_calendar_candidate_extraction(raw):
        return True

    date_terms = (
        "tgl",
        "tanggal",
        "besok",
        "lusa",
        "hari ini",
        "malam ini",
        "pagi ini",
        "siang ini",
        "sore ini",
        "senin",
        "selasa",
        "rabu",
        "kamis",
        "jumat",
        "jum'at",
        "sabtu",
        "minggu",
        "januari",
        "februari",
        "maret",
        "april",
        "mei",
        "juni",
        "juli",
        "agustus",
        "september",
        "oktober",
        "november",
        "desember",
    )
    activity_terms = (
        "aku mau",
        "saya mau",
        "ada",
        "acara",
        "agenda",
        "jadwal",
        "meeting",
        "rapat",
        "ketemu",
        "appointment",
        "janji",
        "dokter",
        "klinik",
        "fisioterapi",
        "terapi",
        "gym",
        "golf",
        "dinner",
        "lunch",
        "makan",
        "nonton",
        "bioskop",
        "flight",
        "terbang",
        "event",
        "launching",
    )

    has_date = any(term in compact for term in date_terms)
    has_time = bool(
        re.search(r"\bjam\s*\d{1,2}(?:[.:]\d{2})?\b", compact)
        or re.search(r"\b\d{1,2}[.:]\d{2}\b", compact)
        or re.search(r"\b\d{1,2}\s*(?:pagi|siang|sore|malam)\b", compact)
    )
    has_activity = any(term in compact for term in activity_terms)

    return bool(has_activity and (has_date or has_time))

def render_calendar_hard_gate_clarification(
    *,
    address_term: str | None = None,
) -> str:
    term = clean_calendar_address_term(address_term)
    prefix = f"{term}, " if term else ""

    return (
        f"{prefix}ini kayaknya agenda, tapi aku belum cukup yakin detailnya.\n\n"
        "Bisa sebutkan acara, tanggal, waktu, dan lokasi?"
    )

async def load_calendar_address_term(
    *,
    user_id: str,
    assistant_mode: str = "life_companion",
) -> str:
    """Load a user-preferred address term for deterministic receipts.

    No fallback nickname is hardcoded. If the user has not explicitly stored a
    preferred address/name/nickname, deterministic receipts simply omit it.
    """
    if assistant_mode == "chief_of_staff":
        return ""

    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .select("structured_field, structured_value, content, updated_at")
                .eq("user_id", user_id)
                .eq("archived", False)
                .eq("superseded", False)
                .in_(
                    "structured_field",
                    ["preferred_address", "preferred_name", "nickname"],
                )
                .order("updated_at", desc=True)
                .limit(8)
                .execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "chat: calendar address term lookup failed user=%s error_type=%s",
            user_id[:8],
            type(exc).__name__,
        )
        return ""

    for row in list(result.data or []):
        value = clean_calendar_address_term(row.get("structured_value"))
        if value:
            return value

    return ""

def clean_calendar_address_term(value) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split()).strip()
    text = text.strip(" .,:;!?'\"")
    if not text:
        return ""

    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in (
            "jangan panggil",
            "do not call",
            "don't call",
            "disallowed",
        )
    ):
        return ""

    if len(text) > 40:
        return ""

    return text
