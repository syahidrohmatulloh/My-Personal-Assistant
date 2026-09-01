from __future__ import annotations

import asyncio
import logging

from app.services import temporal_calendar_policy
from app.services.supabase_client import safe_execute


log = logging.getLogger(__name__)


def should_hard_gate_calendar_candidate(
    user_message: str | None,
) -> bool:
    """Gate only turns semantically eligible for Calendar handling."""

    assessment = (
        temporal_calendar_policy
        .assess_calendar_semantics(
            user_message
        )
    )

    return (
        temporal_calendar_policy
        .requires_calendar_handling(
            assessment
        )
    )

def render_calendar_hard_gate_clarification(
    *,
    address_term: str | None = None,
    user_message: str | None = None,
    semantic_assessment=None,
) -> str:
    term = clean_calendar_address_term(
        address_term
    )
    prefix = f"{term}, " if term else ""

    assessment = semantic_assessment
    if assessment is None:
        assessment = (
            temporal_calendar_policy
            .assess_calendar_semantics(
                user_message
            )
        )

    if (
        assessment.persistence_target
        == "reminder"
    ):
        return (
            f"{prefix}aku belum punya detail yang cukup "
            "untuk reminder itu. Kapan kamu mau diingatkan?"
        )

    if (
        assessment.persistence_target
        == "calendar"
    ):
        return (
            f"{prefix}aku belum punya detail yang cukup "
            "untuk memasukkannya ke Calendar. "
            "Acara apa dan kapan waktunya?"
        )

    return (
        f"{prefix}aku belum mau menganggap ini jadwal dulu. "
        "Kamu sedang cerita/rencana saja, atau mau ini "
        "dijadikan agenda di Calendar?"
    )

async def load_calendar_address_term(
    *,
    user_id: str,
    assistant_mode: str = "life_companion",
) -> str:
    """Load a user-preferred address term for deterministic receipts.

    No fallback nickname is hardcoded. If the user has not explicitly stored a
    preferred address/name/nickname, deterministic receipts simply omit it.
    """
    if assistant_mode == "chief_of_staff":
        return ""

    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .select("structured_field, structured_value, content, updated_at")
                .eq("user_id", user_id)
                .eq("archived", False)
                .eq("superseded", False)
                .in_(
                    "structured_field",
                    ["preferred_address", "preferred_name", "nickname"],
                )
                .order("updated_at", desc=True)
                .limit(8)
                .execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "chat: calendar address term lookup failed user=%s error_type=%s",
            user_id[:8],
            type(exc).__name__,
        )
        return ""

    for row in list(result.data or []):
        value = clean_calendar_address_term(row.get("structured_value"))
        if value:
            return value

    return ""

def clean_calendar_address_term(value) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split()).strip()
    text = text.strip(" .,:;!?'\"")
    if not text:
        return ""

    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in (
            "jangan panggil",
            "do not call",
            "don't call",
            "disallowed",
        )
    ):
        return ""

    if len(text) > 40:
        return ""

    return text
