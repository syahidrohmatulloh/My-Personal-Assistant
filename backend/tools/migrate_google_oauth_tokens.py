"""One-time migration of plaintext Google OAuth tokens."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.supabase_client import safe_execute
from app.services.token_crypto import (
    decrypt_token,
    encrypt_token,
    is_encrypted_token,
    require_token_encryption_configured,
)


def main() -> None:
    require_token_encryption_configured()

    result = safe_execute(
        lambda sb: sb.table("google_calendar_connections")
        .select("id,user_id,access_token,refresh_token")
        .limit(10000)
        .execute()
    )

    rows = list(result.data or [])
    migrated = 0
    already_encrypted = 0

    for row in rows:
        connection_id = str(row.get("id") or "").strip()
        if not connection_id:
            continue

        updates: dict[str, Any] = {}

        for field in ("access_token", "refresh_token"):
            raw_value = str(row.get(field) or "").strip()
            if not raw_value:
                continue

            if is_encrypted_token(raw_value):
                decrypt_token(raw_value)
                already_encrypted += 1
                continue

            updates[field] = encrypt_token(raw_value)

        if not updates:
            continue

        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        safe_execute(
            lambda sb, cid=connection_id, payload=updates: (
                sb.table("google_calendar_connections")
                .update(payload)
                .eq("id", cid)
                .execute()
            )
        )
        migrated += 1

    print(
        f"Scanned {len(rows)} connection rows; "
        f"migrated {migrated}; "
        f"encrypted token fields already present {already_encrypted}."
    )


if __name__ == "__main__":
    main()
