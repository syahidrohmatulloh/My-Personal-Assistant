from typing import Any, Optional
from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=20000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    # Ephemeral app/browser state sent by the frontend on each request.
    # This is not stored as memory or message content.
    ui_context: Optional[dict[str, Any]] = None
