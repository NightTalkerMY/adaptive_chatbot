from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: Optional[str] = None  # omit to start a new session
    message: str = Field(min_length=1, max_length=8000)


class SessionOut(BaseModel):
    id: str
    title: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    intent: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
