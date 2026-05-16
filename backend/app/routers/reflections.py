"""Self-reflection endpoints.

  POST /reflections/generate
    Manually trigger reflection generation for the current user, looking
    back N days (default 14). Returns count of new reflections written.
    Synchronous — typical run is 1-3 seconds.

  GET /reflections
    List recent reflections for inspection / debugging.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.core.auth import get_current_user_id
from app.services import self_reflection
from app.services.supabase_client import get_supabase

router = APIRouter(prefix="/reflections", tags=["reflections"])


@router.post("/generate", status_code=status.HTTP_201_CREATED)
async def generate_reflections(
    lookback_days: int = Query(default=14, ge=3, le=60),
    user_id: str = Depends(get_current_user_id),
):
    count = await self_reflection.generate_weekly_reflection(
        user_id=user_id, lookback_days=lookback_days
    )
    return {"count": count, "lookback_days": lookback_days}


@router.get("")
async def list_reflections(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    result = (
        supabase.table("self_reflections")
        .select("id, content, kind, covers_period_start, covers_period_end, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []
