"""CRUD endpoints for memories.

The user-facing /memories page calls these to view, manually add, and delete
the facts Claude has remembered.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services.embeddings import embed_document
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


@router.get("", response_model=list[MemoryOut])
async def list_memories(user_id: str = Depends(get_current_user_id)):
    """Return every memory for the current user, newest first."""
    supabase = get_supabase()
    result = (
        supabase.table("memories")
        .select("id, content, kind, source, created_at")
        .eq("user_id", user_id)
        .eq("superseded", False)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: CreateMemoryIn,
    user_id: str = Depends(get_current_user_id),
):
    """Manually add a memory. The user types something they want remembered."""
    supabase = get_supabase()

    try:
        embedding = await embed_document(body.content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Embedding failed: {exc}"
        ) from exc

    result = (
        supabase.table("memories")
        .insert(
            {
                "user_id": user_id,
                "content": body.content,
                "kind": body.kind,
                "embedding": embedding,
                "source": "manual",
            }
        )
        .execute()
    )
    if not result.data:
        raise HTTPException(500, "Failed to create memory")
    return result.data[0]


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a single memory."""
    supabase = get_supabase()
    supabase.table("memories").delete().eq("id", memory_id).eq(
        "user_id", user_id
    ).execute()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_memories(user_id: str = Depends(get_current_user_id)):
    """Nuke all memories for this user. Use with care."""
    supabase = get_supabase()
    supabase.table("memories").delete().eq("user_id", user_id).execute()
