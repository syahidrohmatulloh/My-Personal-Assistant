"""Attachment upload endpoint.

POST /attachments/upload (multipart/form-data, field name: "file")
  -> { id, kind, media_type, original_filename, size_bytes, description: null }

Limits + validation enforced server-side. Frontend pre-resizes images via
Canvas API to <1MB but we don't trust that — we re-validate here.

After successful upload, schedules a background task to ask Haiku to
describe the image. The description gets persisted on the attachment row
AND inserted as a semantic memory for future cross-chat recall.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from app.core.auth import get_current_user_id
from app.services import attachments
from app.services.safe_background import add_safe_background_task

log = logging.getLogger(__name__)
router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    if not file.filename:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Missing filename"
        )

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    # Detect real MIME from magic bytes — ignore client-supplied content_type
    # and extension. Mismatches break Claude vision (per upstream bug reports).
    detection = attachments.detect_media_type(data)
    if not detection:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Unsupported file type. Accepted: JPEG, PNG, GIF, WebP, PDF",
        )
    media_type, kind = detection

    # Size check.
    err = attachments.validate_size(data=data, kind=kind)
    if err:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, err)

    try:
        row = attachments.save_pending(
            user_id=user_id,
            data=data,
            original_filename=file.filename,
            media_type=media_type,
            kind=kind,
        )
    except Exception as exc:
        log.exception(
            "attachment upload failed user=%s filename=%s",
            user_id[:8],
            file.filename[:120],
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Upload failed"
        ) from exc

    # For images: schedule auto-description in background. PDF descriptions
    # are skipped — full document analysis happens when the user actually
    # sends the chat message that references the PDF.
    if kind == "image":
        add_safe_background_task(
            background_tasks,
            attachments.describe_image_background,
            attachment_id=row["id"],
            user_id=user_id,
        )

    return {
        "id": row["id"],
        "kind": row["kind"],
        "media_type": row["media_type"],
        "original_filename": row["original_filename"],
        "size_bytes": row["size_bytes"],
    }
