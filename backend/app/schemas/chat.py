from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=300)
    driver_mode: bool = False


class ChatResponse(BaseModel):
    intent: str
    lang: Literal["en", "hinglish", "kn"]
    text: str
    has_location: bool
