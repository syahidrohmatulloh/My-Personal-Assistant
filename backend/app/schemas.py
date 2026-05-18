from typing import Any, Optional
from pydantic import BaseModel, Field




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
    ui_context: Optional[dict[str, Any]] = None
