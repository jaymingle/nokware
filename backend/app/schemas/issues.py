"""Public civic issues and the voices added to them. Never a citizen's words, photos or number."""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.citizen_reports import VOICE_NAME_MAX


class Issue(BaseModel):
    public_id: str
    topic: str  # the topic's label
    ward: str | None
    sub_metro: str | None
    departments: list[str]  # who has it
    stage: Literal["received", "in_progress", "escalated"]
    filed_at: str
    voices: int  # residents who said it affects them too


class IssuePage(BaseModel):
    issues: list[Issue]
    total: int


class VoiceRequest(BaseModel):
    device_token: str = Field(min_length=16, max_length=128)  # a random token the browser keeps
    name: str | None = Field(None, max_length=VOICE_NAME_MAX)  # absent: an anonymous voice


class VoiceResult(BaseModel):
    voices: int
    added: bool  # False: this browser had already added its voice
