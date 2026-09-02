"""Goal source-of-truth rules.

Goals should be the canonical place for goal details, progress, and check-ins.
Memories may keep a lightweight reference so the assistant remembers there is
an active goal without duplicating the full goal record.

This module is generic:
- no user-specific hardcoding
- no goal-specific hardcoding
- no assistant-name hardcoding
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import re
from typing import Any

from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoalReferenceDecision:
    should_convert: bool
    reason: str
    goal_id: str | None
    goal_title: str | None
    score: float


GOALISH_PATTERNS = (
    r"\bgoal\b",
    r"\btarget\b",
    r"\bobjective\b",
    r"\bhabit\b",
    r"\bconsistent\b",
    r"\bprogress\b",
    r"\btraining\b",
    r"\bwork(?:ing)? on\b",
    r"\bplan to\b",
    r"\bingin\b",
    r"\bmau\b",
    r"\btujuan\b",
    r"\btarget\b",
    r"\bkonsisten\b",
    r"\bolahraga\b",
)


TITLE_FIELDS = (
    "title",
    "name",
    "goal",
    "objective",
    "summary",
)

TEXT_FIELDS = (
    "title",
    "name",
    "goal",
    "objective",
    "summary",
    "description",
    "motivation",
    "target",
    "metric",
    "cadence",
)


def convert_goal_duplicate_rows(*, user_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert duplicate goal-memory rows into lightweight goal references.

    This is intentionally best-effort. On any Supabase failure, return rows
    unchanged so memory extraction never breaks chat.
    """
    if not rows:
        return rows

    goalish_rows = [row for row in rows if _row_looks_goalish(row)]
    if not goalish_rows:
        return rows

    try:
        goals = _load_active_goals(user_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("goal source rules: failed to load goals: %s", exc)
        return rows

    if not goals:
        return rows

    converted: list[dict[str, Any]] = []
    for row in rows:
        decision = decide_goal_reference(row, goals)
        if decision.should_convert:
            converted.append(convert_row_to_goal_reference(row, decision))
        else:
            converted.append(row)

    return converted


def decide_goal_reference(row: dict[str, Any], active_goals: list[dict[str, Any]]) -> GoalReferenceDecision:
    content = _clean(row.get("content"))
    if not content or not active_goals:
        return GoalReferenceDecision(False, "empty_or_no_goals", None, None, 0.0)

    if not _row_looks_goalish(row):
        return GoalReferenceDecision(False, "not_goalish", None, None, 0.0)

    best_goal: dict[str, Any] | None = None
    best_score = 0.0

    for goal in active_goals:
        score = _goal_match_score(content, goal)
        if score > best_score:
            best_score = score
            best_goal = goal

    if not best_goal:
        return GoalReferenceDecision(False, "no_match", None, None, 0.0)

    title = _goal_title(best_goal)
    goal_id = _clean(best_goal.get("id")) or None

    # 0.34 is intentionally conservative enough to avoid weak matches,
    # while allowing duplicate memories that paraphrase an existing active goal.
    if best_score >= 0.34:
        return GoalReferenceDecision(True, "matched_active_goal", goal_id, title, best_score)

    return GoalReferenceDecision(False, "low_score", goal_id, title, best_score)


def convert_row_to_goal_reference(row: dict[str, Any], decision: GoalReferenceDecision) -> dict[str, Any]:
    title = decision.goal_title or "active goal"
    value_parts = []
    if decision.goal_id:
        value_parts.append(f"goal_id={decision.goal_id}")
    value_parts.append(f"title={title}")

    converted = dict(row)
    converted["content"] = f"User has an active goal in Goals: {title}"
    converted["kind"] = "plan"
    converted["category"] = "goals"
    converted["structured_field"] = "active_goal_reference"
    converted["structured_value"] = " | ".join(value_parts)[:300]

    # M35c2a1:
    # Goal matching is a projection/normalization decision, not new evidence.
    # Preserve the incoming epistemic metadata exactly. In particular, an
    # assistant-originated plan must not be upgraded to an explicit user
    # statement merely because it matched an existing Goals record.
    #
    # Projection match != evidence strength.
    # Transformation != provenance upgrade.
    return converted


def _load_active_goals(user_id: str) -> list[dict[str, Any]]:
    supabase = get_supabase()
    result = (
        supabase.table("goals")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    return result.data or []


def _row_looks_goalish(row: dict[str, Any]) -> bool:
    category = _norm(row.get("category"))
    kind = _norm(row.get("kind"))
    field = _norm(row.get("structured_field"))
    content = _norm(row.get("content"))

    if category == "goals":
        return True
    if field in {"active_project", "scheduled_event", "active_goal_reference"}:
        return True
    if kind == "plan" and _matches_any(content, GOALISH_PATTERNS):
        return True
    return _matches_any(content, GOALISH_PATTERNS)


def _goal_match_score(content: str, goal: dict[str, Any]) -> float:
    content_norm = _norm(content)
    goal_text = _goal_text(goal)
    if not goal_text:
        return 0.0

    goal_norm = _norm(goal_text)
    seq = SequenceMatcher(None, content_norm, goal_norm).ratio()

    content_tokens = _tokens(content_norm)
    goal_tokens = _tokens(goal_norm)

    if not content_tokens or not goal_tokens:
        overlap = 0.0
    else:
        shared = content_tokens.intersection(goal_tokens)
        overlap = len(shared) / max(1, min(len(content_tokens), len(goal_tokens)))

    title = _goal_title(goal)
    title_tokens = _tokens(title)
    title_overlap = 0.0
    if title_tokens:
        title_overlap = len(content_tokens.intersection(title_tokens)) / max(1, len(title_tokens))

    return max(seq, overlap, title_overlap)


def _goal_title(goal: dict[str, Any]) -> str:
    for field in TITLE_FIELDS:
        value = _clean(goal.get(field))
        if value:
            return value[:180]
    return "active goal"


def _goal_text(goal: dict[str, Any]) -> str:
    parts = []
    for field in TEXT_FIELDS:
        value = _clean(goal.get(field))
        if value:
            parts.append(value)
    return " ".join(parts)


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value) for pattern in patterns)


def _tokens(value: str) -> set[str]:
    stop = {
        "user", "the", "and", "or", "with", "for", "to", "in", "on", "a", "an",
        "is", "has", "have", "of", "yang", "dan", "di", "ke", "untuk", "dengan",
    }
    return {t for t in re.findall(r"[a-z0-9]+", _norm(value)) if len(t) > 2 and t not in stop}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _norm(value: Any) -> str:
    return _clean(value).casefold()
