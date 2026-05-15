"""Verify the Supabase JWT and pull out the user's UUID.

Supabase issues ES256-signed JWTs (asymmetric, since 2024). We verify them by
fetching Supabase's public keys from its JWKS endpoint and checking the
signature.

PyJWKClient caches the keys in memory, so we hit the JWKS endpoint at most
once per key rotation — not on every request.
"""

from fastapi import Header, HTTPException, status
import jwt
from jwt import PyJWKClient

from app.config import settings

# Supabase publishes its public keys at this stable URL.
JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks_client = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = authorization.removeprefix("Bearer ").strip()

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256", "RS256", "HS256"],  # support all Supabase variants
            audience="authenticated",
        )
    except jwt.InvalidTokenError as exc:
        print(f"🔴 JWT VERIFICATION FAILED: {exc}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no user id",
        )
    return user_id