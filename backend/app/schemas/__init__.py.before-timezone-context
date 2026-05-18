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


class ChatIn(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=20000)
    # IDs of attachments uploaded via /attachments/upload that this message
    # should reference. Each attachment must belong to the same user — the
    # chat router verifies before linking. Empty/missing = text-only message.
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    # Ephemeral app/browser state sent by the frontend on each request.
    # This is not stored as memory or message content. It helps the assistant
    # answer UI/time questions accurately, e.g. current background or timezone.
    ui_context: dict[str, Any] | None = None
