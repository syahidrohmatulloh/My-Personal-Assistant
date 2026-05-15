"""HTTP endpoints for the life model.

Only the surfaces we need in Phase 3:
- /identity (get/upsert) — needed for the new setup UI
- /people, /goals, /life-events — basic CRUD so they can be edited from the UI

We don't expose every operation the service supports (e.g. supersede
existing rows, decay confidence). Those are internal to the agent for now.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import life_model

router = APIRouter(tags=["life-model"])


# ----------------------------------------------------------------------------
# Identity
# ----------------------------------------------------------------------------


class IdentityIn(BaseModel):
    profile: dict = Field(default_factory=dict)
    narrative: str | None = None


@router.get("/identity")
async def get_identity(user_id: str = Depends(get_current_user_id)):
    data = await life_model.get_identity(user_id)
    return data or {"profile": {}, "narrative": None, "updated_at": None}


@router.put("/identity")
async def put_identity(body: IdentityIn, user_id: str = Depends(get_current_user_id)):
    return await life_model.upsert_identity(user_id, body.profile, body.narrative)


# ----------------------------------------------------------------------------
# People
# ----------------------------------------------------------------------------


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship: str | None = Field(default=None, max_length=120)
    importance: int = Field(default=5, ge=1, le=10)
    emotional_significance: int = Field(default=5, ge=1, le=10)
    birthday: date | None = None
    details: dict = Field(default_factory=dict)


@router.get("/people")
async def list_people(user_id: str = Depends(get_current_user_id)):
    return await life_model.list_people(user_id)


@router.post("/people", status_code=status.HTTP_201_CREATED)
async def create_person(body: PersonIn, user_id: str = Depends(get_current_user_id)):
    return await life_model.create_person(
        user_id=user_id,
        name=body.name,
        relationship=body.relationship,
        importance=body.importance,
        emotional_significance=body.emotional_significance,
        birthday=body.birthday,
        details=body.details,
    )


# ----------------------------------------------------------------------------
# Goals
# ----------------------------------------------------------------------------


Horizon = Literal["week", "month", "quarter", "year", "multi_year", "life"]
GoalStatus = Literal["active", "paused", "achieved", "abandoned"]


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    horizon: Horizon
    emotional_weight: int = Field(default=5, ge=1, le=10)
    target_date: date | None = None


class GoalStatusIn(BaseModel):
    status: GoalStatus


@router.get("/goals")
async def list_goals(
    status: GoalStatus | None = "active",
    user_id: str = Depends(get_current_user_id),
):
    return await life_model.list_goals(user_id, status=status)


@router.post("/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(body: GoalIn, user_id: str = Depends(get_current_user_id)):
    return await life_model.create_goal(
        user_id=user_id,
        title=body.title,
        description=body.description,
        horizon=body.horizon,
        emotional_weight=body.emotional_weight,
        target_date=body.target_date,
    )


@router.patch("/goals/{goal_id}/status")
async def update_goal_status(
    goal_id: str, body: GoalStatusIn, user_id: str = Depends(get_current_user_id)
):
    await life_model.update_goal_status(
        user_id=user_id, goal_id=goal_id, status=body.status
    )
    return {"ok": True}


# ----------------------------------------------------------------------------
# Life events
# ----------------------------------------------------------------------------


LifeEventCategory = Literal[
    "milestone", "transition", "loss", "achievement", "reflection", "health", "other"
]


class LifeEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: LifeEventCategory = "other"
    happened_on: date
    significance: int = Field(default=5, ge=1, le=10)
    tags: list[str] = Field(default_factory=list)


@router.get("/life-events")
async def list_life_events(
    days: int = 365, user_id: str = Depends(get_current_user_id)
):
    return await life_model.recent_events(user_id, days=days)


@router.post("/life-events", status_code=status.HTTP_201_CREATED)
async def create_life_event(
    body: LifeEventIn, user_id: str = Depends(get_current_user_id)
):
    return await life_model.record_life_event(
        user_id=user_id,
        title=body.title,
        description=body.description,
        category=body.category,
        happened_on=body.happened_on,
        significance=body.significance,
        tags=body.tags,
    )


# ----------------------------------------------------------------------------
# Delete endpoints
# ----------------------------------------------------------------------------


@router.delete("/people/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    person_id: str, user_id: str = Depends(get_current_user_id)
):
    await life_model.delete_person(user_id=user_id, person_id=person_id)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: str, user_id: str = Depends(get_current_user_id)
):
    await life_model.delete_goal(user_id=user_id, goal_id=goal_id)


@router.delete("/life-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_life_event(
    event_id: str, user_id: str = Depends(get_current_user_id)
):
    await life_model.delete_life_event(user_id=user_id, event_id=event_id)
