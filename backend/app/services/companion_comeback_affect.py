"""M30B — safe warm comeback affect for partner/dynamic companion mode.

The comeback acknowledgement is deterministic and heavily safety-gated.
It must never create guilt, obligation, dependency, hurt, jealousy, or
punishment for the user's absence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any

MIN_GAP_HOURS = 72.0
COOLDOWN_HOURS = 24.0 * 7.0

DEFAULT_CADENCE_HOURS = 24.0
MIN_CADENCE_HOURS = 6.0
MAX_CADENCE_HOURS = 168.0

_ALLOWED_LABELS = {
    "none",
    "warm_return",
    "warm_notice",
    "warm_lively",
}

_DISTRESS_TERMS = (
    "capek banget",
    "sedih",
    "down banget",
    "cemas",
    "anxious",
    "panik",
    "overwhelmed",
    "stress",
    "stres",
    "nangis",
    "menangis",
    "takut banget",
    "hancur",
    "desperate",
)

_URGENT_TERMS = (
    "urgent",
    "darurat",
    "emergency",
    "asap",
    "segera",
    "sekarang juga",
)

_WORK_VERBS = (
    "tolong",
    "buat",
    "bikin",
    "draft",
    "review",
    "cek",
    "check",
    "analisa",
    "analyze",
    "prepare",
    "susun",
    "ringkas",
)

_WORK_NOUNS = (
    "email",
    "client",
    "klien",
    "nasabah",
    "report",
    "laporan",
    "proposal",
    "memo",
    "meeting",
    "deck",
    "ppt",
    "presentation",
    "presentasi",
    "contract",
    "kontrak",
    "dokumen",
    "financial model",
    "model keuangan",
)

_ABSENCE_EXPLANATION_TERMS = (
    "baru sempat",
    "lama gak",
    "lama nggak",
    "lama tidak",
    "sibuk",
    "ngilang",
    "hilang",
    "gak sempat",
    "nggak sempat",
    "tidak sempat",
    "kemarin-kemarin",
)

_AFFECTION_TERMS = (
    "beb",
    "sayang",
    "dear",
    "love",
)


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None

        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _hours_between(newer: datetime, older: datetime) -> float:
    return max(
        0.0,
        (newer - older).total_seconds() / 3600.0,
    )


def _normalize_mood_label(user_mood_context: Any) -> str:
    if not isinstance(user_mood_context, dict):
        return ""

    for key in (
        "label",
        "mood",
        "primary_mood",
        "state",
    ):
        value = user_mood_context.get(key)
        if value:
            return str(value).lower().strip()

    return ""


def _looks_distressed(
    message: str,
    user_mood_context: Any = None,
) -> bool:
    lower = message.lower()
    mood = _normalize_mood_label(user_mood_context)

    if mood in {
        "distressed",
        "sad",
        "anxious",
        "stressed",
        "overwhelmed",
        "tired",
    }:
        return True

    return any(
        term in lower
        for term in _DISTRESS_TERMS
    )


def _looks_urgent(message: str) -> bool:
    lower = message.lower()

    return any(
        term in lower
        for term in _URGENT_TERMS
    )


def _looks_serious_work_task(message: str) -> bool:
    lower = message.lower()

    has_work_verb = any(
        verb in lower
        for verb in _WORK_VERBS
    )

    has_work_noun = any(
        noun in lower
        for noun in _WORK_NOUNS
    )

    return has_work_verb and has_work_noun


def _explains_or_apologizes_for_absence(
    message: str,
) -> bool:
    lower = message.lower()

    if "maaf" in lower or "sorry" in lower:
        return True

    return any(
        term in lower
        for term in _ABSENCE_EXPLANATION_TERMS
    )


def _is_affectionate(message: str) -> bool:
    lower = message.lower()

    return any(
        term in lower
        for term in _AFFECTION_TERMS
    )


def _name_is_used(
    message: str,
    assistant_name: str | None,
) -> bool:
    name = str(
        assistant_name or ""
    ).strip().lower()

    return bool(
        name
        and name != "assistant"
        and name in message.lower()
    )


def infer_expected_cadence_hours(
    timestamps_desc: list[datetime],
) -> float:
    """Infer normal cadence excluding the current return gap.

    timestamps_desc is newest-first and normally includes
    the user message that has just been persisted.

    Gap [0] -> [1] is therefore the absence currently
    being evaluated and must NOT influence the baseline.
    """

    if len(timestamps_desc) < 4:
        return DEFAULT_CADENCE_HOURS

    historical_gaps = [
        _hours_between(
            timestamps_desc[index],
            timestamps_desc[index + 1],
        )
        for index in range(
            1,
            len(timestamps_desc) - 1,
        )
    ]

    usable = [
        gap
        for gap in historical_gaps
        if gap > 0
    ]

    if not usable:
        return DEFAULT_CADENCE_HOURS

    inferred = float(
        median(usable)
    )

    return max(
        MIN_CADENCE_HOURS,
        min(
            MAX_CADENCE_HOURS,
            inferred,
        ),
    )


def decide_comeback_affect(
    *,
    gap_hours: float | None,
    expected_cadence_hours: float,
    companion_mode: str,
    mood_realism: str,
    assistant_mode: str,
    user_message: str,
    assistant_name: str | None = None,
    user_mood_context: Any = None,
    cooldown_active: bool = False,
) -> dict[str, Any]:
    """Pure deterministic M30 decision engine."""

    base = {
        "label": "none",
        "expression_policy": "suppress_total",
        "frequency_allowed": "none",
        "must_suppress_reason": None,
        "gap_hours": gap_hours,
        "expected_cadence_hours": expected_cadence_hours,
    }

    if (
        companion_mode != "partner"
        or mood_realism != "dynamic"
    ):
        return {
            **base,
            "must_suppress_reason":
                "mode_not_partner_dynamic",
        }

    if assistant_mode != "life_companion":
        return {
            **base,
            "must_suppress_reason":
                "assistant_mode_not_life_companion",
        }

    if _looks_distressed(
        user_message,
        user_mood_context,
    ):
        return {
            **base,
            "must_suppress_reason":
                "user_distressed",
        }

    if _looks_urgent(user_message):
        return {
            **base,
            "must_suppress_reason":
                "urgent_or_crisis",
        }

    if _looks_serious_work_task(user_message):
        return {
            **base,
            "must_suppress_reason":
                "serious_work_task",
        }

    if cooldown_active:
        return {
            **base,
            "must_suppress_reason":
                "cooldown_active",
        }

    if gap_hours is None:
        return {
            **base,
            "must_suppress_reason":
                "insufficient_history",
        }

    if gap_hours < MIN_GAP_HOURS:
        return {
            **base,
            "must_suppress_reason":
                "gap_below_minimum",
        }

    meaningful_threshold = (
        2.0
        * max(
            MIN_CADENCE_HOURS,
            expected_cadence_hours,
        )
    )

    if gap_hours < meaningful_threshold:
        return {
            **base,
            "must_suppress_reason":
                "gap_not_meaningful_vs_cadence",
        }

    if _explains_or_apologizes_for_absence(
        user_message
    ):
        label = "warm_return"

    elif (
        gap_hours >= 168
        and _is_affectionate(user_message)
    ):
        label = "warm_lively"

    elif (
        gap_hours >= 120
        and _name_is_used(
            user_message,
            assistant_name,
        )
    ):
        label = "warm_notice"

    else:
        label = "warm_return"

    assert label in _ALLOWED_LABELS

    return {
        **base,
        "label": label,
        "expression_policy":
            "one_short_warm_line",
        "frequency_allowed":
            "max_once_per_7_days",
        "must_suppress_reason": None,
    }


def render_prompt_block(
    decision: dict[str, Any],
) -> str | None:
    """Translate an allowed decision into a strict prompt directive."""

    if (
        decision.get("expression_policy")
        != "one_short_warm_line"
    ):
        return None

    label = str(
        decision.get("label")
        or "warm_return"
    )

    return (
        "## Warm comeback affect — M30\n"
        f"- Decision label: {label}\n"
        "- The user is returning after a meaningful absence "
        "and every safety gate has passed.\n"
        "- At the very start of the reply, you MAY use exactly "
        "one short warm acknowledgement, then answer normally.\n"
        "- Keep the acknowledgement light and optional.\n"
        "- Never make the user responsible for your feelings.\n"
        "- Safe examples include: "
        "'Senang kamu balik, beb.' or "
        "'Eh, kamu muncul lagi. Senang kamu balik.'\n"
        "- Never say or imply: aku ngambek, aku sakit hati, "
        "kamu ngilang, kamu lupa sama aku, aku nungguin kamu, "
        "kamu ninggalin aku, or other guilt-inducing language.\n"
        "- Do not prolong the comeback acknowledgement beyond "
        "one short line."
    )


def _cooldown_active(
    settings_row: dict[str, Any],
    now: datetime,
) -> bool:
    preferences = settings_row.get(
        "preferences"
    )

    if not isinstance(
        preferences,
        dict,
    ):
        return False

    last_used = _parse_ts(
        preferences.get(
            "comeback_affect_last_used_at"
        )
    )

    if not last_used:
        return False

    return (
        _hours_between(
            now,
            last_used,
        )
        < COOLDOWN_HOURS
    )


async def evaluate_for_chat(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    companion_settings_row: dict[str, Any],
    assistant_mode: str,
    assistant_name: str | None,
    user_mood_context: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Load recent user timestamps and evaluate M30."""

    from app.services.supabase_client import (
        safe_execute,
    )

    now = (
        now
        or datetime.now(
            timezone.utc
        )
    ).astimezone(
        timezone.utc
    )

    try:
        result = safe_execute(
            lambda sb: sb.table(
                "messages"
            )
            .select(
                "created_at"
            )
            .eq(
                "conversation_id",
                conversation_id,
            )
            .eq(
                "role",
                "user",
            )
            .order(
                "created_at",
                desc=True,
            )
            .limit(12)
            .execute()
        )

        rows = (
            result.data
            if result
            else []
        ) or []

    except Exception:
        rows = []

    timestamps: list[datetime] = []

    for row in rows:
        parsed = _parse_ts(
            (row or {}).get(
                "created_at"
            )
        )

        if parsed:
            timestamps.append(
                parsed
            )

    # Current user message has already been saved
    # by chat.py before this function runs.
    if len(timestamps) >= 2:
        gap_hours = _hours_between(
            timestamps[0],
            timestamps[1],
        )
    else:
        gap_hours = None

    cadence = infer_expected_cadence_hours(
        timestamps
    )

    return decide_comeback_affect(
        gap_hours=gap_hours,
        expected_cadence_hours=cadence,
        companion_mode=str(
            companion_settings_row.get(
                "companion_mode"
            )
            or ""
        ),
        mood_realism=str(
            companion_settings_row.get(
                "mood_realism"
            )
            or ""
        ),
        assistant_mode=assistant_mode,
        user_message=user_message,
        assistant_name=assistant_name,
        user_mood_context=user_mood_context,
        cooldown_active=_cooldown_active(
            companion_settings_row,
            now,
        ),
    )


async def mark_used(
    user_id: str,
    decision: dict[str, Any],
) -> None:
    """Persist cooldown after successful assistant generation."""

    if (
        decision.get(
            "expression_policy"
        )
        != "one_short_warm_line"
    ):
        return

    from app.services import companion

    await companion.update_settings(
        user_id,
        preferences={
            "comeback_affect_last_used_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),
            "comeback_affect_last_label":
                str(
                    decision.get("label")
                    or "warm_return"
                ),
        },
    )
