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

    if candidate.confidence < 0.72:
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
    return (result.data or [None])[0]


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
    return GoalIntelligenceResult.model_validate(parsed)


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
    except (ValidationError, json.JSONDecodeError) as exc:
        log.warning("goal intelligence: invalid model output: %s", exc)
        return counts
    except Exception as exc:  # noqa: BLE001
        log.warning("goal intelligence: extraction failed: %s", exc)
        return counts

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
