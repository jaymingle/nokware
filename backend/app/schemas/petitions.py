"""Petitions and phone confirmation. A creator's number never leaves the server; only a masked hint does."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.documents import Option
from app.services.ledger_documents import Provenance
from app.services.petition_rules import BODY_MAX, DOCUMENTS_MAX, NAME_MAX, NOTE_MAX, TITLE_MAX

Status = Literal["in_review", "refused", "open", "awaiting_response", "closed", "withdrawn"]
Scope = Literal["metro", "area"]


class AreaOption(BaseModel):
    id: str
    name: str
    sub_metro: str  # the sub-metro's name


class RefusalReason(BaseModel):
    id: str
    label: str
    explanation: str


class Verification(BaseModel):
    """The ways a number can be confirmed here: WhatsApp and USSD when set up; SMS only once switched on."""

    whatsapp: bool
    ussd_code: str | None
    sms: bool


class PetitionOptions(BaseModel):
    topics: list[Option]
    areas: list[AreaOption]
    threshold_area: int
    threshold_metro: int
    review_hours: int
    open_days: int
    response_days: int
    refusal_reasons: list[RefusalReason]
    verification: Verification


class DocumentRef(BaseModel):
    id: str  # its PDF is at /api/ledger/{id}/file
    title: str
    department_name: str | None
    year: int | None
    provenance: Provenance | None


class LedgerMatch(DocumentRef):
    passage: str  # the part that matched


class LinkedIssue(BaseModel):
    public_id: str
    topic: str
    ward: str | None
    stage: Literal["received", "in_progress", "escalated", "resolved"]
    voices: int


class PetitionCard(BaseModel):
    code: str
    title: str  # what it asks the Assembly to do
    topic: str  # the topic's label
    departments: list[str]
    scope: Scope
    area: str | None  # the electoral area, for an area petition
    sub_metro: str | None
    status: Status
    published_at: str | None
    published_by: Literal["mce", "automatic"] | None
    closes_at: str | None
    closed_at: str | None
    threshold: int | None
    signatures: int
    started_by: str | None  # a name only if the creator chose to show one
    threshold_reached_at: str | None
    response_due: str | None  # the MCE's 30 days to respond publicly, once it reached its threshold


class TimelineEntry(BaseModel):
    action: Literal["submitted", "resubmitted", "published", "auto_published", "refused", "withdrawn", "closed", "threshold_reached"]
    at: str
    reason: str | None  # a refusal's reason, as the public list counts it


class PetitionDetail(PetitionCard):
    body: str
    timeline: list[TimelineEntry]
    issue: LinkedIssue | None
    documents: list[DocumentRef]  # what the creator cited


class RefusalCount(BaseModel):
    reason: str
    label: str
    count: int


class Moderation(BaseModel):
    """How the MCE has handled petitions: shown exactly, since the count is of decisions, not of people."""

    awaiting: int
    published_by_mce: int
    published_automatically: int
    refusals: list[RefusalCount]
    refusals_total: int


class PetitionPage(BaseModel):
    petitions: list[PetitionCard]
    total: int
    moderation: Moderation
    topics: list[Option]


class DraftRequest(BaseModel):
    title: str = Field(max_length=TITLE_MAX + 50)
    body: str = Field(max_length=BODY_MAX + 500)
    topic: str
    scope: Scope
    ward: str | None = None
    issue: str | None = Field(None, max_length=20)
    documents: list[str] = Field(default_factory=list, max_length=DOCUMENTS_MAX)


class SubmitRequest(DraftRequest):
    show_name: bool = False
    name: str | None = Field(None, max_length=NAME_MAX + 20)


class ScreenRequest(BaseModel):
    title: str = Field(max_length=TITLE_MAX + 50)
    body: str = Field(max_length=BODY_MAX + 500)


class ScreenResult(BaseModel):
    stop: str | None  # it can't go as written, and why
    warning: str | None  # it can go, but the creator should know this first


class LedgerSearchRequest(ScreenRequest):
    topic: str


class Refusal(BaseModel):
    reason: str
    label: str
    explanation: str
    note: str | None  # the MCE's note to the creator: never public
    duplicate_of: str | None


class OwnPetition(PetitionCard):
    body: str
    topic_id: str
    ward_id: str | None
    issue_id: str | None
    document_ids: list[str]
    submitted_at: str | None
    review_deadline: str | None
    refusal: Refusal | None
    resubmissions_left: int
    actions: list[Literal["withdraw", "resubmit", "make_anonymous"]]


class MyPetitions(BaseModel):
    number: str  # masked, e.g. +233…73
    petitions: list[OwnPetition]


class ReviewItem(BaseModel):
    code: str
    title: str
    body: str
    topic: str
    departments: list[str]
    scope: Scope
    area: str | None
    sub_metro: str | None
    started_by: str | None
    submitted_at: str
    review_deadline: str
    resubmissions: int
    earlier_refusals: list[Refusal]
    issue: LinkedIssue | None
    documents: list[DocumentRef]


class ReviewQueue(BaseModel):
    petitions: list[ReviewItem]
    refusal_reasons: list[RefusalReason]


class DecisionRequest(BaseModel):
    decision: Literal["publish", "refuse"]
    reason: str | None = None
    note: str | None = Field(None, max_length=NOTE_MAX + 100)
    duplicate_of: str | None = Field(None, max_length=20)


class ChallengeResult(BaseModel):
    challenge: str  # the secret this page keeps, to collect the proof
    code: str  # six digits, to send by WhatsApp or type in USSD
    expires_in: int  # seconds
    whatsapp_url: str | None
    ussd_code: str | None
    sms: bool


class ChallengeRequest(BaseModel):
    challenge: str = Field(max_length=64)


class ChallengeStatus(BaseModel):
    state: Literal["waiting", "proven", "expired"]
    proof: str | None  # sent back as X-Phone-Proof
    number: str | None  # masked
    expires_at: str | None


class SmsCodeRequest(ChallengeRequest):
    phone: str = Field(max_length=32)


class SmsCodeSent(BaseModel):
    sent_to: str  # masked


class SmsConfirmRequest(ChallengeRequest):
    code: str = Field(max_length=12)


class SignRequest(BaseModel):
    show_name: bool = False
    name: str | None = Field(None, max_length=NAME_MAX + 20)


class SignResult(BaseModel):
    added: bool  # False: this number had already signed
    named: bool
    signatures: int
    threshold: int | None
    status: Status


class MySignature(BaseModel):
    signed: bool
    named: bool
    name: str | None
    signed_at: str | None


class NamedSignature(BaseModel):
    name: str
    signed_at: str


class NamedSignatures(BaseModel):
    names: list[NamedSignature]
    total: int  # signers who chose to show their name


class AwaitingResponse(BaseModel):
    code: str
    title: str
    topic: str
    departments: list[str]
    scope: Scope
    area: str | None
    sub_metro: str | None
    signatures: int
    threshold: int
    threshold_reached_at: str
    response_due: str
