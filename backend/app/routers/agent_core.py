"""Authenticated Agent Core inspection and deterministic transition API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import agent_core


router = APIRouter(
    prefix="/agent-core",
    tags=["agent-core"],
)


ObjectiveStatus = Literal[
    "proposed",
    "active",
    "waiting",
    "paused",
    "completed",
    "cancelled",
]

StepStatus = Literal[
    "pending",
    "ready",
    "in_progress",
    "waiting",
    "blocked",
    "completed",
    "failed",
    "cancelled",
]


class TransitionIn(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=1_000,
    )
    evidence: dict[str, Any] = Field(
        default_factory=dict,
    )
    resume_after: str | None = Field(
        default=None,
        max_length=80,
    )


class StepTransitionIn(TransitionIn):
    status: StepStatus


class StepVerificationIn(BaseModel):
    status: Literal["verified", "failed"]
    evidence: dict[str, Any] = Field(
        default_factory=dict,
    )


class ObservationIn(BaseModel):
    evidence: dict[str, Any]
    plan_id: str | None = None
    step_id: str | None = None


def _translate_agent_error(
    exc: Exception,
) -> HTTPException:
    if isinstance(
        exc,
        agent_core.AgentCoreNotFound,
    ):
        return HTTPException(
            status_code=404,
            detail=str(exc),
        )

    if isinstance(
        exc,
        agent_core.InvalidAgentTransition,
    ):
        return HTTPException(
            status_code=409,
            detail=str(exc),
        )

    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=422,
            detail=str(exc),
        )

    return HTTPException(
        status_code=500,
        detail="Agent Core operation failed",
    )


@router.get("/objectives")
async def list_objectives(
    status: ObjectiveStatus | None = None,
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    return await agent_core.list_objectives(
        user_id=user_id,
        status=status,
        limit=limit,
    )


@router.get("/objectives/{objective_id}")
async def get_objective(
    objective_id: str,
    user_id: str = Depends(get_current_user_id),
):
    data = await agent_core.get_objective_detail(
        user_id=user_id,
        objective_id=objective_id,
    )

    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Objective not found",
        )

    return data


async def _objective_transition(
    *,
    objective_id: str,
    target_status: str,
    body: TransitionIn,
    user_id: str,
):
    try:
        return await agent_core.transition_objective(
            user_id=user_id,
            objective_id=objective_id,
            target_status=target_status,
            actor="user",
            reason=body.reason,
            evidence=body.evidence,
            resume_after=body.resume_after,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_agent_error(exc) from exc


@router.post("/objectives/{objective_id}/pause")
async def pause_objective(
    objective_id: str,
    body: TransitionIn,
    user_id: str = Depends(get_current_user_id),
):
    return await _objective_transition(
        objective_id=objective_id,
        target_status="paused",
        body=body,
        user_id=user_id,
    )


@router.post("/objectives/{objective_id}/resume")
async def resume_objective(
    objective_id: str,
    body: TransitionIn,
    user_id: str = Depends(get_current_user_id),
):
    return await _objective_transition(
        objective_id=objective_id,
        target_status="active",
        body=body,
        user_id=user_id,
    )


@router.post("/objectives/{objective_id}/wait")
async def wait_objective(
    objective_id: str,
    body: TransitionIn,
    user_id: str = Depends(get_current_user_id),
):
    return await _objective_transition(
        objective_id=objective_id,
        target_status="waiting",
        body=body,
        user_id=user_id,
    )


@router.post("/objectives/{objective_id}/complete")
async def complete_objective(
    objective_id: str,
    body: TransitionIn,
    user_id: str = Depends(get_current_user_id),
):
    return await _objective_transition(
        objective_id=objective_id,
        target_status="completed",
        body=body,
        user_id=user_id,
    )


@router.post("/objectives/{objective_id}/cancel")
async def cancel_objective(
    objective_id: str,
    body: TransitionIn,
    user_id: str = Depends(get_current_user_id),
):
    return await _objective_transition(
        objective_id=objective_id,
        target_status="cancelled",
        body=body,
        user_id=user_id,
    )


@router.post("/steps/{step_id}/transition")
async def transition_step(
    step_id: str,
    body: StepTransitionIn,
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await agent_core.transition_step(
            user_id=user_id,
            step_id=step_id,
            target_status=body.status,
            actor="user",
            reason=body.reason,
            evidence=body.evidence,
            resume_after=body.resume_after,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_agent_error(exc) from exc


@router.post("/steps/{step_id}/verify")
async def verify_step(
    step_id: str,
    body: StepVerificationIn,
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await agent_core.verify_step(
            user_id=user_id,
            step_id=step_id,
            verification_status=body.status,
            actor="user",
            evidence=body.evidence,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_agent_error(exc) from exc


@router.post("/objectives/{objective_id}/observations")
async def record_observation(
    objective_id: str,
    body: ObservationIn,
    user_id: str = Depends(get_current_user_id),
):
    try:
        return await agent_core.record_observation(
            user_id=user_id,
            objective_id=objective_id,
            actor="user",
            evidence=body.evidence,
            plan_id=body.plan_id,
            step_id=body.step_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_agent_error(exc) from exc
