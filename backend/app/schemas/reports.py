"""Request and response models for citizen reports (public routes)."""

from pydantic import BaseModel, Field

from app.schemas.contacts import PublicContact
from app.schemas.documents import Option


class SubMetroOption(BaseModel):
    id: str
    name: str
    wards: list[Option]


class SafetyType(BaseModel):
    id: str
    label: str
    guide: str
    recipients: list[str]  # who a report of this type goes to, in plain names ("Social Welfare")


class ReportOptions(BaseModel):
    sub_metros: list[SubMetroOption]
    safety_types: list[SafetyType]
    max_photos: int
    max_photo_bytes: int
    description_min: int
    description_max: int
    safety_contacts: list[PublicContact]  # shown on the safety form: emergency lines, the helpline, Social Welfare


class ReportReceipt(BaseModel):
    reference: str
    case_id: str
    private: bool  # filed as personal safety
    topic: str | None  # the topic's label; None for personal safety
    recipients: list[str]  # who it was sent to (shown once, on the confirmation page); plain names if private
    messages_on: bool  # the citizen will get the received / resolved / escalated messages
    held_for_consent: bool  # filed as personal safety by the classifier: ask about messages and calls
    preferences_token: str | None  # send back as X-Receipt-Token to answer that question, once, within the hour
    contacts: list[PublicContact]  # numbers for where the report went


class ResolutionNote(BaseModel):
    recipient: str
    note: str


class ReportStatus(BaseModel):
    """A case's status. For personal safety, only the stage: no category, service, place or note."""

    reference: str
    case_id: str
    private: bool
    submitted_at: str
    escalated: bool
    escalate_until: str | None  # set while the citizen may still escalate
    stage: str | None = None  # personal safety only: received, in_progress or completed
    status: str | None = None
    topic: str | None = None
    recipients: list[str] = Field(default_factory=list)
    ward: str | None = None
    sub_metro: str | None = None
    resolved_at: str | None = None
    resolution_notes: list[ResolutionNote] = Field(default_factory=list)
    contacts: list[PublicContact] = Field(default_factory=list)  # everyday reports only: numbers for where it went
    voices: int | None = None  # civic reports only: other residents who said it affects them too


class EscalationRequest(BaseModel):
    note: str = Field(max_length=2000)


class PreferencesRequest(BaseModel):
    notify: bool
    callback_consent: bool


class PreferencesResult(BaseModel):
    messages_on: bool
