"""Voice endpoints."""
from __future__ import annotations

from io import BytesIO
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services.voice import (
    TranscriptionProviderError,
    VoiceConfigurationError,
    VoiceProviderError,
    generate_speech,
    transcribe_audio,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class TranscribeResponse(BaseModel):
    text: str
    confidence: float | None = None


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
        log.warning("voice speak: invalid request user=%s error=%s", user_id[:8], str(exc)[:160])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid speech request") from exc
    except VoiceConfigurationError as exc:
        log.warning("voice speak: configuration error user=%s error=%s", user_id[:8], str(exc)[:160])
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Voice is not configured yet",
        ) from exc
    except VoiceProviderError as exc:
        log.warning("voice speak: provider error user=%s error=%s", user_id[:8], str(exc)[:160])
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Voice generation is temporarily unavailable",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("voice speak: unexpected failure user=%s", user_id[:8])
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Voice generation failed unexpectedly",
        ) from exc

    return StreamingResponse(
        BytesIO(audio.content),
        media_type=audio.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )



@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    user_id: str = Depends(get_current_user_id),
):
    # user_id dependency is intentionally used for auth; transcription itself is stateless.
    _ = user_id

    try:
        content = await audio.read()
        result = await transcribe_audio(
            content=content,
            content_type=audio.content_type,
            language=language,
        )
        return TranscribeResponse(text=result.text, confidence=result.confidence)
    except ValueError as exc:
        log.warning("voice transcribe: invalid request user=%s error=%s", user_id[:8], str(exc)[:160])
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid audio request") from exc
    except VoiceConfigurationError as exc:
        log.warning("voice transcribe: configuration error user=%s error=%s", user_id[:8], str(exc)[:160])
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Voice transcription is not configured yet",
        ) from exc
    except TranscriptionProviderError as exc:
        log.warning("voice transcribe: provider error user=%s error=%s", user_id[:8], str(exc)[:160])
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Voice transcription is temporarily unavailable",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("voice transcribe: unexpected failure user=%s", user_id[:8])
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Transcription failed unexpectedly",
        ) from exc
