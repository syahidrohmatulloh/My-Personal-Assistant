"""M31E-FINAL foreground Calendar executive orchestration.

This service sequences existing authoritative Calendar services.

It does not implement Calendar parsing, confirmation classification,
database mutation, or Google provider behavior itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services import (
    calendar_candidate_extractor,
    calendar_confirmation_actions,
    calendar_draft_actions,
    chat_calendar_helpers,
    temporal_calendar_policy,
)


@dataclass(frozen=True)
class CalendarTurnExecution:
    is_draft_action_turn: bool
    action_result: dict[str, Any] | None
    confirmation_result: dict[str, Any] | None
    action_snapshot_dirty: bool
    receipt_text: str | None = None
    receipt_source: str | None = None
    receipt_snapshot_dirty: bool = False


async def execute_calendar_turn(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    client_context: Any,
    recent_messages: list[dict[str, Any]],
    assistant_mode: str,
    logger: logging.Logger | None = None,
) -> CalendarTurnExecution:
    """Run authoritative foreground Calendar routing before model generation."""

    is_calendar_draft_action_turn = (
        calendar_draft_actions
        .is_calendar_draft_action_request(
            user_message
        )
    )

    calendar_semantic_assessment = (
        temporal_calendar_policy
        .assess_calendar_semantics(
            user_message
        )
    )

    calendar_action_result: (
        dict[str, Any] | None
    ) = None

    if is_calendar_draft_action_turn:
        try:
            calendar_action_result = (
                await calendar_draft_actions
                .apply_chat_calendar_draft_action(
                    user_id=user_id,
                    conversation_id=(
                        conversation_id
                    ),
                    user_message=user_message,
                    client_context=(
                        client_context
                    ),
                    recent_messages=(
                        recent_messages
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            if logger is not None:
                logger.warning(
                    "chat: authoritative calendar "
                    "action failed "
                    "user=%s conversation=%s "
                    "error_type=%s",
                    user_id[:8],
                    conversation_id[:8],
                    type(exc).__name__,
                )

            calendar_action_result = {
                "attempted": True,
                "success": False,
                "updated": False,
                "deleted": False,
                "action": "unknown",
                "source": "unknown",
                "reason": (
                    "calendar_action_exception"
                ),
            }

    calendar_action_success = (
        calendar_draft_actions
        .calendar_action_succeeded(
            calendar_action_result
        )
    )

    calendar_action_reason = str(
        (
            calendar_action_result
            or {}
        ).get(
            "reason"
        )
        or ""
    )

    calendar_action_snapshot_dirty = bool(
        calendar_action_success
        or calendar_action_reason
        in {
            (
                "local_update_after_"
                "google_patch_failed"
            ),
            (
                "local_archive_after_"
                "google_delete_failed"
            ),
        }
    )

    calendar_address_term = (
        await chat_calendar_helpers
        .load_calendar_address_term(
            user_id=user_id,
            assistant_mode=(
                assistant_mode
            ),
        )
    )

    calendar_action_receipt = (
        calendar_draft_actions
        .render_calendar_action_user_receipt(
            calendar_action_result,
            address_term=(
                calendar_address_term
            ),
        )
    )

    if (
        is_calendar_draft_action_turn
        and calendar_action_receipt
    ):
        return CalendarTurnExecution(
            is_draft_action_turn=True,
            action_result=(
                calendar_action_result
            ),
            confirmation_result=None,
            action_snapshot_dirty=(
                calendar_action_snapshot_dirty
            ),
            receipt_text=(
                calendar_action_receipt
            ),
            receipt_source=(
                "deterministic_calendar_action"
            ),
            receipt_snapshot_dirty=(
                calendar_action_snapshot_dirty
            ),
        )

    calendar_confirmation_result: (
        dict[str, Any] | None
    ) = None

    if not is_calendar_draft_action_turn:
        calendar_confirmation_relevant = (
            temporal_calendar_policy
            .should_check_pending_confirmation(
                user_message
            )
        )
    else:
        calendar_confirmation_relevant = False

    if calendar_confirmation_relevant:
        calendar_confirmation_result = (
            await calendar_confirmation_actions
            .apply_calendar_confirmation_decision(
                user_id=user_id,
                conversation_id=(
                    conversation_id
                ),
                user_message=user_message,
                client_context=(
                    client_context
                ),
                recent_messages=(
                    recent_messages
                ),
            )
        )

        calendar_confirmation_receipt = (
            calendar_confirmation_actions
            .render_calendar_confirmation_user_receipt(
                calendar_confirmation_result,
                address_term=(
                    calendar_address_term
                ),
            )
        )

        if calendar_confirmation_receipt:
            return CalendarTurnExecution(
                is_draft_action_turn=False,
                action_result=(
                    calendar_action_result
                ),
                confirmation_result=(
                    calendar_confirmation_result
                ),
                action_snapshot_dirty=(
                    calendar_action_snapshot_dirty
                ),
                receipt_text=(
                    calendar_confirmation_receipt
                ),
                receipt_source=(
                    "deterministic_"
                    "calendar_confirmation"
                ),
                receipt_snapshot_dirty=bool(
                    (
                        calendar_confirmation_result
                        or {}
                    ).get(
                        "executed"
                    )
                ),
            )

    calendar_candidate_hard_gate = (
        not is_calendar_draft_action_turn
        and not calendar_draft_actions
        .is_google_calendar_create_request(
            user_message
        )
        and temporal_calendar_policy
        .requires_calendar_handling(
            calendar_semantic_assessment
        )
        and chat_calendar_helpers
        .should_hard_gate_calendar_candidate(
            user_message
        )
    )

    if calendar_candidate_hard_gate:
        calendar_candidate_result = (
            await calendar_candidate_extractor
            .extract_and_persist(
                user_id=user_id,
                conversation_id=(
                    conversation_id
                ),
                user_message=user_message,
                client_context=(
                    client_context
                ),
                recent_messages=(
                    recent_messages
                ),
            )
        )

        calendar_candidate_preview = (
            calendar_candidate_extractor
            .render_calendar_candidate_preview(
                calendar_candidate_result,
                address_term=(
                    calendar_address_term
                ),
            )
        )

        if not calendar_candidate_preview:
            calendar_candidate_preview = (
                chat_calendar_helpers
                .render_calendar_hard_gate_clarification(
                    address_term=(
                        calendar_address_term
                    ),
                    user_message=user_message,
                    semantic_assessment=(
                        calendar_semantic_assessment
                    ),
                )
            )

        receipt_source = (
            "deterministic_candidate_preview"
            if calendar_candidate_result.get(
                "candidate"
            )
            else (
                "deterministic_"
                "calendar_clarification"
            )
        )

        return CalendarTurnExecution(
            is_draft_action_turn=False,
            action_result=(
                calendar_action_result
            ),
            confirmation_result=(
                calendar_confirmation_result
            ),
            action_snapshot_dirty=(
                calendar_action_snapshot_dirty
            ),
            receipt_text=(
                calendar_candidate_preview
            ),
            receipt_source=receipt_source,
            receipt_snapshot_dirty=bool(
                calendar_candidate_result.get(
                    "saved"
                )
            ),
        )

    if (
        not is_calendar_draft_action_turn
        and calendar_draft_actions
        .is_google_calendar_create_request(
            user_message
        )
    ):
        google_create_result = (
            await calendar_draft_actions
            .create_google_calendar_event_from_chat(
                user_id=user_id,
                conversation_id=(
                    conversation_id
                ),
                user_message=user_message,
                client_context=(
                    client_context
                ),
                recent_messages=(
                    recent_messages
                ),
            )
        )

        if str(
            google_create_result.get(
                "reason"
            )
            or ""
        ) in {
            "no_confident_draft",
            "missing_required_fields",
        }:
            latest_local_google_sync_result = (
                await calendar_draft_actions
                .sync_latest_confirmed_local_event_to_google_from_chat(
                    user_id=user_id,
                    conversation_id=(
                        conversation_id
                    ),
                    user_message=(
                        user_message
                    ),
                )
            )

            latest_local_google_sync_receipt = (
                calendar_draft_actions
                .render_google_calendar_create_user_receipt(
                    latest_local_google_sync_result,
                    address_term=(
                        calendar_address_term
                    ),
                )
            )

            if (
                latest_local_google_sync_receipt
            ):
                google_create_result = (
                    latest_local_google_sync_result
                )

        google_create_receipt = (
            calendar_draft_actions
            .render_google_calendar_create_user_receipt(
                google_create_result,
                address_term=(
                    calendar_address_term
                ),
            )
        )

        if google_create_receipt:
            return CalendarTurnExecution(
                is_draft_action_turn=False,
                action_result=(
                    calendar_action_result
                ),
                confirmation_result=(
                    calendar_confirmation_result
                ),
                action_snapshot_dirty=(
                    calendar_action_snapshot_dirty
                ),
                receipt_text=(
                    google_create_receipt
                ),
                receipt_source=(
                    "deterministic_"
                    "google_calendar_create"
                ),
                receipt_snapshot_dirty=bool(
                    google_create_result.get(
                        "google_event_id"
                    )
                ),
            )

    return CalendarTurnExecution(
        is_draft_action_turn=(
            is_calendar_draft_action_turn
        ),
        action_result=(
            calendar_action_result
        ),
        confirmation_result=(
            calendar_confirmation_result
        ),
        action_snapshot_dirty=(
            calendar_action_snapshot_dirty
        ),
    )
