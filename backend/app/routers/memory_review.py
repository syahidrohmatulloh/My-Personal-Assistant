"""Memory Review API v1.

A safe control surface for reviewing and managing Aliyya's memories.

Design:
- Read grouped active + archived/superseded memories.
- Confirm memory by bumping last_confirmed_at.
- Forget memory by marking superseded=true, never delete.
- Edit memory by creating a new corrected version and superseding the old row.

This router does not touch companion mood, user mood, journal, or prompt logic.
"""

from __future__ import annotations
import asyncio

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services.embeddings import embed_document
from app.services.supabase_client import get_supabase, safe_execute
from app.services import memory_consolidation, memory_pin
from app.services.memory_quality import assess_memory_quality
from app.services.memory_quality_resolve import build_quality_resolve_plan
from app.services.memory_health_scheduler import get_memory_health_scheduler_status


router = APIRouter(prefix="/memory-review", tags=["memory_review"])


Category = Literal[
    "identity",
    "important_dates",
    "preferences",
    "relationships",
    "routines",
    "goals",
    "constraints",
    "other",
]


GROUP_ORDER = [
    "Identity",
    "Important Dates",
    "Preferences",
    "Projects & Goals",
    "Relationships",
    "Routines",
    "Constraints",
    "Behavioral Patterns",
    "Other",
]



class MemoryQualityResolveIn(BaseModel):
    action: Literal["keep_one_archive_rest", "archive_memory"]
    keep_memory_id: str | None = None
    archive_memory_ids: list[str] = Field(default_factory=list)
    issue_type: str | None = None
    pin: str = Field(min_length=6, max_length=6)


class MemoryEditIn(BaseModel):
    content: str = Field(min_length=3, max_length=500)
    category: Category | None = None
    structured_field: str | None = Field(default=None, max_length=80)
    structured_value: str | None = Field(default=None, max_length=300)
    pin: str = Field(min_length=6, max_length=6)


class MemoryPinIn(BaseModel):
    pin: str = Field(min_length=6, max_length=6)


class MemoryPinSetupIn(BaseModel):
    pin: str = Field(min_length=6, max_length=6)
    confirm_pin: str = Field(min_length=6, max_length=6)


class MemoryPinChangeIn(BaseModel):
    current_pin: str = Field(min_length=6, max_length=6)
    new_pin: str = Field(min_length=6, max_length=6)
    confirm_pin: str = Field(min_length=6, max_length=6)


class MemoryManualIn(BaseModel):
    content: str = Field(min_length=3, max_length=500)
    category: Category = "other"
    structured_field: str | None = Field(default=None, max_length=80)
    structured_value: str | None = Field(default=None, max_length=300)
    pin: str = Field(min_length=6, max_length=6)


class MemoryActionOut(BaseModel):
    ok: bool
    action: str
    memory_id: str | None = None
    new_memory_id: str | None = None


class CalendarCandidateOut(BaseModel):
    id: str
    content: str | None = None
    category: str | None = None
    structured_field: str | None = None
    structured_value: str | None = None
    due_date: str | None = None
    expires_at: str | None = None
    calendar_candidate: bool = False
    created_at: str | None = None
    source_conversation_id: str | None = None


@router.get("/pin/status")
async def memory_pin_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return await memory_pin.get_pin_status(user_id=user_id)


@router.post("/pin/setup")
async def memory_pin_setup(
    body: MemoryPinSetupIn,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return await memory_pin.setup_pin(
        user_id=user_id,
        pin=body.pin,
        confirm_pin=body.confirm_pin,
    )


@router.post("/pin/verify")
async def memory_pin_verify(
    body: MemoryPinIn,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    await memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)
    return {"ok": True}


@router.post("/pin/change")
async def memory_pin_change(
    body: MemoryPinChangeIn,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return await memory_pin.change_pin(
        user_id=user_id,
        current_pin=body.current_pin,
        new_pin=body.new_pin,
        confirm_pin=body.confirm_pin,
    )


@router.post("/pin/remove")
async def memory_pin_remove(
    body: MemoryPinIn,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return await memory_pin.remove_pin(user_id=user_id, pin=body.pin)



@router.post("/consolidate")
async def consolidate_memories(
    body: MemoryPinIn,
    days: int = 30,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Manually consolidate recent active memories into higher-level memories."""
    if days < 7 or days > 180:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="days must be between 7 and 180",
        )

    await memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)

    try:
        return await memory_consolidation.consolidate_and_persist(
            user_id=user_id,
            days=days,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to consolidate memories: {exc}",
        ) from exc


@router.get("")
async def list_memory_review(
    include_archived: bool = True,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return memories grouped for review UI."""
    query = (
        get_supabase()
        .table("memories")
        .select(
            "id, content, kind, category, structured_field, structured_value, "
            "confidence, source_priority, evidence, superseded, superseded_by, "
            "superseded_at, last_confirmed_at, created_at, "
            "source, source_conversation_id"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(500)
    )

    if not include_archived:
        query = query.eq("superseded", False)

    try:
        result = safe_execute(lambda _sb: query.execute())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load memories: {exc}",
        ) from exc

    rows = result.data or []
    return _build_review_payload(rows)



@router.get("/calendar-candidates")
async def list_calendar_candidates(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return memory-backed calendar candidates for review.

    This does not create calendar events. It only exposes scheduled/time-bound
    memories that have been marked as calendar candidates.
    """
    try:
        result = await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .select(
                    "id, content, category, structured_field, structured_value, "
                    "due_date, expires_at, calendar_candidate, created_at, "
                    "source_conversation_id, archived, superseded"
                )
                .eq("user_id", user_id)
                .eq("calendar_candidate", True)
                .eq("archived", False)
                .eq("superseded", False)
                .order("due_date", desc=False)
                .limit(100)
                .execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load calendar candidates: {exc}",
        ) from exc

    rows = result.data or []
    items = [_normalize_calendar_candidate(row) for row in rows]

    return {
        "items": items,
        "count": len(items),
    }


@router.post("/calendar-candidates/{memory_id}/dismiss")
async def dismiss_calendar_candidate(
    memory_id: str,
    body: MemoryPinIn,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Keep the memory, but remove it from calendar candidate review."""
    await memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)
    await _assert_memory_owner(memory_id=memory_id, user_id=user_id)

    now = _now_iso()
    try:
        await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .update(
                    {
                        "calendar_candidate": False,
                        "updated_at": now,
                    }
                )
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dismiss calendar candidate: {exc}",
        ) from exc

    return {"ok": True, "action": "calendar_candidate_dismissed", "memory_id": memory_id}


@router.post("/calendar-candidates/{memory_id}/archive")
async def archive_calendar_candidate(
    memory_id: str,
    body: MemoryPinIn,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Archive a calendar candidate memory."""
    await memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)
    await _assert_memory_owner(memory_id=memory_id, user_id=user_id)

    now = _now_iso()
    try:
        await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .update(
                    {
                        "archived": True,
                        "archived_by": "calendar_candidate_review",
                        "archived_at": now,
                        "updated_at": now,
                    }
                )
                .eq("id", memory_id)
                .eq("user_id", user_id)
                .execute()
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive calendar candidate: {exc}",
        ) from exc

    return {"ok": True, "action": "calendar_candidate_archived", "memory_id": memory_id}


@router.get("/quality")
async def memory_quality(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
    )

    return assess_memory_quality(result.data or [])


@router.get("/quality/scheduler/status")
async def memory_quality_scheduler_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return get_memory_health_scheduler_status(user_id=user_id)


@router.post("/quality/resolve")
async def resolve_memory_quality(
    body: MemoryQualityResolveIn,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    await memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)

    try:
        plan = build_quality_resolve_plan(
            action=body.action,
            keep_memory_id=body.keep_memory_id,
            archive_memory_ids=body.archive_memory_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("memories")
            .select("id,user_id,content,archived,superseded")
            .eq("user_id", user_id)
            .in_("id", plan.all_memory_ids)
            .execute()
        )
    )

    found_ids = {str(row.get("id")) for row in (existing.data or [])}
    missing_ids = [memory_id for memory_id in plan.all_memory_ids if memory_id not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory not found or not owned by user: {', '.join(missing_ids)}",
        )

    now = datetime.now(timezone.utc).isoformat()
    archive_reason = (
        "quality_resolve_archive"
        if plan.action == "archive_memory"
        else "quality_resolve_keep_one_archive_rest"
    )

    for memory_id in plan.archive_memory_ids:
        await asyncio.to_thread(
            lambda memory_id=memory_id: safe_execute(
                lambda sb: sb.table("memories")
                .update(
                    {
                        "archived": True,
                        "archived_by": archive_reason,
                        "archived_at": now,
                        "updated_at": now,
                    }
                )
                .eq("user_id", user_id)
                .eq("id", memory_id)
                .execute()
            )
        )

    if plan.keep_memory_id:
        await asyncio.to_thread(
            lambda: safe_execute(
                lambda sb: sb.table("memories")
                .update(
                    {
                        "archived": False,
                        "last_confirmed_at": now,
                        "updated_at": now,
                    }
                )
                .eq("user_id", user_id)
                .eq("id", plan.keep_memory_id)
                .execute()
            )
        )

    return {
        "ok": True,
        "action": plan.action,
        "kept_memory_id": plan.keep_memory_id,
        "archived_memory_ids": plan.archive_memory_ids,
        "archived": len(plan.archive_memory_ids),
    }


@router.post("/{memory_id}/confirm", response_model=MemoryActionOut)
async def confirm_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
) -> MemoryActionOut:
    """Mark an active memory as still true."""
    await _assert_memory_owner(memory_id=memory_id, user_id=user_id)

    now = _now_iso()
    try:
        safe_execute(
            lambda sb: sb.table("memories")
            .update({"last_confirmed_at": now})
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to confirm memory: {exc}",
        ) from exc

    return MemoryActionOut(ok=True, action="confirmed", memory_id=memory_id)


@router.post("/{memory_id}/forget", response_model=MemoryActionOut)
async def forget_memory(
    memory_id: str,
    body: MemoryPinIn,
    user_id: str = Depends(get_current_user_id),
) -> MemoryActionOut:
    """Archive/forget a memory by marking it superseded.

    We do not delete rows so audit trail and supersede chain remain safe.
    """
    await _assert_memory_owner(memory_id=memory_id, user_id=user_id)

    now = _now_iso()
    await memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)

    try:
        safe_execute(
            lambda sb: sb.table("memories")
            .update(
                {
                    "superseded": True,
                    "superseded_at": now,
                }
            )
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to forget memory: {exc}",
        ) from exc

    return MemoryActionOut(ok=True, action="forgotten", memory_id=memory_id)


@router.patch("/{memory_id}", response_model=MemoryActionOut)
async def edit_memory(
    memory_id: str,
    body: MemoryEditIn,
    user_id: str = Depends(get_current_user_id),
) -> MemoryActionOut:
    """Create a corrected version and supersede the old memory.

    This is safer than mutating the original row in-place because it preserves
    an audit trail and keeps superseded-chain semantics consistent.
    """
    await memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)

    old = await _assert_memory_owner(memory_id=memory_id, user_id=user_id)

    category = body.category or old.get("category") or "other"
    kind = _category_to_kind(category)
    now = _now_iso()

    try:
        embedding = await embed_document(body.content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to embed edited memory: {exc}",
        ) from exc

    new_row = {
        "user_id": user_id,
        "content": body.content,
        "kind": kind,
        "embedding": embedding,
        "source": "manual_review",
        "source_conversation_id": old.get("source_conversation_id"),
        "confidence": 1.0,
        "source_priority": "explicit_user_statement",
        "evidence": ["Edited by user in Memory Review"],
        "category": category,
        "structured_field": _clean_optional(body.structured_field)
        if body.structured_field is not None
        else old.get("structured_field"),
        "structured_value": _clean_optional(body.structured_value)
        if body.structured_value is not None
        else old.get("structured_value"),
        "superseded": False,
        "last_confirmed_at": now,
    }

    try:
        inserted = safe_execute(
            lambda sb: sb.table("memories").insert(new_row).execute()
        )
        new_rows = inserted.data or []
        if not new_rows:
            raise RuntimeError("insert returned no rows")

        new_id = new_rows[0]["id"]

        safe_execute(
            lambda sb: sb.table("memories")
            .update(
                {
                    "superseded": True,
                    "superseded_by": new_id,
                    "superseded_at": now,
                }
            )
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit memory: {exc}",
        ) from exc

    return MemoryActionOut(
        ok=True,
        action="edited",
        memory_id=memory_id,
        new_memory_id=new_id,
    )


async def _assert_memory_owner(*, memory_id: str, user_id: str) -> dict[str, Any]:
    try:
        result = safe_execute(
            lambda sb: sb.table("memories")
            .select(
                "id, user_id, content, kind, category, structured_field, "
                "structured_value, source_conversation_id, superseded"
            )
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read memory: {exc}",
        ) from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    return rows[0]


def _build_review_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    active: dict[str, list[dict[str, Any]]] = {name: [] for name in GROUP_ORDER}
    archived: dict[str, list[dict[str, Any]]] = {name: [] for name in GROUP_ORDER}

    for row in rows:
        item = _normalize_memory_row(row)
        group = _group_for_memory(item)
        target = archived if item.get("superseded") else active
        target.setdefault(group, []).append(item)

    return {
        "active": _drop_empty_groups(active),
        "archived": _drop_empty_groups(archived),
        "counts": {
            "active": sum(len(v) for v in active.values()),
            "archived": sum(len(v) for v in archived.values()),
            "total": len(rows),
        },
    }


def _normalize_calendar_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "content": row.get("content"),
        "category": row.get("category"),
        "structured_field": row.get("structured_field"),
        "structured_value": row.get("structured_value"),
        "due_date": str(row.get("due_date")) if row.get("due_date") else None,
        "expires_at": row.get("expires_at"),
        "calendar_candidate": bool(row.get("calendar_candidate")),
        "created_at": row.get("created_at"),
        "source_conversation_id": row.get("source_conversation_id"),
    }


def _normalize_memory_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence")
    if not isinstance(evidence, list):
        evidence = []

    return {
        "id": row.get("id"),
        "content": row.get("content"),
        "kind": row.get("kind"),
        "category": row.get("category") or "other",
        "group": _group_for_category(
            row.get("category"),
            row.get("structured_field"),
        ),
        "structured_field": row.get("structured_field"),
        "structured_value": row.get("structured_value"),
        "confidence": row.get("confidence"),
        "source_priority": row.get("source_priority"),
        "evidence": evidence[:3],
        "superseded": bool(row.get("superseded")),
        "superseded_by": row.get("superseded_by"),
        "superseded_at": row.get("superseded_at"),
        "last_confirmed_at": row.get("last_confirmed_at"),
        "created_at": row.get("created_at"),
        "source": row.get("source"),
        "source_conversation_id": row.get("source_conversation_id"),
    }


def _group_for_memory(row: dict[str, Any]) -> str:
    return _group_for_category(row.get("category"), row.get("structured_field"))


def _group_for_category(category: str | None, structured_field: str | None) -> str:
    field = (structured_field or "").strip().lower()
    cat = (category or "other").strip().lower()

    if field in {"birthday", "timezone", "nickname", "assistant_name", "name", "location"}:
        return "Identity"

    if cat == "identity":
        return "Identity"
    if cat == "important_dates":
        return "Important Dates"
    if cat == "preferences":
        if field.endswith("_style_under_frustration") or "support_style" in field:
            return "Behavioral Patterns"
        return "Preferences"
    if cat == "goals":
        return "Projects & Goals"
    if cat == "relationships":
        return "Relationships"
    if cat == "routines":
        return "Routines"
    if cat == "constraints":
        return "Constraints"
    return "Other"


def _drop_empty_groups(groups: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {k: v for k, v in groups.items() if v}


def _category_to_kind(category: str) -> str:
    if category == "preferences":
        return "preference"
    if category == "goals":
        return "plan"
    if category in {"constraints", "routines", "relationships"}:
        return "context"
    return "fact"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
