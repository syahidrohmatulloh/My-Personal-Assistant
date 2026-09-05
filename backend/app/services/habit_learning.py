"""M32 — deterministic habit and routine learning from repeated user evidence.

M32 learns only conservative recurring activity patterns. It does not:
- turn one event into a habit;
- replace explicit user-authored routine statements;
- create reminders, calendar events, or goals;
- use an LLM to decide whether a habit exists;
- infer sensitive habits;
- write to the identity/life-model profile;
- create a second per-turn CognitiveDecisionTrace after streaming.

Explicit routine assertions remain owned by memory_intelligence. M32 handles
cross-conversation repeated occurrences and explicit corrections of M32-owned
inferred habit memories.

Inferred M32 memories deliberately stay below the existing lifecycle
LOW_CONFIDENCE_THRESHOLD so M31F treats them as unverified until stronger
user-authored evidence exists.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.services.embeddings import embed_document
from app.services.supabase_client import safe_execute


log = logging.getLogger(__name__)

HABIT_LEARNING_VERSION = "M32-v1"

MIN_OCCURRENCES = 4
MIN_DISTINCT_DAYS = 3
MIN_SPAN_DAYS = 7
HISTORY_DAYS = 60
MAX_CONVERSATIONS = 30
MAX_HISTORY_MESSAGES = 320
MAX_EVIDENCE = 3
MAX_ACTIVITY_CHARS = 120
MAX_INFERRED_CONFIDENCE = 0.54

HabitSignal = Literal[
    "none",
    "explicit_routine",
    "occurrence",
    "explicit_correction",
]

HABIT_REASON_CODES = frozenset(
    {
        "habit.gate.no_signal",
        "habit.gate.explicit_routine_delegated",
        "habit.gate.occurrence_signal",
        "habit.gate.explicit_correction",
        "habit.history.loaded",
        "habit.history.unavailable",
        "habit.pattern.sensitive_skipped",
        "habit.pattern.insufficient_occurrences",
        "habit.pattern.insufficient_distinct_days",
        "habit.pattern.insufficient_span",
        "habit.pattern.qualified",
        "habit.persistence.inserted_inferred",
        "habit.persistence.refreshed_inferred",
        "habit.persistence.explicit_existing_preserved",
        "habit.persistence.hidden_existing_preserved",
        "habit.persistence.superseded_by_user_correction",
        "habit.persistence.no_matching_inferred_pattern",
        "habit.persistence.embedding_failed",
        "habit.persistence.failed",
        "habit.fallback.safe_default",
    }
)

_EXPLICIT_ROUTINE_PATTERNS = (
    re.compile(
        r"\b(?:setiap|tiap|biasanya|sering|rutin|kebiasaan|"
        r"hampir\s+setiap)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+\s*(?:x|kali)\s*(?:se|per)\s*"
        r"(?:hari|minggu|bulan)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:every|usually|often|daily|weekly|weekdays|"
        r"weekends|routine|habit)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+\s+times?\s+(?:a|per)\s+(?:day|week|month)\b",
        re.IGNORECASE,
    ),
)

_OCCURRENCE_PATTERNS = (
    re.compile(
        r"^\s*(?:aku|saya|gue|gw)\s+"
        r"(?:baru\s+)?(?:selesai|habis|abis)\s+(.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*i\s+(?:just\s+)?finished\s+(.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*i\s+just\s+(?:did|completed|went\s+for|went\s+to)\s+"
        r"(.+?)\s*$",
        re.IGNORECASE,
    ),
)

_CORRECTION_PATTERNS = (
    re.compile(
        r"^\s*(?:aku|saya|gue|gw)\s+(?:sudah\s+)?"
        r"(?:tidak|nggak|ngga|gak|ga)\s+(.+?)\s+lagi\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:aku|saya|gue|gw)\s+(?:sudah\s+)?"
        r"(?:berhenti|stop)\s+(.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*i\s+(?:no\s+longer|don't|do\s+not)\s+"
        r"(.+?)(?:\s+anymore)?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*i\s+(?:stopped|quit)\s+(.+?)\s*$",
        re.IGNORECASE,
    ),
)

_TRAILING_FILLER_RE = re.compile(
    r"(?:\s+(?:lagi|tadi|hari\s+ini|nih|dong|ya|again|today|"
    r"just\s+now))+$",
    re.IGNORECASE,
)

_SENSITIVE_TERMS = {
    # Medical / health treatment.
    "obat",
    "medicine",
    "medication",
    "insulin",
    "terapi",
    "therapy",
    "dokter",
    "doctor",
    "hospital",
    "diagnosis",
    "diagnosed",
    "prescription",
    # Religion.
    "sholat",
    "salat",
    "pray",
    "prayer",
    "church",
    "mosque",
    "masjid",
    "quran",
    "bible",
    "mass",
    # Politics.
    "politik",
    "political",
    "partai",
    "party",
    "pemilu",
    "election",
    "vote",
    "voting",
    "campaign",
    # Sexual activity.
    "sex",
    "sexual",
    "porn",
    "intimacy",
    # Substance use.
    "alcohol",
    "beer",
    "wine",
    "whisky",
    "whiskey",
    "drunk",
    "rokok",
    "cigarette",
    "smoke",
    "smoking",
    "vape",
    "drugs",
    "drug",
    "thc",
    "marijuana",
}

_NON_ACTION_STATE_TERMS = {
    "capek",
    "lelah",
    "tired",
    "exhausted",
    "sedih",
    "sad",
    "stress",
    "stressed",
    "cemas",
    "anxious",
    "panik",
    "panic",
    "marah",
    "angry",
    "kesal",
    "upset",
    "bingung",
    "confused",
    "sakit",
    "sick",
    "lapar",
    "hungry",
    "ngantuk",
    "sleepy",
}


@dataclass(frozen=True)
class ActivityObservation:
    activity: str
    signature: str


@dataclass(frozen=True)
class HabitCandidate:
    activity: str
    signature: str
    structured_field: str
    observation_count: int
    distinct_days: int
    span_days: int
    confidence: float
    evidence: tuple[str, ...]

    @property
    def content(self) -> str:
        return (
            "User appears to have a recurring routine involving: "
            f"{self.activity}."
        )


@dataclass(frozen=True)
class HabitLearningAudit:
    version: str = HABIT_LEARNING_VERSION
    attempted: bool = False
    signal: HabitSignal = "none"
    action: str = "none"
    pattern_ref: str | None = None
    history_rows: int = 0
    observation_count: int = 0
    distinct_days: int = 0
    span_days: int = 0
    reason_codes: tuple[str, ...] = ()


def _append_reason(reasons: list[str], code: str) -> None:
    if code not in HABIT_REASON_CODES:
        raise ValueError(f"Unknown M32 habit reason code: {code}")
    if code not in reasons:
        reasons.append(code)


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_activity(value: Any) -> str | None:
    text = _compact(value).casefold()
    if not text:
        return None

    text = re.sub(r"^[,.;:!?'\"]+|[,.;:!?'\"]+$", "", text).strip()
    text = _TRAILING_FILLER_RE.sub("", text).strip()

    for prefix in (
        "the ",
        "my ",
        "a ",
        "an ",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > MAX_ACTIVITY_CHARS:
        return None

    words = set(re.findall(r"[a-z0-9\u00c0-\u024f]+", text))
    if not words:
        return None

    if words & _SENSITIVE_TERMS:
        return None

    if words <= _NON_ACTION_STATE_TERMS:
        return None

    if (
        len(words & _NON_ACTION_STATE_TERMS) >= 1
        and len(words) <= 3
    ):
        return None

    return text


def _pattern_ref(signature: str) -> str:
    digest = hashlib.sha256(
        signature.encode("utf-8")
    ).hexdigest()[:12]
    return f"habit_pattern_{digest}"


def _observation_from_match(match: re.Match[str]) -> ActivityObservation | None:
    activity = _normalize_activity(match.group(1))
    if not activity:
        return None
    return ActivityObservation(
        activity=activity,
        signature=activity,
    )


def parse_occurrence(user_message: str) -> ActivityObservation | None:
    if is_explicit_routine_assertion(user_message):
        return None

    for pattern in _OCCURRENCE_PATTERNS:
        match = pattern.match(
            _compact(user_message)
        )
        if match:
            return _observation_from_match(match)

    return None


def parse_explicit_correction(user_message: str) -> ActivityObservation | None:
    for pattern in _CORRECTION_PATTERNS:
        match = pattern.match(
            _compact(user_message)
        )
        if match:
            return _observation_from_match(match)

    return None


def is_explicit_routine_assertion(user_message: str) -> bool:
    text = _compact(user_message)
    return bool(
        text
        and any(
            pattern.search(text)
            for pattern in _EXPLICIT_ROUTINE_PATTERNS
        )
    )


def classify_habit_signal(user_message: str) -> HabitSignal:
    if parse_explicit_correction(user_message):
        return "explicit_correction"

    if is_explicit_routine_assertion(user_message):
        return "explicit_routine"

    if parse_occurrence(user_message):
        return "occurrence"

    return "none"


def should_attempt_habit_learning(user_message: str) -> bool:
    return classify_habit_signal(user_message) in {
        "occurrence",
        "explicit_correction",
    }


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _compact(value)
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )
    return parsed.astimezone(
        timezone.utc
    )


def _inferred_confidence(observation_count: int) -> float:
    # Deliberately below memory_lifecycle_governance.LOW_CONFIDENCE_THRESHOLD
    # (0.55). Repetition makes the signal stronger, but not user-confirmed truth.
    return round(
        min(
            MAX_INFERRED_CONFIDENCE,
            0.48 + max(0, observation_count - MIN_OCCURRENCES) * 0.015,
        ),
        2,
    )


def derive_habit_candidate(
    *,
    current_user_message: str,
    history_rows: list[dict[str, Any]],
) -> tuple[HabitCandidate | None, tuple[str, ...]]:
    reasons: list[str] = []

    current = parse_occurrence(
        current_user_message
    )
    if current is None:
        _append_reason(
            reasons,
            "habit.gate.no_signal",
        )
        return (None, tuple(reasons))

    _append_reason(
        reasons,
        "habit.gate.occurrence_signal",
    )

    observations: list[
        tuple[datetime, str]
    ] = []

    for row in history_rows:
        content = row.get("content")
        created_at = _parse_datetime(
            row.get("created_at")
        )
        if created_at is None:
            continue

        observation = parse_occurrence(
            str(content or "")
        )
        if (
            observation is None
            or observation.signature
            != current.signature
        ):
            continue

        observations.append(
            (
                created_at,
                _compact(content)[:180],
            )
        )

    # Same-day repetition counts as occurrences but cannot satisfy the
    # distinct-day requirement by itself.
    observations.sort(
        key=lambda item: item[0]
    )

    count = len(observations)
    days = {
        observed_at.date()
        for observed_at, _text in observations
    }

    distinct_days = len(days)

    span_days = (
        (
            observations[-1][0].date()
            - observations[0][0].date()
        ).days
        if observations
        else 0
    )

    if count < MIN_OCCURRENCES:
        _append_reason(
            reasons,
            "habit.pattern.insufficient_occurrences",
        )
        return (None, tuple(reasons))

    if distinct_days < MIN_DISTINCT_DAYS:
        _append_reason(
            reasons,
            "habit.pattern.insufficient_distinct_days",
        )
        return (None, tuple(reasons))

    if span_days < MIN_SPAN_DAYS:
        _append_reason(
            reasons,
            "habit.pattern.insufficient_span",
        )
        return (None, tuple(reasons))

    _append_reason(
        reasons,
        "habit.pattern.qualified",
    )

    evidence: list[str] = []
    seen: set[str] = set()

    # Prefer evidence spread across time rather than adjacent duplicate turns.
    for _observed_at, text in observations:
        if not text or text in seen:
            continue
        seen.add(text)
        evidence.append(text)
        if len(evidence) >= MAX_EVIDENCE:
            break

    candidate = HabitCandidate(
        activity=current.activity,
        signature=current.signature,
        structured_field=_pattern_ref(
            current.signature
        ),
        observation_count=count,
        distinct_days=distinct_days,
        span_days=span_days,
        confidence=_inferred_confidence(
            count
        ),
        evidence=tuple(evidence),
    )

    return (
        candidate,
        tuple(reasons),
    )


async def fetch_recent_user_messages(
    *,
    user_id: str,
    days: int = HISTORY_DAYS,
) -> list[dict[str, Any]]:
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(days=max(1, days))
    ).isoformat()

    def _conversation_query():
        return safe_execute(
            lambda sb: sb.table("conversations")
            .select("id")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(MAX_CONVERSATIONS)
            .execute()
        )

    conversations = await asyncio.to_thread(
        _conversation_query
    )

    conversation_ids = [
        str(row.get("id"))
        for row in (
            getattr(
                conversations,
                "data",
                None,
            )
            or []
        )
        if row.get("id")
    ]

    if not conversation_ids:
        return []

    def _message_query():
        return safe_execute(
            lambda sb: sb.table("messages")
            .select(
                "conversation_id, content, created_at"
            )
            .in_(
                "conversation_id",
                conversation_ids,
            )
            .eq("role", "user")
            .gte("created_at", cutoff)
            .order("created_at", desc=False)
            .limit(MAX_HISTORY_MESSAGES)
            .execute()
        )

    messages = await asyncio.to_thread(
        _message_query
    )

    return list(
        getattr(
            messages,
            "data",
            None,
        )
        or []
    )


def _fetch_existing_routine_rows(
    *,
    user_id: str,
) -> list[dict[str, Any]]:
    result = safe_execute(
        lambda sb: sb.table("memories")
        .select(
            "id, source, source_priority, category, "
            "structured_field, structured_value, confidence, "
            "evidence, archived, superseded, status, deleted_at, "
            "last_confirmed_at, last_user_confirmed_at"
        )
        .eq("user_id", user_id)
        .eq("category", "routines")
        .limit(120)
        .execute()
    )
    return list(
        getattr(
            result,
            "data",
            None,
        )
        or []
    )


def _memory_row_hidden(
    row: dict[str, Any],
) -> bool:
    status_value = str(
        row.get("status") or ""
    ).strip().lower()

    return bool(
        row.get("archived")
        or row.get("superseded")
        or row.get("deleted_at")
        or status_value in {
            "archived",
            "superseded",
            "deleted",
        }
    )


def _merge_evidence(
    existing: Any,
    incoming: tuple[str, ...],
) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    source_values = (
        existing
        if isinstance(
            existing,
            list,
        )
        else []
    )

    for raw in [
        *source_values,
        *incoming,
    ]:
        text = _compact(raw)[:180]
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
        if len(values) >= MAX_EVIDENCE:
            break

    return values


def _insert_memory_row(
    payload: dict[str, Any],
) -> str | None:
    result = safe_execute(
        lambda sb: sb.table("memories")
        .insert(payload)
        .execute()
    )
    rows = (
        getattr(
            result,
            "data",
            None,
        )
        or []
    )
    if not rows:
        return None
    memory_id = rows[0].get("id")
    return (
        str(memory_id)
        if memory_id is not None
        else None
    )


def _update_memory_row(
    *,
    user_id: str,
    memory_id: str,
    payload: dict[str, Any],
) -> None:
    safe_execute(
        lambda sb: sb.table("memories")
        .update(payload)
        .eq("id", memory_id)
        .eq("user_id", user_id)
        .execute()
    )


async def persist_habit_candidate(
    *,
    user_id: str,
    conversation_id: str,
    candidate: HabitCandidate,
) -> tuple[str, str | None]:
    existing_rows = await asyncio.to_thread(
        _fetch_existing_routine_rows,
        user_id=user_id,
    )

    active_rows = [
        row
        for row in existing_rows
        if not _memory_row_hidden(row)
    ]
    hidden_rows = [
        row
        for row in existing_rows
        if _memory_row_hidden(row)
    ]

    # Exact active M32 pattern match comes first.
    for row in active_rows:
        if (
            str(
                row.get(
                    "structured_field"
                )
                or ""
            )
            != candidate.structured_field
        ):
            continue

        source_priority = str(
            row.get(
                "source_priority"
            )
            or ""
        ).strip()

        source = str(
            row.get(
                "source"
            )
            or ""
        ).strip()

        memory_id = str(
            row.get("id")
            or ""
        ).strip()

        if (
            source_priority
            != "repeated_pattern"
            or source != "auto"
        ):
            return (
                "explicit_existing_preserved",
                memory_id or None,
            )

        if not memory_id:
            break

        try:
            existing_confidence = float(
                row.get(
                    "confidence"
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            existing_confidence = 0.0

        if (
            row.get("last_user_confirmed_at")
            or existing_confidence >= 0.55
        ):
            # A previously confirmed/raised memory is no longer treated as
            # unverified M32 inference. Never downgrade its trust.
            return (
                "explicit_existing_preserved",
                memory_id,
            )

        next_confidence = min(
            MAX_INFERRED_CONFIDENCE,
            max(
                existing_confidence,
                candidate.confidence,
            ),
        )

        await asyncio.to_thread(
            _update_memory_row,
            user_id=user_id,
            memory_id=memory_id,
            payload={
                "confidence": next_confidence,
                "evidence": _merge_evidence(
                    row.get("evidence"),
                    candidate.evidence,
                ),
            },
        )

        return (
            "refreshed_inferred",
            memory_id,
        )

    # Preserve exact active user-authored routine assertions if
    # structured_value already carries the same normalized activity.
    for row in active_rows:
        if (
            str(
                row.get(
                    "source_priority"
                )
                or ""
            )
            in {
                "explicit_user_statement",
                "user_answer_in_context",
                "user_correction",
            }
            and _normalize_activity(
                row.get(
                    "structured_value"
                )
            )
            == candidate.signature
        ):
            return (
                "explicit_existing_preserved",
                str(
                    row.get("id")
                    or ""
                )
                or None,
            )

    # A forgotten/corrected machine habit must not come back solely because
    # repeated-pattern inference sees it again. A future direct user assertion
    # is handled by memory_intelligence and may create new active truth.
    hidden_match = next(
        (
            row
            for row in hidden_rows
            if (
                str(
                    row.get("structured_field")
                    or ""
                )
                == candidate.structured_field
                or _normalize_activity(
                    row.get("structured_value")
                )
                == candidate.signature
            )
        ),
        None,
    )

    if hidden_match is not None:
        return (
            "hidden_existing_preserved",
            str(
                hidden_match.get("id")
                or ""
            )
            or None,
        )

    try:
        embedding = await embed_document(
            candidate.content
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "habit_learning: embedding failed type=%s",
            type(exc).__name__,
        )
        return (
            "embedding_failed",
            None,
        )

    payload = {
        "user_id": user_id,
        "content": candidate.content,
        "kind": "context",
        "category": "routines",
        "structured_field": (
            candidate.structured_field
        ),
        "structured_value": (
            candidate.activity
        ),
        "confidence": (
            candidate.confidence
        ),
        "source": "auto",
        "source_priority": "repeated_pattern",
        "source_conversation_id": conversation_id,
        "evidence": list(
            candidate.evidence
        ),
        "embedding": embedding,
        "archived": False,
        "superseded": False,
        "status": "active",
        "last_confirmed_at": None,
        "last_user_confirmed_at": None,
    }

    memory_id = await asyncio.to_thread(
        _insert_memory_row,
        payload,
    )

    if not memory_id:
        return (
            "failed",
            None,
        )

    return (
        "inserted_inferred",
        memory_id,
    )


async def supersede_inferred_habit(
    *,
    user_id: str,
    observation: ActivityObservation,
) -> tuple[str, str | None]:
    field = _pattern_ref(
        observation.signature
    )

    rows = await asyncio.to_thread(
        _fetch_existing_routine_rows,
        user_id=user_id,
    )

    match = next(
        (
            row
            for row in rows
            if (
                str(
                    row.get(
                        "structured_field"
                    )
                    or ""
                )
                == field
                and str(
                    row.get(
                        "source_priority"
                    )
                    or ""
                )
                == "repeated_pattern"
                and str(
                    row.get(
                        "source"
                    )
                    or ""
                )
                == "auto"
                and not _memory_row_hidden(row)
            )
        ),
        None,
    )

    if match is None:
        return (
            "no_matching_inferred_pattern",
            None,
        )

    memory_id = str(
        match.get("id")
        or ""
    ).strip()

    if not memory_id:
        return (
            "no_matching_inferred_pattern",
            None,
        )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    await asyncio.to_thread(
        _update_memory_row,
        user_id=user_id,
        memory_id=memory_id,
        payload={
            "superseded": True,
            "status": "superseded",
            "superseded_at": now,
            "updated_at": now,
        },
    )

    return (
        "superseded_by_user_correction",
        memory_id,
    )


def safe_default_audit() -> HabitLearningAudit:
    return HabitLearningAudit(
        attempted=False,
        signal="none",
        action="safe_default",
        reason_codes=(
            "habit.fallback.safe_default",
        ),
    )


async def learn_from_chat(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
) -> HabitLearningAudit:
    """Evaluate one current message against cross-conversation user evidence."""

    try:
        signal = classify_habit_signal(
            user_message
        )

        if signal == "none":
            return HabitLearningAudit(
                attempted=False,
                signal=signal,
                action="no_signal",
                reason_codes=(
                    "habit.gate.no_signal",
                ),
            )

        if signal == "explicit_routine":
            # Existing memory_intelligence owns direct user assertions.
            return HabitLearningAudit(
                attempted=False,
                signal=signal,
                action="delegated",
                reason_codes=(
                    "habit.gate.explicit_routine_delegated",
                ),
            )

        if signal == "explicit_correction":
            reasons = [
                "habit.gate.explicit_correction"
            ]

            correction = (
                parse_explicit_correction(
                    user_message
                )
            )

            if correction is None:
                return HabitLearningAudit(
                    attempted=False,
                    signal=signal,
                    action="no_signal",
                    reason_codes=(
                        "habit.gate.no_signal",
                    ),
                )

            action, memory_id = (
                await supersede_inferred_habit(
                    user_id=user_id,
                    observation=correction,
                )
            )

            reason = {
                "superseded_by_user_correction":
                    "habit.persistence.superseded_by_user_correction",
                "no_matching_inferred_pattern":
                    "habit.persistence.no_matching_inferred_pattern",
            }.get(
                action,
                "habit.persistence.failed",
            )

            _append_reason(
                reasons,
                reason,
            )

            audit = HabitLearningAudit(
                attempted=True,
                signal=signal,
                action=action,
                pattern_ref=(
                    _pattern_ref(
                        correction.signature
                    )
                ),
                reason_codes=tuple(
                    reasons
                ),
            )

            _log_audit(audit)
            return audit

        reasons = [
            "habit.gate.occurrence_signal"
        ]

        try:
            history_rows = (
                await fetch_recent_user_messages(
                    user_id=user_id
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "habit_learning: history unavailable type=%s",
                type(exc).__name__,
            )
            _append_reason(
                reasons,
                "habit.history.unavailable",
            )
            return HabitLearningAudit(
                attempted=True,
                signal=signal,
                action="history_unavailable",
                reason_codes=tuple(
                    reasons
                ),
            )

        _append_reason(
            reasons,
            "habit.history.loaded",
        )

        candidate, pattern_reasons = (
            derive_habit_candidate(
                current_user_message=user_message,
                history_rows=history_rows,
            )
        )

        for code in pattern_reasons:
            _append_reason(
                reasons,
                code,
            )

        if candidate is None:
            audit = HabitLearningAudit(
                attempted=True,
                signal=signal,
                action="insufficient_evidence",
                history_rows=len(
                    history_rows
                ),
                reason_codes=tuple(
                    reasons
                ),
            )
            _log_audit(audit)
            return audit

        action, memory_id = (
            await persist_habit_candidate(
                user_id=user_id,
                conversation_id=conversation_id,
                candidate=candidate,
            )
        )

        persistence_reason = {
            "inserted_inferred":
                "habit.persistence.inserted_inferred",
            "refreshed_inferred":
                "habit.persistence.refreshed_inferred",
            "explicit_existing_preserved":
                "habit.persistence.explicit_existing_preserved",
            "hidden_existing_preserved":
                "habit.persistence.hidden_existing_preserved",
            "embedding_failed":
                "habit.persistence.embedding_failed",
            "failed":
                "habit.persistence.failed",
        }.get(
            action,
            "habit.persistence.failed",
        )

        _append_reason(
            reasons,
            persistence_reason,
        )

        audit = HabitLearningAudit(
            attempted=True,
            signal=signal,
            action=action,
            pattern_ref=(
                candidate.structured_field
            ),
            history_rows=len(
                history_rows
            ),
            observation_count=(
                candidate.observation_count
            ),
            distinct_days=(
                candidate.distinct_days
            ),
            span_days=(
                candidate.span_days
            ),
            reason_codes=tuple(
                reasons
            ),
        )

        _log_audit(audit)
        return audit

    except Exception as exc:  # noqa: BLE001
        log.warning(
            "habit_learning: failed open type=%s",
            type(exc).__name__,
        )
        return safe_default_audit()


def _log_audit(
    audit: HabitLearningAudit,
) -> None:
    # No raw message, activity, or evidence is logged.
    log.info(
        "habit_learning: signal=%s action=%s pattern=%s "
        "history=%d observations=%d days=%d span=%d reasons=%s",
        audit.signal,
        audit.action,
        audit.pattern_ref or "-",
        audit.history_rows,
        audit.observation_count,
        audit.distinct_days,
        audit.span_days,
        ",".join(
            audit.reason_codes
        ),
    )
