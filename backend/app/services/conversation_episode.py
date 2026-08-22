"""Lightweight episode classification for cross-conversation summaries.

This is intentionally pure and deterministic. It does not replace embeddings;
it adds a small route-aware signal so packed summaries are less generic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


EPISODE_KINDS = {
    "self_regulation",
    "identity_family",
    "work_client",
    "dev_project",
    "travel",
    "health",
    "finance_market",
    "calendar_schedule",
    "general",
}

_EPISODE_TERMS: dict[str, tuple[str, ...]] = {
    "self_regulation": (
        "overthinking",
        "kepikiran",
        "istirahat",
        "rest",
        "marah",
        "cemas",
        "anxious",
        "insecure",
        "burnout",
        "stress",
        "bad mood",
        "overwhelmed",
        "gentle reminder",
        "soft nudge",
        "without pressure",
    ),
    "identity_family": (
        "anak",
        "daughter",
        "zahra",
        "aneira",
        "istri",
        "wife",
        "spouse",
        "aghnia",
        "ayah",
        "father",
        "keluarga",
        "family",
        "nama",
        "name",
        "birthday",
        "ulang tahun",
    ),
    "work_client": (
        "client",
        "nasabah",
        "bank mandiri",
        "corporate banking",
        "meeting",
        "email",
        "pak ",
        "bu ",
        "stonepeak",
        "erajaya",
        "map",
        "indonet",
        "grand lucky",
        "project",
        "nda",
    ),
    "dev_project": (
        "repo",
        "github",
        "frontend",
        "backend",
        "fastapi",
        "next.js",
        "supabase",
        "vercel",
        "fly.io",
        "deploy",
        "pytest",
        "memory retrieval",
        "personal assistant",
        "aliyya",
        "quant",
    ),
    "travel": (
        "flight",
        "hotel",
        "visa",
        "airport",
        "lhr",
        "coventry",
        "australia",
        "melbourne",
        "singapore",
        "usa",
        "umrah",
        "jeddah",
        "makkah",
        "trip",
        "travel",
    ),
    "health": (
        "sakit",
        "doctor",
        "dokter",
        "vitamin",
        "b12",
        "sariawan",
        "osteoarthritis",
        "therapy",
        "obat",
        "health",
    ),
    "finance_market": (
        "saham",
        "stock",
        "market",
        "ihsg",
        "kurs",
        "dollar",
        "usd",
        "crypto",
        "yield",
        "sofr",
        "valuation",
    ),
    "calendar_schedule": (
        "jadwal",
        "calendar",
        "agenda",
        "reminder",
        "ingatkan",
        "besok",
        "hari ini",
        "minggu depan",
        "schedule",
        "meeting jam",
    ),
}


@dataclass(frozen=True)
class EpisodeClassification:
    kind: str
    matched_terms: tuple[str, ...] = ()

    @property
    def is_specific(self) -> bool:
        return self.kind != "general"


def _as_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _fold(value: Any) -> str:
    return _as_text(value).casefold()


def classify_episode_text(text: str | None) -> EpisodeClassification:
    folded = _fold(text)
    if not folded:
        return EpisodeClassification(kind="general")

    best_kind = "general"
    best_terms: tuple[str, ...] = ()

    for kind, terms in _EPISODE_TERMS.items():
        matches = tuple(term for term in terms if term.casefold() in folded)
        if len(matches) > len(best_terms):
            best_kind = kind
            best_terms = matches

    return EpisodeClassification(kind=best_kind, matched_terms=best_terms)


def classify_summary_episode(row: dict[str, Any]) -> EpisodeClassification:
    text = " ".join(
        part
        for part in (
            _as_text(row.get("title")),
            _as_text(row.get("summary")),
            _as_text(row.get("topic")),
            _as_text(row.get("episode_kind")),
        )
        if part
    )
    return classify_episode_text(text)


def episode_match_bonus(*, query_text: str | None, summary_row: dict[str, Any]) -> float:
    query_episode = classify_episode_text(query_text)
    if not query_episode.is_specific:
        return 0.0

    summary_episode = classify_summary_episode(summary_row)
    if summary_episode.kind == query_episode.kind:
        return 0.45

    # Keep adjacent personal continuity modestly useful.
    if query_episode.kind == "identity_family" and summary_episode.kind == "self_regulation":
        return 0.10
    if query_episode.kind == "self_regulation" and summary_episode.kind == "identity_family":
        return 0.05

    return 0.0
