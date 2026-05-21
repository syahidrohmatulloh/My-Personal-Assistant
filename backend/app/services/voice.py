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


@dataclass(frozen=True)
class SpeechAudio:
    content: bytes
    media_type: str = "audio/mpeg"


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
