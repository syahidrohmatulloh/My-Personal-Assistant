"""Conservative memory-retrieval intent gate.

This gate answers one narrow question:

    Should a user query retrieve personal memory at all?

It does not rank memory and does not change similarity scoring. It only blocks
obvious public/current/general-information queries that should be answered from
tools/web/model knowledge rather than personal memory.

Personal cues intentionally override public-current patterns so queries like
"ingatkan aku soal kurs yang pernah aku tanya" can still retrieve memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class MemoryRetrievalGateDecision:
    should_retrieve: bool
    reason: str
    matched: str = ""


_PERSONAL_CUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...    (
        "self_regulation",
        re.compile(
            r"("
            r"overthinking|kepikiran|marah|cemas|anxious|insecure|"
            r"burnout|stress|stressed|galau|bad mood|overwhelmed|"
            r"spiral|panik|panic"
            r")",
            re.IGNORECASE,
        ),
    ),
] = (
    (
        "explicit_memory",
        re.compile(
            r"\b("
            r"ingat|ingetin|inget|remember|memory|memories|kenangan|"
            r"kamu inget|you remember|do you remember"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "personal_pronoun_or_relation",
        re.compile(
            r"\b("
            r"aku|saya|gue|gw|ku|my|me|"
            r"istri|suami|anak|keluarga|ayah|ibu|"
            r"aghnia|zahra|aneira"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "personal_profile",
        re.compile(
            r"\b("
            r"preferensi|preference|preferences|profil|profile|"
            r"suka|tidak suka|biasanya|kebiasaan|"
            r"jadwal|schedule|calendar|agenda|rencana|goal|target|"
            r"kalau aku|when i|about me"
            r")\b",
            re.IGNORECASE,
        ),
    ),
)


_PUBLIC_CURRENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "market_or_stock_price",
        re.compile(
            r"\b("
            r"harga saham|saham hari ini|stock price|market today|"
            r"ihsg|crypto|bitcoin|btc|eth"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "fx_or_exchange_rate",
        re.compile(
            r"\b("
            r"kurs|dollar|usd|idr|exchange rate|fx rate"
            r")\b.*\b("
            r"hari ini|sekarang|today|current|terbaru"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "weather",
        re.compile(
            r"\b("
            r"cuaca|weather|hujan|rain|forecast|suhu|temperature"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "current_affairs",
        re.compile(
            r"\b("
            r"presiden|president|menteri|prime minister|ceo|"
            r"berita|news|latest|terbaru|sekarang|hari ini|current"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "generic_latest_recommendation",
        re.compile(
            r"\b("
            r"rekomendasi|recommendation|recommend"
            r")\b.*\b("
            r"terbaru|latest|laptop|hp|phone|mobil|car|produk|product|gadget"
            r")\b",
            re.IGNORECASE,
        ),
    ),
)


_LOW_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("empty", re.compile(r"^\s*$", re.IGNORECASE)),
    (
        "greeting_or_ack",
        re.compile(
            r"^\s*(hi|halo|hello|hey|ok|oke|okay|thanks|thank you|terima kasih|sip)\s*[.!?]*\s*$",
            re.IGNORECASE,
        ),
    ),
)


def _normalize_query(query: str | None) -> str:
    return " ".join(str(query or "").strip().split())


def _first_match(
    query: str,
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> tuple[str, str] | None:
    for reason, pattern in patterns:
        match = pattern.search(query)
        if match:
            return reason, match.group(0)
    return None





def _strong_public_current_match(query: str) -> tuple[str, str] | None:
    folded = query.casefold()

    macro_terms = (
        "ekonomi global",
        "global economy",
        "makro global",
        "macro economy",
        "kondisi ekonomi",
        "economic outlook",
        "outlook ekonomi",
    )
    for term in macro_terms:
        if term in folded:
            return "macro_economy", term

    sports_terms = (
        "piala dunia",
        "world cup",
        "liga champions",
        "champions league",
        "premier league",
        "epl",
        "nba",
        "f1",
        "formula 1",
        "motogp",
        "olimpiade",
    )
    sports_signals = (
        "jadwal",
        "schedule",
        "terbaru",
        "latest",
        "hari ini",
        "sekarang",
        "current",
        "hasil",
        "score",
        "skor",
    )
    matched_sport = next((term for term in sports_terms if term in folded), None)
    if matched_sport and any(signal in folded for signal in sports_signals):
        return "sports_schedule_or_current_event", matched_sport

    return None

_SELF_REGULATION_RE = re.compile(
    r"(overthinking|kepikiran|marah|cemas|anxious|insecure|burnout|stress|stressed|galau|bad mood|overwhelmed|spiral|panik|panic)",
    re.IGNORECASE,
)

def should_retrieve_memory(query: str | None) -> MemoryRetrievalGateDecision:
    """Return whether personal memory retrieval should run for this query."""
    normalized = _normalize_query(query)

    low_signal = _first_match(normalized, _LOW_SIGNAL_PATTERNS)
    if low_signal:
        reason, matched = low_signal
        return MemoryRetrievalGateDecision(False, reason, matched)

    strong_public_current = _strong_public_current_match(normalized)
    if strong_public_current:
        reason, matched = strong_public_current
        return MemoryRetrievalGateDecision(False, f"public_current:{reason}", matched)

    personal = _first_match(normalized, _PERSONAL_CUE_PATTERNS)
    if personal:
        reason, matched = personal
        return MemoryRetrievalGateDecision(True, f"personal_cue:{reason}", matched)

    public_current = _first_match(normalized, _PUBLIC_CURRENT_PATTERNS)
    if public_current:
        reason, matched = public_current
        return MemoryRetrievalGateDecision(False, f"public_current:{reason}", matched)

    self_regulation_match = _SELF_REGULATION_RE.search(query or "")
    if self_regulation_match:
        return MemoryRetrievalGateDecision(
            should_retrieve=True,
            reason="personal_cue:self_regulation",
            matched=self_regulation_match.group(0),
        )

    return MemoryRetrievalGateDecision(True, "default_allow", "")
