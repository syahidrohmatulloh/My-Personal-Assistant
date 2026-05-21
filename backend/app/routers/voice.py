"""Voice endpoints."""
from __future__ import annotations

from io import BytesIO
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services.voice import VoiceConfigurationError, VoiceProviderError, generate_speech

log = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/speak")
async def speak(
    body: SpeakRequest,
    user_id: str = Depends(get_current_user_id),
):
    # user_id dependency is intentionally used for auth; speech generation itself is stateless.
    _ = user_id

    try:
        audio = await generate_speech(body.text)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except VoiceConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except VoiceProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.error("speech generation failed unexpectedly: %s", exc, exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Speech generation failed unexpectedly",
        ) from exc

    return StreamingResponse(
        BytesIO(audio.content),
        media_type=audio.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
