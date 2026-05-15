from app.services.supabase_client import get_supabase


async def get_user_state(user_id: str) -> dict:
    supabase = get_supabase()

    result = (
        supabase.table("user_state")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    return result.data or {}


async def save_user_state(user_id: str, mode: str, romantic_baseline: str):
    supabase = get_supabase()

    supabase.table("user_state").upsert(
        {
            "user_id": user_id,
            "mode": mode,
            "romantic_baseline": romantic_baseline,
        }
    ).execute()
