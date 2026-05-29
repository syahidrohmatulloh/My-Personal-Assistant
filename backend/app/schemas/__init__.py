"""Request and response schemas.

Pydantic models double as input validation and OpenAPI docs. Anything sent to
or from the API should be defined here so invalid payloads fail at the door
with a clear 422 instead of crashing the handler.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Conversations ---


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    # Null = Default style (baseline behavior). Otherwise references a row
    # in style_profiles.
    style_profile_id: str | None = None


class CreateConversationIn(BaseModel):
    title: str = Field(default="New chat", max_length=200)
    # Optional: link a saved style profile. The chat router reads this and
    # injects a style directive into the system prompt for this conversation.
    style_profile_id: str | None = None


# --- Messages ---


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


# --- Chat ---

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
    # IDs of attachments uploaded via /attachments/upload that this message
    # should reference. Each attachment must belong to the same user — the
    # chat router verifies before linking. Empty/missing = text-only message.
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    client_context: ClientContextIn | None = None
    # Ephemeral app/browser state sent by the frontend on each request.
    # This is not stored as memory or message content. It helps the assistant
    # answer UI/time questions accurately, e.g. current background or timezone.
    ui_context: UIContextIn | None = None
