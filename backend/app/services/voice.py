"""Voice text-to-speech service.

Provider credentials and voice selection are environment-driven.
No user name, assistant name, or personal data is hardcoded here.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

DEFAULT_TTS_TIMEOUT_SECONDS = 45.0


class VoiceConfigurationError(RuntimeError):
    """Raised when voice provider settings are incomplete."""


class VoiceProviderError(RuntimeError):
    """Raised when the voice provider cannot generate audio."""


class TranscriptionProviderError(RuntimeError):
    """Raised when the transcription provider cannot transcribe audio."""


@dataclass(frozen=True)
class SpeechAudio:
    content: bytes
    media_type: str = "audio/mpeg"


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    confidence: float | None = None


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise VoiceConfigurationError(f"{name} is not configured")
    return value


def _clean_text(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        raise ValueError("Text is required")
    if len(cleaned) > 4000:
        raise ValueError("Text is too long for speech generation")
    return cleaned


async def generate_speech(text: str) -> SpeechAudio:
    """Generate speech audio for assistant text.

    Currently uses ElevenLabs-compatible text-to-speech API.
    """
    cleaned_text = _clean_text(text)

    api_key = _required_env("ELEVENLABS_API_KEY")
    voice_id = _required_env("ELEVENLABS_VOICE_ID")
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip() or "eleven_multilingual_v2"
    base_url = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").strip().rstrip("/")

    url = f"{base_url}/v1/text-to-speech/{voice_id}"

    payload = {
        "text": cleaned_text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75,
            "style": 0.2,
            "use_speaker_boost": True,
        },
    }

    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TTS_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("voice provider network error: %s", exc)
        raise VoiceProviderError("Speech generation provider is unreachable") from exc

    if response.status_code == 401:
        raise VoiceProviderError("Speech generation failed because the voice API key is unauthorized")
    if response.status_code == 404:
        raise VoiceProviderError("Speech generation failed because the configured voice was not found")
    if response.status_code == 429:
        raise VoiceProviderError("Speech generation rate limit reached")
    if response.status_code >= 400:
        log.warning(
            "voice provider error status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        raise VoiceProviderError(f"Speech generation failed with provider status {response.status_code}")

    content_type = response.headers.get("content-type", "audio/mpeg").split(";")[0].strip() or "audio/mpeg"
    if not response.content:
        raise VoiceProviderError("Speech generation returned empty audio")

    return SpeechAudio(content=response.content, media_type=content_type)


def _clean_audio_upload(content: bytes, content_type: str | None) -> tuple[bytes, str]:
    if not content:
        raise ValueError("Audio file is required")

    max_bytes = 20 * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError("Audio file is too large")

    media_type = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    allowed_media_types = {
        "audio/webm",
        "audio/mp4",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "application/octet-stream",
    }

    if media_type not in allowed_media_types:
        raise ValueError("Unsupported audio format")

    return content, media_type


def _extract_deepgram_text(payload: dict) -> TranscriptionResult:
    alternatives = (
        payload.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [])
    )
    if not alternatives:
        return TranscriptionResult(text="", confidence=None)

    best = alternatives[0] or {}
    transcript = " ".join(str(best.get("transcript", "")).split())
    confidence = best.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_value = None

    return TranscriptionResult(text=transcript, confidence=confidence_value)


async def transcribe_audio(
    *,
    content: bytes,
    content_type: str | None,
    language: str | None = None,
) -> TranscriptionResult:
    """Transcribe user audio with Deepgram.

    This only converts the authenticated user's microphone audio into text.
    It does not identify speakers or infer identity.
    """
    audio, media_type = _clean_audio_upload(content, content_type)

    api_key = _required_env("DEEPGRAM_API_KEY")
    base_url = os.getenv("DEEPGRAM_BASE_URL", "https://api.deepgram.com").strip().rstrip("/")
    model = os.getenv("DEEPGRAM_MODEL_ID", "nova-3").strip() or "nova-3"

    params = {
        "model": model,
        "smart_format": "true",
        "punctuate": "true",
    }

    clean_language = (language or os.getenv("DEEPGRAM_LANGUAGE", "multi")).strip()
    if clean_language:
        params["language"] = clean_language

    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": media_type,
    }

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TTS_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{base_url}/v1/listen",
                params=params,
                content=audio,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        log.warning("transcription provider network error: %s", exc)
        raise TranscriptionProviderError("Transcription provider is unreachable") from exc

    if response.status_code == 401:
        raise TranscriptionProviderError("Transcription failed because the API key is unauthorized")
    if response.status_code == 402:
        raise TranscriptionProviderError("Transcription failed because billing or credits are required")
    if response.status_code == 429:
        raise TranscriptionProviderError("Transcription rate limit reached")
    if response.status_code >= 400:
        log.warning(
            "transcription provider error status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        raise TranscriptionProviderError(
            f"Transcription failed with provider status {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise TranscriptionProviderError("Transcription provider returned invalid JSON") from exc

    return _extract_deepgram_text(payload)
