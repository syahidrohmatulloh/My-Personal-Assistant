"""Supabase Storage wrapper.

Used for file attachments (images, PDFs). We use the private `attachments`
bucket, accessed via service role. The frontend never talks to Storage
directly — every upload and download goes through the FastAPI backend so we
can enforce per-user access checks.
"""

from __future__ import annotations

import logging

from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)

ATTACHMENTS_BUCKET = "attachments"


def upload_bytes(*, path: str, data: bytes, content_type: str) -> None:
    """Upload raw bytes to the attachments bucket at the given path.

    Raises on failure — caller must handle. We don't catch here because a
    failed upload should surface to the user, not silently log.
    """
    supabase = get_supabase()
    supabase.storage.from_(ATTACHMENTS_BUCKET).upload(
        path=path,
        file=data,
        file_options={
            "content-type": content_type,
            "upsert": "false",
        },
    )


def download_bytes(path: str) -> bytes:
    """Download a file from the attachments bucket."""
    supabase = get_supabase()
    return supabase.storage.from_(ATTACHMENTS_BUCKET).download(path)


def delete_file(path: str) -> None:
    """Delete a single file from the bucket. Best-effort — logs on failure."""
    try:
        supabase = get_supabase()
        supabase.storage.from_(ATTACHMENTS_BUCKET).remove([path])
    except Exception as exc:
        log.warning("storage: delete failed for %s: %s", path, exc)
