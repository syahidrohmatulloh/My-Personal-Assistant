from typing import Any, Literal, Optional
from pydantic import BaseModel, Field




class CompanionMoodContextIn(BaseModel):
    # Ephemeral frontend companion mood snapshot.
    # Extra fields are ignored by Pydantic default behavior.
    mood: str | None = Field(default=None, max_length=32)
    intensity: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = Field(default=None, max_length=160)
    mood_scores: dict[str, float] = Field(default_factory=dict)


class UIContextIn(BaseModel):
    # Ephemeral app/browser state sent by the frontend on each request.
    # This is not stored as memory or message content.
    # Unknown fields are ignored, preventing arbitrary prompt-context injection.
    timezone: str | None = Field(default=None, max_length=80)
    local_time_iso: str | None = Field(default=None, max_length=80)
    theme: Literal["light", "dark", "system"] | None = None
    background_style: str | None = Field(default=None, max_length=80)
    background_intensity: str | None = Field(default=None, max_length=32)
    background_motion: str | None = Field(default=None, max_length=32)
    background_mode: str | None = Field(default=None, max_length=32)
    client_platform: str | None = Field(default=None, max_length=80)
    current_page: str | None = Field(default=None, max_length=120)
    companion_mood: CompanionMoodContextIn | None = None


class ClientContextIn(BaseModel):
    # Browser-provided local time context for this chat turn.
    # This is prompt context only; it is not persisted.
    timezone: str | None = Field(default=None, max_length=80)
    local_time: str | None = Field(default=None, max_length=64)
    utc_offset_minutes: int | None = None
    locale: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default="browser", max_length=32)
    captured_at_utc: str | None = Field(default=None, max_length=64)

class ChatIn(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=20000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    client_context: ClientContextIn | None = None
    # Ephemeral app/browser state sent by the frontend on each request.
    # This is not stored as memory or message content.
    ui_context: UIContextIn | None = None
