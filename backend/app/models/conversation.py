from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant"]


class ConversationMessage(BaseModel):
    role: MessageRole
    content: str
    created_at: datetime
    citation_ids: list[str] = Field(default_factory=list)


class Conversation(BaseModel):
    id: str
    owner_id: str | None = None
    messages: list[ConversationMessage] = Field(default_factory=list)
