"""Legacy read-only memory compatibility API.

M35C3 retires all legacy mutation endpoints. Memory Review is the sole
user-facing mutation surface so PIN, confirmation provenance, archive
semantics, and correction history cannot be bypassed.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services.supabase_client import get_supabase

router = APIRouter(prefix="/memories", tags=["memories"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MemoryOut(BaseModel):
    id: str
    content: str
    kind: Literal["fact", "preference", "context", "plan"]
    source: Literal["auto", "manual"]
    created_at: datetime


class CreateMemoryIn(BaseModel):
    content: str = Field(min_length=3, max_length=500)
    kind: Literal["fact", "preference", "context", "plan"] = "fact"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _legacy_mutation_retired() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Legacy memory mutation endpoint retired; "
            "use /memory-review"
        ),
    )


@router.get("", response_model=list[MemoryOut])
async def list_memories(user_id: str = Depends(get_current_user_id)):
    """Return every memory for the current user, newest first."""
    supabase = get_supabase()
    result = (
        supabase.table("memories")
        .select("id, content, kind, source, created_at")
        .eq("user_id", user_id)
        .eq("superseded", False)
        .or_("archived.is.false,archived.is.null")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: CreateMemoryIn,
    user_id: str = Depends(get_current_user_id),
):
    """Retired: use PIN-gated Memory Review manual add."""
    _legacy_mutation_retired()


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Retired: use PIN-gated Memory Review archive."""
    _legacy_mutation_retired()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_memories(user_id: str = Depends(get_current_user_id)):
    """Retired: bulk hard-delete is no longer an allowed mutation path."""
    _legacy_mutation_retired()
