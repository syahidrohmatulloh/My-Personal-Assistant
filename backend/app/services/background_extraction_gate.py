"""Background extraction gate.

Purpose:
- Avoid running every background extractor on every chat turn.
- Reduce duplicate memories and unnecessary LLM calls.
- Keep deterministic/cheap extractors available when their signal is present.

This gate only decides WHETHER to run an extractor. The extractors themselves
still decide WHAT, if anything, should be saved.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ExtractionDecision:
    run_legacy_memory: bool
    run_memory_intelligence: bool
    run_mood_memory_feedback: bool
    run_relationship_memory: bool
    run_goal_intelligence: bool
    run_calendar_candidate_extraction: bool
    reasons: list[str]


_MEMORY_SIGNALS = (
    "remember",
    "ingat",
    "catat",
    "save this",
    "simpan",
    "note that",
    "from now on",
    "mulai sekarang",
    "going forward",
    "panggil aku",
    "call me",
    "nama saya",
    "my name is",
    "aku tinggal",
    "i live",
    "timezone",
    "gmt",
    "ulang tahun",
    "birthday",
    "jangan panggil",
    "don't call me",
    # Durable preference / constraint signals. These are intentionally routed
    # through memory_intelligence only; the extractor still decides whether
    # anything is specific and durable enough to save.
    "prefer",
    "preference",
    "i prefer",
    "i like",
    "i don't like",
    "dont like",
    "lebih suka",
    "saya suka",
    "aku suka",
    "tidak suka",
    "ga suka",
    "gak suka",
    "kurang suka",
    "jangan ",
    "do not ",
    "don't ",
    "dont ",
    "avoid",
    "hindari",
    "usahakan",
    "biasakan",
    "selalu",
    "always",
    "never",
    "ke depan",
    "for future",
    "next time",
    "copy-paste",
    "consulting style",
    "gaya consulting",
    "jangan hardcode",
)

_CALENDAR_SIGNALS = (
    "meeting",
    "meet",
    "call",
    "zoom",
    "gmeet",
    "google meet",
    "presentasi",
    "presentation",
    "rapat",
    "ketemu",
    "diskusi",
    "deadline",
    "appointment",
    "janji",
    "agenda",
    "besok",
    "tomorrow",
    "lusa",
    "hari ini",
    "today",
    "jam ",
    "pukul ",
)

_GOAL_SIGNALS = (
    "goal",
    "goals",
    "target",
    "tujuan",
    "mau lebih",
    "pengen lebih",
    "ingin lebih",
    "konsisten",
    "habit",
    "kebiasaan",
    "progress",
    "milestone",
    "tahun ini",
    "bulan ini",
    "quarter",
    "rencana jangka",
    "aku mau mencapai",
    "ingin mencapai",
    "pengen mencapai",
)

_MOOD_FEEDBACK_SIGNALS = (
    "capek",
    "pusing",
    "frustrated",
    "frustrasi",
    "bingung",
    "kesel",
    "stuck",
    "ribet",
    "error",
    "failed",
    "traceback",
    "deploy",
    "build",
    "patch",
    "terminal",
)

_RELATIONSHIP_SIGNALS = (
    "aliyya",
    "personal assistant",
    "companion",
    "jangan generic",
    "bukan generic",
    "lebih teliti",
    "jangan nebak",
    "jangan asal",
    "patch final",
    "lebih hati-hati",
    "ui",
    "ux",
    "vibes",
    "theme",
    "mobile",
    "sidebar",
)


def _norm(text: str | None) -> str:
    value = (text or "").lower()
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _looks_like_direct_identity_answer(user_message: str, recent_messages: list[dict]) -> bool:
    """Detect short answers to assistant questions like birthday/name/timezone."""
    text = _norm(user_message)
    if len(text) > 80:
        return False

    previous_assistant = ""
    for message in reversed(recent_messages or []):
        if message.get("role") == "assistant":
            previous_assistant = _norm(str(message.get("content") or ""))
            break

    if not previous_assistant:
        return False

    question_signal = any(
        cue in previous_assistant
        for cue in (
            "nama",
            "name",
            "birthday",
            "ulang tahun",
            "ultah",
            "timezone",
            "zona waktu",
            "panggil",
            "call you",
        )
    )
    return question_signal and bool(text)


def _looks_like_self_regulation_memory_preference(text: str | None) -> bool:
    raw = " ".join(str(text or "").lower().split())
    if not raw:
        return False

    emotion_terms = (
        "marah",
        "emosi",
        "kesal",
        "sedih",
        "panik",
        "cemas",
        "anxious",
        "angry",
        "upset",
        "stress",
        "stressed",
        "overwhelmed",
        "capek",
    )
    if not any(term in raw for term in emotion_terms):
        return False

    future_or_reminder_terms = (
        "ke depan",
        "kedepan",
        "mulai sekarang",
        "going forward",
        "from now on",
        "kalau aku",
        "kalo aku",
        "if i",
        "when i",
        "ingetin aku",
        "ingatkan aku",
        "remind me",
        "kamu ingetin",
    )
    if not any(term in raw for term in future_or_reminder_terms):
        return False

    concrete_calendar_terms = (
        "hari ini",
        "besok",
        "lusa",
        "nanti malam",
        "tanggal ",
        "jam ",
        "pukul ",
        "today",
        "tomorrow",
        "tonight",
    )
    has_digit_time = any(ch.isdigit() for ch in raw) and any(
        marker in raw for marker in ("jam", "pukul", ":", ".", "am", "pm")
    )

    return not (has_digit_time or any(term in raw for term in concrete_calendar_terms))


def decide(
    *,
    user_message: str,
    assistant_response: str | None = None,
    recent_messages: list[dict] | None = None,
    is_first_message: bool = False,
) -> ExtractionDecision:
    text = _norm(user_message)
    combined = _norm(f"{user_message}\n{assistant_response or ''}")
    reasons: list[str] = []

    has_memory_signal = _contains_any(text, _MEMORY_SIGNALS) or _looks_like_direct_identity_answer(
        user_message,
        recent_messages or [],
    )
    has_goal_signal = _contains_any(text, _GOAL_SIGNALS)
    has_calendar_signal = _contains_any(text, _CALENDAR_SIGNALS)
    has_mood_feedback_signal = _contains_any(combined, _MOOD_FEEDBACK_SIGNALS)
    has_relationship_signal = _contains_any(combined, _RELATIONSHIP_SIGNALS)

    if has_memory_signal:
        reasons.append("memory_signal")
    if has_goal_signal:
        reasons.append("goal_signal")
    if has_calendar_signal:
        reasons.append("calendar_signal")
    if has_mood_feedback_signal:
        reasons.append("mood_feedback_signal")
    if has_relationship_signal:
        reasons.append("relationship_signal")
    if is_first_message:
        reasons.append("first_message")

    # Legacy memory overlaps with memory_intelligence and is the most expensive
    # because it also embeds and dedup-checks rows. Keep it off by default.
    run_legacy_memory = False

    # Structured memory intelligence handles identity, preferences, routines,
    # dates, constraints, and corrections. Run only when there is a strong signal.
    run_memory_intelligence = has_memory_signal

    # Deterministic lightweight extractors. Still gated to avoid repeated writes.
    run_mood_memory_feedback = has_mood_feedback_signal
    run_relationship_memory = has_relationship_signal

    # Goal intelligence is an LLM call. Run only on goal-like turns.
    run_goal_intelligence = has_goal_signal
    run_calendar_candidate_extraction = has_calendar_signal and not _looks_like_self_regulation_memory_preference(text)

    return ExtractionDecision(
        run_legacy_memory=run_legacy_memory,
        run_memory_intelligence=run_memory_intelligence,
        run_mood_memory_feedback=run_mood_memory_feedback,
        run_relationship_memory=run_relationship_memory,
        run_goal_intelligence=run_goal_intelligence,
        run_calendar_candidate_extraction=run_calendar_candidate_extraction,
        reasons=reasons,
    )
