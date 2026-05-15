from app.services.supabase_client import get_supabase


async def get_user_state(user_id: str) -> dict:
    supabase = get_supabase()

    try:
        result = (
            supabase.table("user_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        # 🔥 HANDLE ALL EDGE CASES
        if result is None:
            return {}

        if not hasattr(result, "data"):
            return {}

        if result.data is None:
            return {}

        return result.data

    except Exception as e:
        print("USER_STATE ERROR:", str(e))
        return {}


async def save_user_state(
    user_id: str,
    mode: str,
    romantic_baseline: str,
    style: str = None,
    nickname: str = None,
    nickname_preference: str = None,
):
    supabase = get_supabase()

    try:
        payload = {
            "user_id": user_id,
            "mode": mode,
            "romantic_baseline": romantic_baseline,
        }

        if style is not None:
            payload["communication_style"] = style

        if nickname is not None:
            payload["nickname"] = nickname

        if nickname_preference is not None:
            payload["nickname_preference"] = nickname_preference

        supabase.table("user_state").upsert(payload).execute()

    except Exception as e:
        print("SAVE_STATE ERROR:", str(e))
