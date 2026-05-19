"""Goal intelligence from chat.

Detects goal candidates and progress from natural conversation.

Design principles:
- Do not create confirmed goals directly from chat.
- Save goal candidates as pending suggestions.
- User confirms in Goals UI before it becomes a real goal.
- No hardcoded goal categories; extraction is based on conversation semantics.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.claude import get_claude
from app.services.supabase_client import get_supabase
from app.services import life_model

log = logging.getLogger(__name__)

Horizon = Literal["week", "month", "quarter", "year", "multi_year", "life"]


class GoalCandidate(BaseModel):
    is_goal_candidate: bool = False
    confidence: float = Field(default=0, ge=0, le=1)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=800)
    horizon: Horizon = "quarter"
    emotional_weight: int = Field(default=5, ge=1, le=10)
    target_date: str | None = None
    suggested_milestones: list[str] = Field(default_factory=list)
    assistant_reason: str | None = Field(default=None, max_length=800)


class GoalProgressSignal(BaseModel):
    goal_title_fragment: str = Field(min_length=2, max_length=200)
    momentum: int | None = Field(default=None, ge=-3, le=3)
    note: str | None = Field(default=None, max_length=800)


class GoalIntelligenceResult(BaseModel):
    goal_suggestion: GoalCandidate = Field(default_factory=GoalCandidate)
    goal_progress: list[GoalProgressSignal] = Field(default_factory=list)


GOAL_INTELLIGENCE_PROMPT = """You analyze a user-assistant chat turn for goal intelligence.

You may detect:
1. GOAL CANDIDATE
   A goal candidate is a sustained desired outcome, project, habit, life direction, or target the user may want tracked over time.

2. GOAL PROGRESS
   A progress signal is an update related to one of the user's ACTIVE GOALS listed below.

Rules:
- Do NOT invent goals.
- Do NOT treat every desire as a goal.
- A goal candidate should feel trackable over days/weeks/months, not a one-off task.
- If the user says they want to become more consistent, improve a habit, sustain a routine, or continue something they have already started, treat that as a strong goal-candidate signal.
- If the user mentions an ongoing routine, coach, trainer, class, study plan, project, or repeated activity AND asks how to keep going / be consistent / improve, it can be a goal candidate even if they do not use the word "goal".
- If the user is already doing something and reports early progress, but there is no matching active goal, suggest creating a goal candidate instead of only treating it as progress.
- If unsure, keep is_goal_candidate=false.
- For goal_progress, only reference active goals from the provided list.
- No hardcoded categories. Infer title, horizon, milestones, and reason from the conversation.
- Output strict JSON only.

Allowed horizon values:
week, month, quarter, year, multi_year, life

JSON shape:
{
  "goal_suggestion": {
    "is_goal_candidate": boolean,
    "confidence": number,
    "title": string|null,
    "description": string|null,
    "horizon": "week|month|quarter|year|multi_year|life",
    "emotional_weight": integer 1-10,
    "target_date": "YYYY-MM-DD"|null,
    "suggested_milestones": [string],
    "assistant_reason": string|null
  },
  "goal_progress": [
    {
      "goal_title_fragment": string,
      "momentum": integer -3..3|null,
      "note": string|null
    }
  ]
}
"""


def _json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]

    return json.loads(text)


def _coerce_goal_intelligence_result(parsed: dict[str, Any]) -> GoalIntelligenceResult:
    """Parse model output defensively.

    Haiku sometimes returns partially valid JSON, e.g. a good goal_suggestion
    but one malformed goal_progress item. We should not discard a valid goal
    suggestion because unrelated progress parsing failed.
    """
    if not isinstance(parsed, dict):
        return GoalIntelligenceResult()

    raw_suggestion = parsed.get("goal_suggestion") or {}
    if not isinstance(raw_suggestion, dict):
        raw_suggestion = {}

    try:
        goal_suggestion = _coerce_goal_candidate(raw_suggestion)
    except ValidationError as exc:
        log.warning(
            "goal intelligence: invalid goal_suggestion skipped: %s raw=%r",
            exc,
            raw_suggestion,
        )
        goal_suggestion = GoalCandidate()

    progress_items: list[GoalProgressSignal] = []
    raw_progress = parsed.get("goal_progress") or []
    if not isinstance(raw_progress, list):
        raw_progress = []

    for item in raw_progress[:5]:
        if not isinstance(item, dict):
            continue

        # Model sometimes uses alternative keys. Normalize gently.
        normalized = dict(item)
        if "goal_title_fragment" not in normalized:
            normalized["goal_title_fragment"] = (
                normalized.get("goal")
                or normalized.get("goal_title")
                or normalized.get("title")
                or normalized.get("goal_name")
            )

        try:
            progress_items.append(GoalProgressSignal.model_validate(normalized))
        except ValidationError as exc:
            log.warning("goal intelligence: invalid progress item skipped: %s", exc)
            continue

    return GoalIntelligenceResult(
        goal_suggestion=goal_suggestion,
        goal_progress=progress_items,
    )


def _normalize_title(value: str | None) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9\u00c0-\u024f\u1e00-\u1eff\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _valid_date_or_none(value: str | None) -> str | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _looks_like_explicit_goal_request(text: str) -> bool:
    lowered = (text or "").lower()
    goal_words = (
        "goal",
        "tujuan",
        "target",
    )
    track_words = (
        "track",
        "lacak",
        "catat",
        "simpan",
        "masukin",
        "masukkan",
        "tambahkan",
    )
    intent_words = (
        "pengen",
        "ingin",
        "mau",
        "konsisten",
        "rutin",
        "habit",
        "kebiasaan",
        "progress",
    )

    return (
        any(word in lowered for word in goal_words)
        and (
            any(word in lowered for word in track_words)
            or any(word in lowered for word in intent_words)
        )
    )


def _extract_goal_title_from_message(text: str) -> str:
    raw = " ".join((text or "").strip().split())

    # Remove explicit instruction fragments so title focuses on the user's goal.
    raw = re.sub(
        r"\b(tolong|please)?\s*(bantu\s+)?(track|lacak|catat|simpan|masukin|masukkan|tambahkan)\b.*$",
        "",
        raw,
        flags=re.IGNORECASE,
    ).strip()

    # Prefer the part after common first-person desire phrases.
    match = re.search(
        r"\b(?:aku|saya)\s+(?:pengen|ingin|mau)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        raw = match.group(1).strip()

    # Cut trailing status/update clauses.
    raw = re.split(
        r"\b(?:sekarang|saat ini|udah|sudah|dan sekarang)\b",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,.-")

    raw = re.sub(r"\s+", " ", raw).strip(" ,.-")
    if not raw:
        return "Goal from chat"

    # Keep readable title length.
    words = raw.split()
    if len(words) > 10:
        raw = " ".join(words[:10])

    return raw[:120]


def _deterministic_goal_candidate_from_user_message(user_message: str) -> GoalCandidate:
    """Fallback for explicit requests such as 'tolong track ini sebagai goal'.

    This does not hardcode any goal category or personal data. It only respects
    the user's explicit intent to track something as a goal.
    """
    if not _looks_like_explicit_goal_request(user_message):
        return GoalCandidate()

    lowered = user_message.lower()
    if "tahun" in lowered or "year" in lowered:
        horizon: Horizon = "year"
    elif "bulan" in lowered or "month" in lowered:
        horizon = "month"
    elif "minggu" in lowered or "week" in lowered:
        horizon = "week"
    else:
        horizon = "quarter"

    title = _extract_goal_title_from_message(user_message)

    return GoalCandidate(
        is_goal_candidate=True,
        confidence=0.86,
        title=title,
        description=user_message[:800],
        horizon=horizon,
        emotional_weight=6,
        target_date=None,
        suggested_milestones=[],
        assistant_reason="User explicitly asked to track this as a goal.",
    )


def _coerce_horizon(value: Any) -> Horizon:
    raw = str(value or "").lower().strip().replace("-", "_").replace(" ", "_")
    mapping: dict[str, Horizon] = {
        "week": "week",
        "weekly": "week",
        "this_week": "week",
        "month": "month",
        "monthly": "month",
        "this_month": "month",
        "quarter": "quarter",
        "quarterly": "quarter",
        "3_months": "quarter",
        "three_months": "quarter",
        "year": "year",
        "yearly": "year",
        "annual": "year",
        "annually": "year",
        "this_year": "year",
        "ongoing": "year",
        "long_term": "multi_year",
        "long-term": "multi_year",
        "multi_year": "multi_year",
        "multiyear": "multi_year",
        "life": "life",
        "lifetime": "life",
    }
    return mapping.get(raw, "quarter")


def _coerce_int_range(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _coerce_float_range(value: Any, *, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").lower().strip()
    return raw in {"true", "yes", "y", "1", "candidate", "goal_candidate"}


def _coerce_goal_candidate(raw: dict[str, Any]) -> GoalCandidate:
    normalized = dict(raw)

    if "title" not in normalized or not normalized.get("title"):
        normalized["title"] = (
            normalized.get("goal_title")
            or normalized.get("goal")
            or normalized.get("name")
            or normalized.get("summary")
        )

    if "description" not in normalized:
        normalized["description"] = (
            normalized.get("why")
            or normalized.get("reason")
            or normalized.get("details")
        )

    if "assistant_reason" not in normalized:
        normalized["assistant_reason"] = (
            normalized.get("reason")
            or normalized.get("rationale")
            or normalized.get("why_this_matters")
        )

    normalized["is_goal_candidate"] = _coerce_bool(
        normalized.get("is_goal_candidate", normalized.get("goal_candidate", False))
    )
    normalized["confidence"] = _coerce_float_range(
        normalized.get("confidence"),
        default=0.0,
        low=0.0,
        high=1.0,
    )
    normalized["horizon"] = _coerce_horizon(normalized.get("horizon"))
    normalized["emotional_weight"] = _coerce_int_range(
        normalized.get("emotional_weight", normalized.get("importance")),
        default=5,
        low=1,
        high=10,
    )

    target_date = normalized.get("target_date")
    normalized["target_date"] = _valid_date_or_none(str(target_date)) if target_date else None

    milestones = normalized.get("suggested_milestones") or normalized.get("milestones") or []
    if isinstance(milestones, str):
        milestones = [milestones]
    if not isinstance(milestones, list):
        milestones = []
    normalized["suggested_milestones"] = [str(item).strip() for item in milestones if str(item).strip()][:8]

    # If the model wrote a useful title but forgot the boolean, infer candidate.
    if normalized.get("title") and normalized["confidence"] >= 0.60:
        normalized["is_goal_candidate"] = True

    return GoalCandidate.model_validate(normalized)


async def _load_pending_suggestions(user_id: str) -> list[dict]:
    result = (
        get_supabase()
        .table("goal_suggestions")
        .select("id, title")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return result.data or []


async def _insert_goal_suggestion(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    candidate: GoalCandidate,
) -> dict | None:
    if not candidate.is_goal_candidate:
        return None

    if candidate.confidence < 0.68:
        return None

    title = (candidate.title or "").strip()
    if len(title) < 3:
        return None

    normalized_title = _normalize_title(title)
    for existing in await _load_pending_suggestions(user_id):
        if _normalize_title(existing.get("title")) == normalized_title:
            return existing

    payload = {
        "user_id": user_id,
        "title": title,
        "description": candidate.description,
        "horizon": candidate.horizon,
        "emotional_weight": candidate.emotional_weight,
        "target_date": _valid_date_or_none(candidate.target_date),
        "suggested_milestones": candidate.suggested_milestones[:8],
        "assistant_reason": candidate.assistant_reason,
        "source_conversation_id": conversation_id,
        "source_message": user_message[:1500],
        "confidence": round(float(candidate.confidence), 3),
        "status": "pending",
    }

    result = get_supabase().table("goal_suggestions").insert(payload).execute()
    saved = (result.data or [None])[0]
    if saved:
        log.info(
            "goal intelligence: saved suggestion user=%s title=%s confidence=%.2f",
            user_id,
            title[:80],
            float(candidate.confidence),
        )
    return saved


def _match_active_goal(active_goals: list[dict], fragment: str) -> dict | None:
    needle = _normalize_title(fragment)
    if not needle:
        return None

    best: dict | None = None
    best_score = 0

    for goal in active_goals:
        title = _normalize_title(goal.get("title"))
        if not title:
            continue

        if needle in title or title in needle:
            score = min(len(needle), len(title))
        else:
            needle_words = set(needle.split())
            title_words = set(title.split())
            score = len(needle_words & title_words)

        if score > best_score:
            best = goal
            best_score = score

    return best if best_score >= 1 else None


async def _persist_progress_signals(
    *,
    user_id: str,
    active_goals: list[dict],
    progress: list[GoalProgressSignal],
) -> int:
    count = 0

    for item in progress[:5]:
        matched = _match_active_goal(active_goals, item.goal_title_fragment)
        if not matched:
            continue

        await life_model.add_goal_check_in(
            user_id=user_id,
            goal_id=matched["id"],
            momentum=item.momentum,
            note=item.note,
            source="chat",
            created_by="assistant",
        )
        count += 1

    return count


async def _call_goal_intelligence_model(
    *,
    user_message: str,
    assistant_response: str,
    active_goals: list[dict],
) -> GoalIntelligenceResult:
    goals_block = (
        "\n".join(
            f"- id={g.get('id')} title={g.get('title')} horizon={g.get('horizon')}"
            for g in active_goals[:12]
        )
        if active_goals
        else "(none)"
    )

    user_content = (
        f"## Active goals\n{goals_block}\n\n"
        f"## User message\n{user_message}\n\n"
        f"## Assistant reply\n{assistant_response}\n"
    )

    claude = get_claude()
    response = await claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=900,
        temperature=0,
        system=GOAL_INTELLIGENCE_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    text = response.content[0].text if response.content else "{}"
    parsed = _json_from_text(text)
    return _coerce_goal_intelligence_result(parsed)


async def extract_and_persist(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_response: str,
) -> dict[str, int]:
    """Background task used by chat.py."""
    counts = {"suggestions": 0, "check_ins": 0}

    if not user_message.strip():
        return counts

    try:
        active_goals = await life_model.list_goals(user_id, status="active")
    except Exception as exc:  # noqa: BLE001
        log.warning("goal intelligence: failed to load active goals: %s", exc)
        active_goals = []

    try:
        result = await _call_goal_intelligence_model(
            user_message=user_message,
            assistant_response=assistant_response,
            active_goals=active_goals,
        )
    except json.JSONDecodeError as exc:
        log.warning("goal intelligence: invalid model JSON: %s", exc)
        return counts
    except Exception as exc:  # noqa: BLE001
        log.warning("goal intelligence: extraction failed: %s", exc)
        return counts

    log.info(
        "goal intelligence: decision user=%s is_candidate=%s confidence=%.2f title=%r progress_count=%d",
        user_id,
        result.goal_suggestion.is_goal_candidate,
        float(result.goal_suggestion.confidence or 0),
        result.goal_suggestion.title,
        len(result.goal_progress or []),
    )

    if not result.goal_suggestion.is_goal_candidate:
        fallback_candidate = _deterministic_goal_candidate_from_user_message(user_message)
        if fallback_candidate.is_goal_candidate:
            log.info(
                "goal intelligence: using deterministic explicit-goal fallback title=%r",
                fallback_candidate.title,
            )
            result = result.model_copy(update={"goal_suggestion": fallback_candidate})

    suggestion = await _insert_goal_suggestion(
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=user_message,
        candidate=result.goal_suggestion,
    )
    if suggestion:
        counts["suggestions"] += 1

    counts["check_ins"] = await _persist_progress_signals(
        user_id=user_id,
        active_goals=active_goals,
        progress=result.goal_progress,
    )

    return counts
