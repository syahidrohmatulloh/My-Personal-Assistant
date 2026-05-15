"""Request and response schemas.

Pydantic models double as input validation and OpenAPI docs. Anything sent to
or from the API should be defined here so invalid payloads fail at the door
with a clear 422 instead of crashing the handler.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --- Conversations ---


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class CreateConversationIn(BaseModel):
    title: str = Field(default="New chat", max_length=200)


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
