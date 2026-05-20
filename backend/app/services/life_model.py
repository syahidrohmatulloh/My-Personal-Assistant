"""Life model service — typed access to the digital twin substrate.

Every function in here is a thin, intent-revealing wrapper over Supabase
queries. Three principles encoded throughout:

  1. Retrieval is hierarchical (identity > goals > people > mood > events).
     `get_context()` returns data in that order; the prompt builder preserves it.

  2. Inferred rows are never destructively overwritten. Corrections create new
     rows and mark the originals `superseded = true`. Reads exclude superseded
     rows by default.

  3. User-authored truth dominates inferred truth. `record_self_report_mood`
     supersedes any inferred mood from the same hour to keep the explicit
     statement on top.

The agent calls this service. The chat router calls the agent. The
service doesn't know about HTTP, FastAPI, or Anthropic.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Literal

from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Identity
# ----------------------------------------------------------------------------

async def get_identity(user_id: str) -> dict | None:
    """Fetch the user's identity row. Returns None if they haven't set one yet."""
    supabase = get_supabase()
    result = (
        supabase.table("user_identity")
        .select("profile, narrative, updated_at")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


async def upsert_identity(user_id: str, profile: dict, narrative: str | None = None) -> dict:
    """Create or update the user's identity. Replaces the profile wholesale.

    Caller is responsible for merging if they want incremental updates —
    we deliberately don't auto-merge because identity changes are rare and
    explicit, and merging silently has bitten me before.
    """
    supabase = get_supabase()
    payload: dict[str, Any] = {
        "user_id": user_id,
        "profile": profile,
        "updated_at": "now()",
    }
    if narrative is not None:
        payload["narrative"] = narrative

    result = supabase.table("user_identity").upsert(payload).execute()
    if not result.data:
        raise RuntimeError("failed to upsert identity")
    return result.data[0]


# ----------------------------------------------------------------------------
# Emotional state
# ----------------------------------------------------------------------------

MoodSource = Literal["self_report", "inferred", "passive"]


async def record_mood(
    *,
    user_id: str,
    mood: int | None = None,
    energy: int | None = None,
    stress: int | None = None,
    dimensions: dict | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
    source: MoodSource = "self_report",
    confidence: float = 1.0,
    observed_at: datetime | None = None,
) -> dict:
    """Record one observation of emotional state.

    Principle 3 — user-authored truth dominates inferred truth: if this is a
    self-report and there's an inferred mood from within the last hour, we
    supersede it. This keeps explicit statements at the top of retrieval.
    """
    supabase = get_supabase()
    created_by = "user" if source == "self_report" else "assistant"

    # Principle 3: supersede recent inferred rows when this is a self-report.
    if source == "self_report":
        hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        supabase.table("emotional_state").update(
            {"superseded": True, "superseded_at": "now()"}
        ).eq("user_id", user_id).eq("source", "inferred").eq("superseded", False).gte(
            "observed_at", hour_ago
        ).execute()

    payload: dict[str, Any] = {
        "user_id": user_id,
        "mood": mood,
        "energy": energy,
        "stress": stress,
        "dimensions": dimensions or {},
        "note": note,
        "tags": tags or [],
        "source": source,
        "created_by": created_by,
        "confidence": confidence,
    }
    if observed_at:
        payload["observed_at"] = observed_at.isoformat()

    result = supabase.table("emotional_state").insert(payload).execute()
    return result.data[0]


async def recent_mood(user_id: str, days: int = 14) -> list[dict]:
    """Return non-superseded mood observations from the last N days, newest first."""
    supabase = get_supabase()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    result = (
        supabase.table("emotional_state")
        .select("id, mood, energy, stress, dimensions, note, tags, source, confidence, observed_at")
        .eq("user_id", user_id)
        .eq("superseded", False)
        .gte("observed_at", since)
        .order("observed_at", desc=True)
        .execute()
    )
    return result.data or []


# ----------------------------------------------------------------------------
# People + relationship notes
# ----------------------------------------------------------------------------

async def list_people(user_id: str) -> list[dict]:
    supabase = get_supabase()
    result = (
        supabase.table("people")
        .select("*")
        .eq("user_id", user_id)
        .order("importance", desc=True)
        .execute()
    )
    return result.data or []


async def create_person(
    *,
    user_id: str,
    name: str,
    relationship: str | None = None,
    importance: int = 5,
    emotional_significance: int = 5,
    birthday: date | None = None,
    details: dict | None = None,
) -> dict:
    supabase = get_supabase()
    payload = {
        "user_id": user_id,
        "name": name,
        "relationship": relationship,
        "importance": importance,
        "emotional_significance": emotional_significance,
        "birthday": birthday.isoformat() if birthday else None,
        "details": details or {},
    }
    result = supabase.table("people").insert(payload).execute()
    return result.data[0]


async def add_relationship_note(
    *,
    user_id: str,
    person_id: str,
    content: str,
    kind: Literal["fact", "recent_event", "sentiment", "follow_up"],
    source: Literal["self_report", "inferred", "chat"] = "chat",
    created_by: Literal["user", "assistant"] = "assistant",
    confidence: float = 0.8,
) -> dict:
    supabase = get_supabase()
    payload = {
        "user_id": user_id,
        "person_id": person_id,
        "content": content,
        "kind": kind,
        "source": source,
        "created_by": created_by,
        "confidence": confidence,
    }
    result = supabase.table("relationship_notes").insert(payload).execute()
    return result.data[0]


# ----------------------------------------------------------------------------
# Life events
# ----------------------------------------------------------------------------

LifeEventCategory = Literal[
    "milestone", "transition", "loss", "achievement", "reflection", "health", "other"
]


async def record_life_event(
    *,
    user_id: str,
    title: str,
    happened_on: date,
    category: LifeEventCategory = "other",
    description: str | None = None,
    significance: int = 5,
    tags: list[str] | None = None,
    source: Literal["self_report", "inferred", "chat"] = "self_report",
    created_by: Literal["user", "assistant"] = "user",
) -> dict:
    supabase = get_supabase()
    payload = {
        "user_id": user_id,
        "title": title,
        "description": description,
        "category": category,
        "happened_on": happened_on.isoformat(),
        "significance": significance,
        "tags": tags or [],
        "source": source,
        "created_by": created_by,
    }
    result = supabase.table("life_events").insert(payload).execute()
    return result.data[0]


async def recent_events(user_id: str, days: int = 90) -> list[dict]:
    supabase = get_supabase()
    since = (date.today() - timedelta(days=days)).isoformat()
    result = (
        supabase.table("life_events")
        .select("*")
        .eq("user_id", user_id)
        .gte("happened_on", since)
        .order("happened_on", desc=True)
        .execute()
    )
    return result.data or []


# ----------------------------------------------------------------------------
# Goals + check-ins
# ----------------------------------------------------------------------------

Horizon = Literal["week", "month", "quarter", "year", "multi_year", "life"]


async def list_goals(
    user_id: str, status: Literal["active", "paused", "achieved", "abandoned"] | None = "active"
) -> list[dict]:
    supabase = get_supabase()
    q = supabase.table("goals").select("*").eq("user_id", user_id)
    if status:
        q = q.eq("status", status)
    result = q.order("emotional_weight", desc=True).execute()
    return result.data or []


async def create_goal(
    *,
    user_id: str,
    title: str,
    horizon: Horizon,
    description: str | None = None,
    emotional_weight: int = 5,
    target_date: date | None = None,
) -> dict:
    supabase = get_supabase()
    payload = {
        "user_id": user_id,
        "title": title,
        "description": description,
        "horizon": horizon,
        "emotional_weight": emotional_weight,
        "target_date": target_date.isoformat() if target_date else None,
    }
    result = supabase.table("goals").insert(payload).execute()
    return result.data[0]


async def update_goal(
    *,
    user_id: str,
    goal_id: str,
    title: str | None = None,
    description: str | None = None,
    horizon: Horizon | None = None,
    emotional_weight: int | None = None,
    target_date: date | None = None,
    clear_target_date: bool = False,
) -> dict:
    supabase = get_supabase()

    payload: dict[str, Any] = {"updated_at": "now()"}

    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if horizon is not None:
        payload["horizon"] = horizon
    if emotional_weight is not None:
        payload["emotional_weight"] = emotional_weight
    if clear_target_date:
        payload["target_date"] = None
    elif target_date is not None:
        payload["target_date"] = target_date.isoformat()

    if len(payload) == 1:
        result = (
            supabase.table("goals")
            .select("*")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            raise ValueError("Goal not found")
        return result.data

    result = (
        supabase.table("goals")
        .update(payload)
        .eq("id", goal_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        raise ValueError("Goal not found")

    return result.data[0]


async def update_goal_status(
    *,
    user_id: str,
    goal_id: str,
    status: Literal["active", "paused", "achieved", "abandoned"],
) -> None:
    supabase = get_supabase()
    supabase.table("goals").update({"status": status, "updated_at": "now()"}).eq(
        "id", goal_id
    ).eq("user_id", user_id).execute()


async def add_goal_check_in(
    *,
    user_id: str,
    goal_id: str,
    momentum: int | None,
    note: str | None,
    source: Literal["self_report", "inferred", "chat"] = "chat",
    created_by: Literal["user", "assistant"] = "assistant",
) -> dict:
    supabase = get_supabase()
    payload = {
        "user_id": user_id,
        "goal_id": goal_id,
        "momentum": momentum,
        "note": note,
        "source": source,
        "created_by": created_by,
    }
    result = supabase.table("goal_check_ins").insert(payload).execute()
    return result.data[0]


async def list_goal_suggestions(user_id: str, status: str = "pending") -> list[dict]:
    supabase = get_supabase()
    q = supabase.table("goal_suggestions").select("*").eq("user_id", user_id)
    if status:
        q = q.eq("status", status)
    result = q.order("created_at", desc=True).execute()
    return result.data or []


async def confirm_goal_suggestion(*, user_id: str, suggestion_id: str) -> dict:
    supabase = get_supabase()

    result = (
        supabase.table("goal_suggestions")
        .select("*")
        .eq("id", suggestion_id)
        .eq("user_id", user_id)
        .eq("status", "pending")
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise ValueError("Goal suggestion not found")

    suggestion = result.data

    created = await create_goal(
        user_id=user_id,
        title=suggestion["title"],
        description=suggestion.get("description"),
        horizon=suggestion.get("horizon") or "quarter",
        emotional_weight=int(suggestion.get("emotional_weight") or 5),
        target_date=date.fromisoformat(suggestion["target_date"])
        if suggestion.get("target_date")
        else None,
    )

    supabase.table("goal_suggestions").update(
        {
            "status": "confirmed",
            "confirmed_goal_id": created["id"],
            "updated_at": "now()",
        }
    ).eq("id", suggestion_id).eq("user_id", user_id).execute()

    if suggestion.get("assistant_reason"):
        await add_goal_check_in(
            user_id=user_id,
            goal_id=created["id"],
            momentum=None,
            note=f"Created from Aliyya suggestion: {suggestion['assistant_reason']}",
            source="chat",
            created_by="assistant",
        )

    return created


async def dismiss_goal_suggestion(*, user_id: str, suggestion_id: str) -> None:
    get_supabase().table("goal_suggestions").update(
        {"status": "dismissed", "updated_at": "now()"}
    ).eq("id", suggestion_id).eq("user_id", user_id).execute()


# ----------------------------------------------------------------------------
# The single-query context fetch
# ----------------------------------------------------------------------------

async def get_context(user_id: str, mood_days: int = 14) -> dict:
    """One-shot snapshot of the user's life model.

    Calls the `get_user_context()` SQL function (defined in schema_phase3.sql),
    which returns a single jsonb with identity, goals, people, mood, events,
    and recent self-reflections — in a stable, retrieval-prioritized order.

    Principle 1 — hierarchical retrieval: the SQL function returns keys in a
    specific order. The prompt builder preserves that order when serializing
    into the system prompt.
    """
    supabase = get_supabase()
    result = supabase.rpc(
        "get_user_context",
        {"p_user_id": user_id, "p_mood_days": mood_days},
    ).execute()
    return result.data or {}


# ----------------------------------------------------------------------------
# Delete helpers
# ----------------------------------------------------------------------------

async def delete_person(*, user_id: str, person_id: str) -> None:
    supabase = get_supabase()
    supabase.table("people").delete().eq("id", person_id).eq("user_id", user_id).execute()


async def delete_goal(*, user_id: str, goal_id: str) -> None:
    supabase = get_supabase()
    supabase.table("goals").delete().eq("id", goal_id).eq("user_id", user_id).execute()


async def delete_life_event(*, user_id: str, event_id: str) -> None:
    supabase = get_supabase()
    supabase.table("life_events").delete().eq("id", event_id).eq("user_id", user_id).execute()
