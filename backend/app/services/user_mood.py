"""User mood inference (Layer A) — read-only, additive.

Separate from companion mood. This service infers the USER's emotional state
from existing data sources; it never writes to or alters companion_settings,
companion_mood_state, or any other table.

Sources (priority order):
  1. `emotional_state` self-reports (highest signal — explicit user input)
  2. Optional: rule-based detection on the current chat message (fast, additive)
  3. `emotional_state` inferred entries (low confidence)

Output: a `UserMoodContext` dict for the prompt builder. Includes:
  - `latest` — most recent self-report (mood/energy/stress + note + tags)
  - `baseline` — rolling 30-day average per axis
  - `delta`   — `latest` vs `baseline` deltas with directional labels
  - `causal`  — extracted causes/tags from recent notes
  - `evidence` — short snippets backing the assessment
  - `confidence` — 0-1 score
  - `current_message_signal` — rule-based detection on this chat turn (or None)

Design rules:
  - Never inject content from `companion_mood_state` or `companion_settings`.
  - Render output is the prompt builder's job (this service returns data).
  - Compute baselines via SQL aggregate; no cache table.
  - Inference from chat is rule-based and free. No Haiku per-message.
"""

from __future__ import annotations

import logging
import re
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# How many days back to compute the baseline. Long enough to smooth noise,
# short enough to reflect current life phase.
BASELINE_DAYS = 30

# How many days back to consider "recent" for the latest snapshot.
RECENT_DAYS = 7

# Minimum self-report entries needed before we trust the baseline.
# Below this, we just don't render baseline (avoid misleading deltas).
MIN_BASELINE_ENTRIES = 3

# Minimum self-report entries needed before we render anything at all.
MIN_LATEST_ENTRIES = 1

# Delta threshold (in axis units, -5 to +5 scale) to label as meaningfully
# different from baseline. Below this, treat as "near baseline".
DELTA_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class _Snapshot(TypedDict, total=False):
    mood: float | None
    energy: float | None
    stress: float | None
    note: str | None
    tags: list[str]
    observed_at: str | None


class _Delta(TypedDict, total=False):
    mood: float | None
    energy: float | None
    stress: float | None
    label_mood: str  # e.g. "lower than usual" | "near baseline" | "higher than usual"
    label_energy: str
    label_stress: str


class _CurrentMessageSignal(TypedDict, total=False):
    mood_hint: str | None  # "tired" | "stressed" | "happy" | etc.
    confidence: float
    matched_keywords: list[str]


class UserMoodContext(TypedDict, total=False):
    has_data: bool
    latest: _Snapshot
    baseline: _Snapshot
    delta: _Delta
    causal: list[str]
    evidence: list[str]
    confidence: float
    current_message_signal: _CurrentMessageSignal | None
    sample_size: int  # how many self-reports went into baseline


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def infer_user_mood(
    user_id: str,
    *,
    current_message: str | None = None,
) -> UserMoodContext:
    """Build a user mood context for the prompt builder.

    Read-only. Pure Python on top of `emotional_state` rows.
    Returns `{"has_data": False}` when there's nothing useful to say.
    """
    rows = _fetch_recent_self_reports(user_id, days=BASELINE_DAYS)

    if len(rows) < MIN_LATEST_ENTRIES:
        # No journal/self-report data. Still attempt rule-based hint on
        # current chat message — but don't pretend we know baseline.
        message_signal = _detect_chat_message_mood(current_message)
        return {
            "has_data": bool(message_signal),
            "current_message_signal": message_signal,
        }

    latest = _build_latest(rows)
    baseline, sample_size = _build_baseline(rows)
    delta = _build_delta(latest, baseline) if baseline else {}
    causal = _extract_causal(rows[:5])  # last 5 entries
    evidence = _build_evidence(rows[:5])
    confidence = _compute_confidence(rows, sample_size)
    message_signal = _detect_chat_message_mood(current_message)

    return {
        "has_data": True,
        "latest": latest,
        "baseline": baseline or {},
        "delta": delta,
        "causal": causal,
        "evidence": evidence,
        "confidence": confidence,
        "current_message_signal": message_signal,
        "sample_size": sample_size,
    }


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def _fetch_recent_self_reports(user_id: str, *, days: int) -> list[dict]:
    """Read emotional_state self-reports within the window, ordered newest first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = safe_execute(
            lambda sb: sb.table("emotional_state")
            .select("mood, energy, stress, note, tags, observed_at, source, confidence")
            .eq("user_id", user_id)
            .eq("source", "self_report")
            .eq("superseded", False)
            .gte("observed_at", cutoff)
            .order("observed_at", desc=True)
            .limit(60)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        log.warning("user_mood: emotional_state fetch failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Latest snapshot
# ---------------------------------------------------------------------------


def _build_latest(rows: list[dict]) -> _Snapshot:
    """Latest snapshot = most recent self-report row, with axis-level fields
    coalesced from up to the 3 most recent entries.

    Reasoning: a single check-in might only fill in mood (not energy/stress).
    Coalescing across the 3 newest entries gives a fuller picture without
    averaging across stale data.
    """
    head = rows[0]
    snapshot: _Snapshot = {
        "note": head.get("note"),
        "tags": list(head.get("tags") or []),
        "observed_at": head.get("observed_at"),
    }

    for axis in ("mood", "energy", "stress"):
        # Walk newest to older, take first non-null.
        for row in rows[:3]:
            v = row.get(axis)
            if v is not None:
                snapshot[axis] = float(v)
                break
        else:
            snapshot[axis] = None

    return snapshot


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def _build_baseline(rows: list[dict]) -> tuple[_Snapshot | None, int]:
    """30-day rolling baseline.

    Returns (baseline, sample_size). baseline is None when we don't have enough
    data; sample_size is the count of self-reports in the window regardless.
    """
    if len(rows) < MIN_BASELINE_ENTRIES:
        return None, len(rows)

    baseline: _Snapshot = {}
    for axis in ("mood", "energy", "stress"):
        values = [float(r[axis]) for r in rows if r.get(axis) is not None]
        if len(values) >= MIN_BASELINE_ENTRIES:
            baseline[axis] = statistics.mean(values)
        else:
            baseline[axis] = None

    return baseline, len(rows)


# ---------------------------------------------------------------------------
# Delta vs baseline
# ---------------------------------------------------------------------------


def _label_delta(value: float | None) -> str:
    """Convert a numeric delta to a directional label."""
    if value is None:
        return "unknown"
    if value > DELTA_THRESHOLD:
        return "higher than usual"
    if value < -DELTA_THRESHOLD:
        return "lower than usual"
    return "near baseline"


def _build_delta(latest: _Snapshot, baseline: _Snapshot) -> _Delta:
    """Compute latest vs baseline delta per axis."""
    delta: _Delta = {}
    for axis in ("mood", "energy", "stress"):
        latest_v = latest.get(axis)
        baseline_v = baseline.get(axis)
        if latest_v is None or baseline_v is None:
            delta[axis] = None
            delta[f"label_{axis}"] = "unknown"  # type: ignore[literal-required]
        else:
            d = latest_v - baseline_v
            delta[axis] = round(d, 1)
            delta[f"label_{axis}"] = _label_delta(d)  # type: ignore[literal-required]
    return delta


# ---------------------------------------------------------------------------
# Causal context
# ---------------------------------------------------------------------------


# Common Indonesian + English cause patterns. Free, no LLM.
# We extract from notes a) explicit "because"/"karena" clauses, b) noun phrases
# after these connectors. Best-effort — we'd rather miss than hallucinate.
_CAUSE_PATTERNS = [
    re.compile(r"\b(?:karena|gara-gara|sebab|because of|because|due to)\s+([^,.;!?\n]+)", re.IGNORECASE),
    re.compile(r"\b(?:abis|after|setelah|habis)\s+([^,.;!?\n]+)", re.IGNORECASE),
]


def _extract_causal(rows: list[dict]) -> list[str]:
    """Extract causal phrases from notes.

    Returns up to 5 short snippets. Best-effort regex — designed to err toward
    silence rather than hallucinating causes.
    """
    causes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        note = (row.get("note") or "").strip()
        if not note:
            continue
        for pattern in _CAUSE_PATTERNS:
            for match in pattern.finditer(note):
                cause = match.group(1).strip().rstrip(".,;:!?")
                # Trim aggressive: only first 60 chars, drop trailing partial words
                if len(cause) > 60:
                    cause = cause[:60].rsplit(" ", 1)[0] + "…"
                key = cause.lower()
                if key and key not in seen and len(cause) >= 3:
                    seen.add(key)
                    causes.append(cause)
        # Also surface tags as soft causal signal.
        for tag in (row.get("tags") or [])[:3]:
            t = str(tag).strip()
            tk = t.lower()
            if tk and tk not in seen and len(t) >= 3:
                seen.add(tk)
                causes.append(f"#{t}")

        if len(causes) >= 5:
            break

    return causes[:5]


# ---------------------------------------------------------------------------
# Evidence snippets
# ---------------------------------------------------------------------------


def _build_evidence(rows: list[dict]) -> list[str]:
    """Pull recent dated notes as evidence. Max 3, each capped at 140 chars."""
    out: list[str] = []
    for row in rows:
        note = (row.get("note") or "").strip()
        if not note:
            continue
        observed = (row.get("observed_at") or "")[:10]
        snippet = note if len(note) <= 140 else note[:137] + "…"
        out.append(f"{observed}: {snippet}")
        if len(out) >= 3:
            break
    return out


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def _compute_confidence(rows: list[dict], sample_size: int) -> float:
    """Confidence based on:
      - Number of self-reports (more = better)
      - Average confidence column in DB
      - Recency of most recent entry (stale = lower)

    Clamps to [0, 1]. Conservative — designed to read as "rough signal", not
    "diagnostic certainty".
    """
    if not rows:
        return 0.0

    # Sample-size component (saturates at 10 entries)
    size_score = min(sample_size / 10.0, 1.0)

    # DB-stored confidence component
    confs = [float(r["confidence"]) for r in rows if r.get("confidence") is not None]
    db_score = statistics.mean(confs) if confs else 0.6  # neutral default

    # Recency component — full credit if latest <= 24h, decay over 7 days
    try:
        latest_at = datetime.fromisoformat(
            (rows[0].get("observed_at") or "").replace("Z", "+00:00")
        )
        age_hours = (datetime.now(timezone.utc) - latest_at).total_seconds() / 3600.0
        if age_hours <= 24:
            recency_score = 1.0
        elif age_hours >= 24 * 7:
            recency_score = 0.2
        else:
            recency_score = 1.0 - ((age_hours - 24) / (24 * 6)) * 0.8
    except Exception:
        recency_score = 0.5

    # Weighted average — recency matters most for live tone-shaping.
    score = (recency_score * 0.5) + (size_score * 0.3) + (db_score * 0.2)
    return round(max(0.0, min(1.0, score)), 2)


# ---------------------------------------------------------------------------
# Rule-based current-message mood detection
# ---------------------------------------------------------------------------

# Keyword → mood hint mapping. Indonesian + English. Free, fast, deterministic.
# Designed to fire on clear signal only — better to return None than misread.
_MESSAGE_MOOD_KEYWORDS: dict[str, list[str]] = {
    "tired": [
        "capek banget", "capek sekali", "lelah banget", "udah capek",
        "exhausted", "drained", "burned out", "burnt out", "wiped out",
    ],
    "stressed": [
        "stress banget", "lagi stress", "stres berat", "overwhelmed",
        "kewalahan", "pusing banget", "panik",
    ],
    "sad": [
        "lagi sedih", "sedih banget", "lagi down", "feeling down",
        "feeling sad", "patah hati", "kecewa banget",
    ],
    "anxious": [
        "lagi anxious", "cemas banget", "khawatir banget", "deg-degan",
        "anxious about", "worried about", "gelisah",
    ],
    "angry": [
        "kesel banget", "marah banget", "frustrasi", "frustrated",
        "annoyed af", "pissed off",
    ],
    "happy": [
        "lagi senang", "happy banget", "seneng banget", "bahagia banget",
        "feeling great", "excited",
    ],
    "lonely": [
        "lagi sendiri", "kesepian", "merasa sendiri", "feel alone",
        "feeling lonely",
    ],
}


def _detect_chat_message_mood(message: str | None) -> _CurrentMessageSignal | None:
    """Lightweight keyword detection on the user's current message.

    Returns None on no match. Multiple hits → highest-priority mood wins
    (tired > stressed > sad > anxious > angry > lonely > happy — order matters).
    """
    if not message or len(message) < 3:
        return None

    lower = message.lower()
    matches: list[tuple[str, str]] = []  # (mood, keyword)
    for mood, keywords in _MESSAGE_MOOD_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                matches.append((mood, kw))

    if not matches:
        return None

    # Priority order (negative moods first — more actionable for tone shift)
    priority = ["tired", "stressed", "sad", "anxious", "angry", "lonely", "happy"]
    matches.sort(key=lambda m: priority.index(m[0]) if m[0] in priority else 99)

    top_mood = matches[0][0]
    matched_kw = [kw for m, kw in matches if m == top_mood]
    return {
        "mood_hint": top_mood,
        "confidence": 0.6,  # keyword-only — moderate confidence
        "matched_keywords": matched_kw[:3],
    }
