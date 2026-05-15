"""Supabase client used from the FastAPI backend.

We use the service role key, which bypasses Row-Level Security. This is fine
because the backend has already verified the JWT and knows the user_id — we
then filter every query by that user_id ourselves. RLS still protects against
the frontend talking to Supabase directly (which it does for auth).

Important: never expose SUPABASE_SERVICE_ROLE_KEY to the frontend. Only the
anon key goes in the browser.
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
