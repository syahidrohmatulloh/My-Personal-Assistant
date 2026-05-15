from typing import Optional
from pydantic import BaseModel


class ChatIn(BaseModel):
    conversation_id: str
    message: str
    client_id: Optional[str] = None
