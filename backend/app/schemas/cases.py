"""Models for the staff case routes. What a field holds depends on the caller's view of the case:
recipients see everything; the MCE sees a personal-safety case only in outline."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.documents import Option
from app.services.case_workflow import CaseAction

CaseViewName = Literal["full", "oversight"]


class CaseSummary(BaseModel):
    case_id: str
    reference: str
    private: bool  # personal safety
    view: CaseViewName  # "oversight": no description, photos, place, topic or contact
    topic: str  # the topic's label; "Personal safety" in an outline
    severity: int
    status: str  # the case's status
    my_status: str | None  # the caller's own assignment status, for a recipient
    place: str | None  # "Mudor, Ashiedu Keteke"; only a sub-metro, or none, for personal safety
    excerpt: str | None  # the description's opening words
    submitted_at: str
    recipients: list[str]  # names
    escalated: bool
    needs_routing: bool  # the classifier failed; routed to Central Administration for a person to route
    allowed_actions: list[CaseAction]  # exactly what the server would accept from the caller now


class CaseAssignment(BaseModel):
    recipient: str  # team ID
    name: str
    status: str
    active: bool
    acknowledged_at: str | None
    resolved_at: str | None
    resolution_note: str | None  # full view only


class CaseEvent(BaseModel):
    action: str
    actor_name: str
    actor_role: str
    note: str | None
    at: str


class Contact(BaseModel):
    """Shown only to a case's recipients, and only when the citizen allowed a call."""

    phone: str | None
    whatsapp: str | None


class CaseDetail(CaseSummary):
    description: str | None
    photos: list[str]  # short-lived links
    escalation_note: str | None
    classification_note: str | None
    contact: Contact | None
    assignments: list[CaseAssignment]
    history: list[CaseEvent]


class CaseQueue(BaseModel):
    cases: list[CaseSummary]


class OversightStats(BaseModel):
    open: int
    escalated: int
    resolved_30_days: int
    personal_safety_open: int | None  # None: fewer than 5, never shown as a number


class CaseOversight(BaseModel):
    cases: list[CaseSummary]
    stats: OversightStats
    recipients: list[Option]  # every department and agency, for filtering and reassignment


class NoteRequest(BaseModel):
    note: str = Field(max_length=2000)


class ReassignRequest(BaseModel):
    from_recipient: str
    to_recipient: str
    reason: str = Field(max_length=2000)
