"""Memory Safety Gate v1.

Protects sensitive memory actions with a 6-digit PIN.

PIN rules:
- exactly 6 digits
- never stored as plaintext
- stored as PBKDF2-HMAC-SHA256 hash
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.services.supabase_client import safe_execute


PBKDF2_ITERATIONS = 210_000
SALT_BYTES = 16
HASH_NAME = "sha256"
PIN_HASH_PREFIX = "pbkdf2_sha256"


def validate_pin_format(pin: str | None) -> str:
    value = str(pin or "").strip()
    if not (len(value) == 6 and value.isdigit()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memory PIN must be exactly 6 digits.",
        )
    return value


def hash_pin(pin: str) -> str:
    pin = validate_pin_format(pin)
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        HASH_NAME,
        pin.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"{PIN_HASH_PREFIX}${PBKDF2_ITERATIONS}"
        f"${salt.hex()}${digest.hex()}"
    )


def verify_pin_hash(pin: str, stored_hash: str | None) -> bool:
    pin = validate_pin_format(pin)
    if not stored_hash:
        return False

    try:
        prefix, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
        if prefix != PIN_HASH_PREFIX:
            return False

        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac(
        HASH_NAME,
        pin.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


async def get_pin_status(*, user_id: str) -> dict[str, Any]:
    row = await _get_settings(user_id=user_id)
    enabled = bool(row and row.get("memory_pin_enabled") and row.get("memory_pin_hash"))
    return {"memory_pin_enabled": enabled}


async def setup_pin(*, user_id: str, pin: str, confirm_pin: str) -> dict[str, Any]:
    pin = validate_pin_format(pin)
    confirm_pin = validate_pin_format(confirm_pin)

    if pin != confirm_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memory PIN confirmation does not match.",
        )

    existing = await _get_settings(user_id=user_id)
    if existing and existing.get("memory_pin_enabled") and existing.get("memory_pin_hash"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Memory PIN is already set.",
        )

    now = _now_iso()
    payload = {
        "user_id": user_id,
        "memory_pin_hash": hash_pin(pin),
        "memory_pin_enabled": True,
        "updated_at": now,
    }

    if not existing:
        payload["created_at"] = now

    await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("user_security_settings").upsert(payload).execute()
        )
    )

    return {"ok": True, "memory_pin_enabled": True}


async def change_pin(
    *,
    user_id: str,
    current_pin: str,
    new_pin: str,
    confirm_pin: str,
) -> dict[str, Any]:
    await require_valid_pin(user_id=user_id, pin=current_pin)

    new_pin = validate_pin_format(new_pin)
    confirm_pin = validate_pin_format(confirm_pin)

    if new_pin != confirm_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New Memory PIN confirmation does not match.",
        )

    await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("user_security_settings")
            .update(
                {
                    "memory_pin_hash": hash_pin(new_pin),
                    "memory_pin_enabled": True,
                    "updated_at": _now_iso(),
                }
            )
            .eq("user_id", user_id)
            .execute()
        )
    )

    return {"ok": True, "memory_pin_enabled": True}


async def remove_pin(*, user_id: str, pin: str) -> dict[str, Any]:
    """Memory PIN removal is intentionally disabled.

    Memory actions must remain protected once the PIN system is configured.
    Users may change the PIN, but cannot remove/disable protection.
    """
    validate_pin_format(pin)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Memory PIN protection cannot be removed. You can change your PIN instead.",
    )


async def require_valid_pin(*, user_id: str, pin: str | None) -> None:
    pin = validate_pin_format(pin)
    row = await _get_settings(user_id=user_id)

    if not row or not row.get("memory_pin_enabled") or not row.get("memory_pin_hash"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Memory PIN is not set. Please set up a 6-digit Memory PIN first.",
        )

    if not verify_pin_hash(pin, row.get("memory_pin_hash")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Incorrect Memory PIN.",
        )


async def _get_settings(*, user_id: str) -> dict[str, Any] | None:
    result = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("user_security_settings")
            .select("user_id, memory_pin_hash, memory_pin_enabled")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    )

    rows = result.data or []
    return rows[0] if rows else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
