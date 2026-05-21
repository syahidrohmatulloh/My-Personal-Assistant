"""Attachment service.

Responsibilities:
  1. Validate uploaded file: size, real MIME (magic bytes — NOT extension)
  2. Persist file to Supabase Storage + metadata row
  3. Fetch attachment as Claude content block (base64 wrap + correct media_type)
  4. Auto-describe images via Haiku and store as memory (so assistant "remembers")

We detect MIME from magic bytes rather than trusting the filename. Why: per
upstream Anthropic bug reports, mismatched media_type causes API 400 errors.
A png renamed to .jpg would otherwise blow up the chat router on send.
"""

from __future__ import annotations

import base64
import logging
import uuid as _uuid
from typing import Literal

from app.services import memory, storage
from app.services.claude import get_claude
from app.services.supabase_client import get_supabase
from app.services.visual_memory_rules import decide_visual_memory

log = logging.getLogger(__name__)

# Caps (raw file size before any compression).
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_PDF_BYTES = 10 * 1024 * 1024    # 10 MB

# Magic-byte signatures for the file types we support.
# Source: https://en.wikipedia.org/wiki/List_of_file_signatures
_SIGNATURES: list[tuple[bytes, str, Literal["image", "document"]]] = [
    (b"\xff\xd8\xff", "image/jpeg", "image"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "image"),
    (b"GIF87a", "image/gif", "image"),
    (b"GIF89a", "image/gif", "image"),
    (b"RIFF", "image/webp", "image"),  # WebP starts with RIFF, then WEBP at offset 8 — we accept RIFF
    (b"%PDF-", "application/pdf", "document"),
]


def detect_media_type(
    data: bytes,
) -> tuple[str, Literal["image", "document"]] | None:
    """Inspect magic bytes to determine (media_type, kind).

    Returns None if not a supported format. Caller must reject the upload.
    """
    if not data:
        return None
    for sig, media_type, kind in _SIGNATURES:
        if data.startswith(sig):
            # WebP needs a second check — "RIFF....WEBP" at offset 8.
            if media_type == "image/webp" and (len(data) < 12 or data[8:12] != b"WEBP"):
                continue
            return media_type, kind
    return None


def validate_size(*, data: bytes, kind: Literal["image", "document"]) -> str | None:
    """Return None if valid, an error string if too large."""
    size = len(data)
    if kind == "image" and size > MAX_IMAGE_BYTES:
        return f"Image too large: {size // 1024 // 1024} MB (max {MAX_IMAGE_BYTES // 1024 // 1024} MB)"
    if kind == "document" and size > MAX_PDF_BYTES:
        return f"PDF too large: {size // 1024 // 1024} MB (max {MAX_PDF_BYTES // 1024 // 1024} MB)"
    return None


def save_pending(
    *,
    user_id: str,
    data: bytes,
    original_filename: str,
    media_type: str,
    kind: Literal["image", "document"],
) -> dict:
    """Upload to Storage + insert pending metadata row. Returns the row dict.

    "Pending" = no message_id yet. The chat router links it on send.
    """
    # Path layout: <user_id>/<random>.<ext>
    ext = _ext_for(media_type)
    storage_path = f"{user_id}/{_uuid.uuid4()}{ext}"

    storage.upload_bytes(path=storage_path, data=data, content_type=media_type)

    supabase = get_supabase()
    row = (
        supabase.table("message_attachments")
        .insert(
            {
                "user_id": user_id,
                "storage_path": storage_path,
                "original_filename": original_filename[:200],
                "media_type": media_type,
                "kind": kind,
                "size_bytes": len(data),
            }
        )
        .execute()
    )
    return row.data[0]


def fetch_for_user(*, user_id: str, attachment_ids: list[str]) -> list[dict]:
    """Return attachment metadata rows belonging to the user. Filters out
    anything that doesn't belong — silent skip, not error, so a stale ID
    doesn't break the chat send."""
    if not attachment_ids:
        return []
    supabase = get_supabase()
    rows = (
        supabase.table("message_attachments")
        .select("id, storage_path, media_type, kind, original_filename, description")
        .in_("id", attachment_ids)
        .eq("user_id", user_id)
        .execute()
    )
    return rows.data or []


def link_to_message(
    *, user_id: str, attachment_ids: list[str], message_id: str
) -> None:
    """Attach pending uploads to a message. Filters by user_id for safety."""
    if not attachment_ids:
        return
    supabase = get_supabase()
    supabase.table("message_attachments").update({"message_id": message_id}).in_(
        "id", attachment_ids
    ).eq("user_id", user_id).execute()


def to_claude_content_block(*, row: dict) -> dict | None:
    """Convert one attachment metadata row into a Claude content block.

    Downloads the bytes from Storage, base64-encodes, wraps as image or
    document block depending on `kind`.

    Returns None on download failure (logged) so the caller can continue
    with remaining attachments.
    """
    try:
        data = storage.download_bytes(row["storage_path"])
    except Exception as exc:
        log.warning(
            "attachment: download failed for %s: %s", row["storage_path"], exc
        )
        return None

    encoded = base64.standard_b64encode(data).decode("ascii")

    if row["kind"] == "image":
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": row["media_type"],
                "data": encoded,
            },
        }
    else:  # document
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": row["media_type"],
                "data": encoded,
            },
        }


# ---------------------------------------------------------------------------
# Auto-describe images: lets the assistant "remember" images via memories table
# ---------------------------------------------------------------------------

DESCRIBE_PROMPT = """Describe this image in one or two short sentences, from the \
perspective of someone who needs to recall it months from now.

Focus on:
- What is happening / what is shown
- Where (if discernible)
- People involved (use generic descriptors like "the user" or "two people" — \
NEVER attempt to identify specific individuals)
- Anything specific that would help recall (mood, time of day, occasion)

Avoid speculation. If you can't tell, leave it out. Write naturally in English.
Output ONLY the description — no preamble."""


async def describe_image_background(*, attachment_id: str, user_id: str) -> None:
    """Background task: ask Haiku to describe an image, store as memory.

    Runs after upload succeeds. Failures are logged, not raised.
    """
    supabase = get_supabase()
    row = (
        supabase.table("message_attachments")
        .select("id, storage_path, media_type, kind")
        .eq("id", attachment_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not row or not row.data or row.data["kind"] != "image":
        return

    block = to_claude_content_block(row=row.data)
    if not block:
        return

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=200,
            system=DESCRIBE_PROMPT,
            messages=[{"role": "user", "content": [block]}],
        )
        text_block = next((b for b in response.content if b.type == "text"), None)
        if not text_block:
            return
        description = text_block.text.strip()
        if not description:
            return
    except Exception as exc:
        log.warning("attachment: describe failed: %s", exc)
        return

    # Persist description on the attachment row + as a semantic memory.
    supabase.table("message_attachments").update({"description": description}).eq(
        "id", attachment_id
    ).execute()

    # Decide whether this image should become durable memory.
    #
    # Screenshots/debug/UI images are useful in the current conversation, but
    # should not pollute long-term memory. Personal/travel/food/place photos can
    # become structured visual memory candidates.
    visual_decision = decide_visual_memory(description)

    if visual_decision and visual_decision.should_store:
        try:
            from app.services.embeddings import embed_document  # local to avoid circular

            embedding = await embed_document(visual_decision.content)
            supabase.table("memories").insert(
                {
                    "user_id": user_id,
                    "content": visual_decision.content,
                    "kind": visual_decision.kind,
                    "category": visual_decision.category,
                    "structured_field": visual_decision.structured_field,
                    "structured_value": visual_decision.structured_value,
                    "confidence": visual_decision.confidence,
                    "embedding": embedding,
                    "source": "auto",
                    "source_priority": f"visual_attachment:{visual_decision.reason}",
                }
            ).execute()
        except Exception as exc:
            log.warning("attachment: memory save failed: %s", exc)
    else:
        log.info(
            "attachment: skipped visual memory for image %s reason=%s",
            attachment_id[:8],
            visual_decision.reason if visual_decision else "empty_description",
        )

    log.info(
        "attachment: described image %s for user=%s: %s",
        attachment_id[:8],
        user_id[:8],
        description[:80],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ext_for(media_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }.get(media_type, "")
