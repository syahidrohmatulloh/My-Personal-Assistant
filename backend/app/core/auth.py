"""Verify the Supabase JWT and pull out the user's UUID.

Supabase issues ES256-signed JWTs (asymmetric, since 2024). We verify them by
fetching Supabase's public keys from its JWKS endpoint and checking the
signature.

PyJWKClient caches the keys in memory, so we hit the JWKS endpoint at most
once per key rotation — not on every request.
"""

import logging
from fastapi import Header, HTTPException, status
import jwt
from jwt import PyJWKClient

from app.config import settings

log = logging.getLogger(__name__)
JWT_AUDIENCE = settings.SUPABASE_JWT_AUDIENCE

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
            audience=JWT_AUDIENCE,
        )
    except jwt.InvalidTokenError as exc:
        # Log full exception for debugging, but return a generic message to client.
        # Including the raw error in the response could leak internals (algorithm
        # mismatch, expired claims, etc.) to anyone hitting the endpoint.
        log.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        log.warning("JWT verified but missing 'sub' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no user id",
        )
    return user_id
