"""Explicit Agent Core objective activation from chat.

This module may use an LLM to structure a plan, but it never decides whether
implicit inference is sufficient authority. Durable creation is attempted only
after deterministic explicit-user-request gating succeeds.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.services import agent_core
from app.services.claude import get_claude


log = logging.getLogger(__name__)


StepKind = Literal[
    "internal",
    "user_input",
    "wait_time",
    "observe",
    "verify",
    "external_action",
]

Priority = Literal[
    "low",
    "normal",
    "high",
]


class ObjectiveStepDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(
        default=None,
        max_length=2_000,
    )
    step_kind: StepKind = "internal"
    requires_verification: bool = False


class ObjectiveDraft(BaseModel):
    should_create: bool = False
    title: str | None = Field(
        default=None,
        max_length=200,
    )
    desired_outcome: str | None = Field(
        default=None,
        max_length=5_000,
    )
    priority: Priority = "normal"
    steps: list[ObjectiveStepDraft] = Field(
        default_factory=list,
        max_length=12,
    )


OBJECTIVE_DRAFT_PROMPT = """You structure an explicitly requested Agent Core objective.

The calling code has already decided that the user explicitly asked Aliyya
to create/track an operational objective. You do NOT decide authority.

Return strict JSON only.

Rules:
- Capture the operational outcome the user wants Aliyya to help complete.
- Do not turn a vague life aspiration into an operational objective unless
  the user's message itself contains a concrete operational outcome.
- Produce 2-12 practical steps for a multi-step objective.
- A step may be:
  internal, user_input, wait_time, observe, verify, external_action.
- external_action is representational only. Do not claim it has executed.
- Use requires_verification=true when completion needs evidence.
- Prefer a verify step when the final result should be checked.
- Do not invent private facts, dates, people, accounts, or external results.
- If the request cannot be represented safely or concretely, set
  should_create=false.

JSON:
{
  "should_create": boolean,
  "title": string|null,
  "desired_outcome": string|null,
  "priority": "low|normal|high",
  "steps": [
    {
      "title": string,
      "description": string|null,
      "step_kind": "internal|user_input|wait_time|observe|verify|external_action",
      "requires_verification": boolean
    }
  ]
}
"""


_OBJECTIVE_NOUNS = (
    "objective",
    "objectives",
    "objektif",
)

_ACTION_MARKERS = (
    "buat objective",
    "buatkan objective",
    "buat objektif",
    "buatkan objektif",
    "jadikan objective",
    "jadikan objektif",
    "track sebagai objective",
    "track jadi objective",
    "track ini sebagai objective",
    "track ini jadi objective",
    "create objective",
    "create an objective",
    "make this an objective",
    "track this as an objective",
    "manage this objective",
    "kelola objective",
    "kelola objektif",
)

_CAPABILITY_MARKERS = (
    "apakah kamu bisa",
    "apa kamu bisa",
    "bisa nggak",
    "bisa gak",
    "bisakah",
    "can you",
    "could you",
)

_DIRECT_REQUEST_OVERRIDE_MARKERS = (
    "tolong",
    "please",
    "langsung",
    "sekarang",
    "now",
    "go ahead",
    "ya, buat",
    "ya buat",
    "ya, track",
    "ya track",
)


def _normalize(value: str | None) -> str:
    return " ".join(
        str(value or "").casefold().split()
    )


def is_explicit_objective_activation_request(
    user_message: str | None,
) -> bool:
    text = _normalize(user_message)

    if not text:
        return False

    has_objective_noun = any(
        re.search(
            rf"\b{re.escape(noun)}\b",
            text,
        )
        for noun in _OBJECTIVE_NOUNS
    )

    if not has_objective_noun:
        return False

    has_action = any(
        marker in text
        for marker in _ACTION_MARKERS
    )

    if not has_action:
        return False

    capability_only = (
        any(
            marker in text
            for marker in _CAPABILITY_MARKERS
        )
        and not any(
            marker in text
            for marker in _DIRECT_REQUEST_OVERRIDE_MARKERS
        )
    )

    return not capability_only


def _json_from_text(text: str) -> dict[str, Any]:
    value = str(text or "").strip()

    if value.startswith("```"):
        value = re.sub(
            r"^```(?:json)?",
            "",
            value,
        ).strip()
        value = re.sub(
            r"```$",
            "",
            value,
        ).strip()

    start = value.find("{")
    end = value.rfind("}")

    if start >= 0 and end > start:
        value = value[start : end + 1]

    parsed = json.loads(value)

    if not isinstance(parsed, dict):
        raise ValueError(
            "Agent Core draft response is not an object"
        )

    return parsed


async def _draft_objective(
    *,
    user_message: str,
) -> ObjectiveDraft:
    claude = get_claude()

    response = await claude.messages.create(
        model=settings.UTILITY_LLM_MODEL,
        max_tokens=1_400,
        system=OBJECTIVE_DRAFT_PROMPT,
        messages=[
            {
                "role": "user",
                "content": user_message,
            }
        ],
    )

    text = (
        response.content[0].text
        if response.content
        else "{}"
    )

    parsed = _json_from_text(text)

    try:
        return ObjectiveDraft.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(
            "Invalid Agent Core objective draft"
        ) from exc


async def maybe_activate_from_chat(
    *,
    user_id: str,
    conversation_id: str,
    source_message_id: str,
    user_message: str,
) -> dict[str, Any]:
    if not is_explicit_objective_activation_request(
        user_message
    ):
        return {
            "detected": False,
            "created": False,
            "reason": "not_explicit_objective_request",
        }

    try:
        draft = await _draft_objective(
            user_message=user_message,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "agent_core: objective drafting failed: %s",
            exc,
        )
        return {
            "detected": True,
            "created": False,
            "reason": "draft_failed",
        }

    title = " ".join(
        str(draft.title or "").split()
    )
    desired_outcome = " ".join(
        str(draft.desired_outcome or "").split()
    )

    if (
        not draft.should_create
        or not title
        or not desired_outcome
        or len(draft.steps) < 2
    ):
        return {
            "detected": True,
            "created": False,
            "reason": "draft_rejected",
        }

    steps = [
        step.model_dump()
        for step in draft.steps
    ]

    try:
        created = await agent_core.create_objective_with_plan(
            user_id=user_id,
            title=title,
            desired_outcome=desired_outcome,
            steps=steps,
            creation_authority=(
                "explicit_user_request"
            ),
            priority=draft.priority,
            source_conversation_id=conversation_id,
            source_message_id=source_message_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "agent_core: durable objective creation failed"
        )
        return {
            "detected": True,
            "created": False,
            "reason": "persistence_failed",
            "error_type": type(exc).__name__,
        }

    return {
        "detected": True,
        "created": True,
        "reason": "explicit_user_request",
        "title": title,
        "objective_id": created.get("objective_id"),
        "plan_id": created.get("plan_id"),
    }
