"""Petitions and phone confirmation. A creator's number never leaves the server; only a masked hint does."""

from typing import Literal

from fastapi import UploadFile
from pydantic import BaseModel, Field

from app.schemas.documents import Option
from app.services.ledger_documents import Provenance
from app.services.petition_comments import COMMENT_MAX
from app.services.petition_rules import (
    BODY_MAX,
    DEPARTMENT_NOTE_MAX,
    DOCUMENTS_MAX,
    IMAGES_MAX,
    NAME_MAX,
    REMOVAL_NOTE_MAX,
    REPLY_MAX,
    REPORT_NOTE_MAX,
    RESPONSE_MAX,
    TITLE_MAX,
)

Status = Literal["open", "awaiting_response", "responded", "removed", "closed"]
ResponseKind = Literal["will_act", "referred", "cannot_act"]
Scope = Literal["metro", "area"]
Ground = Literal["private_individual", "incites_violence", "personal_data", "duplicate"]
DismissalReason = Literal["not_the_ground", "already_handled"]


class AreaOption(BaseModel):
    id: str
    name: str
    sub_metro: str  # the sub-metro's name


class GroundOption(BaseModel):
    """One of the four grounds, in the words every screen shows it in. The same id is stored whether it was read
    about a petition or about a comment; only the label differs."""

    id: Ground
    label: str
    needs_petition_number: bool  # a petition's duplicate names the petition it duplicates; a comment's names none


class DismissalOption(BaseModel):
    id: DismissalReason
    label: str


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
    open_days: int
    response_days: int
    max_images: int
    max_documents: int
    report_note_max: int
    removal_note_max: int
    department_note_max: int  # a department's one note on a petition shared with it
    reply_max: int  # the petitioner's reply to the MCE's response
    comment_max: int
    grounds: list[GroundOption]
    comment_grounds: list[GroundOption]  # the same ids, in the words a comment is judged by
    dismissal_reasons: list[DismissalOption]
    status_words: dict[Status, str]  # one wording for a status, wherever it is shown
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
    status_label: str  # the status in the words every page uses
    published_at: str | None
    closes_at: str | None
    closed_at: str | None
    threshold: int | None
    signatures: int
    started_by: str | None  # a name only if the creator chose to show one
    threshold_reached_at: str | None
    response_due: str | None  # the MCE's 30 days to respond publicly, once it reached its threshold
    responded_at: str | None
    response_label: str | None  # "The Assembly will act", "Referred to a department", "The Assembly can't act"
    unanswered_at: str | None  # when the 30 days passed with no response, if they did
    version: int
    versioned_at: str | None  # when the words last changed
    removals: int  # how many times this petition has been removed and published again


class TimelineEntry(BaseModel):
    action: Literal["published", "edited", "republished", "removed", "withdrawn", "closed", "threshold_reached",
                    "responded", "no_response", "shared", "department_note", "creator_replied", "image_removed",
                    # not an action anyone took: the day a petition already in the database came to this process
                    "moved_to_new_process"]
    at: str
    reason: str | None  # a removal's ground, a shared petition's department, or how the old process ended it


class VersionEntry(BaseModel):
    """One version of the words, as an edit history reads it."""

    version: int
    at: str
    title: str
    changed: list[str]  # which of title, body, topic, scope, wardLocation, imageIds changed from the version before


class PetitionReply(BaseModel):
    """The petitioner's one answer to the response. Their name is the petition's own: none unless they showed it."""

    text: str
    at: str


class DepartmentShare(BaseModel):
    """One department the MCE sent this petition to, and the one note that department wrote back."""

    department: str  # the department's name, as every page writes it
    shared_at: str
    note: str | None  # None until the department has written; it writes once
    note_at: str | None


class PetitionResponse(BaseModel):
    """The MCE's public response, as given. Never the name of the person who gave it."""

    kind: ResponseKind
    label: str
    text: str
    department: str | None  # the department it is referred to
    documents: list[DocumentRef]
    responded_at: str
    late: bool  # after the 30-day deadline
    days_late: int  # whole days after it, never rounded up; 0 if in time or less than a day late
    reply: PetitionReply | None  # what the petitioner said back, under it


class PetitionDetail(PetitionCard):
    state: Literal["published"] = "published"
    body: str
    images: list[str]  # short-lived links
    timeline: list[TimelineEntry]
    versions: list[VersionEntry]
    signatures_on_earlier_versions: int  # of `signatures`, how many were given before the words last changed
    issue: LinkedIssue | None
    documents: list[DocumentRef]  # what the creator cited
    response: PetitionResponse | None
    comments: int = 0  # how many stand under it, so a page or a channel can say so; the route counts them
    shared_with: list[DepartmentShare] = Field(default_factory=list)  # the route reads them, as it counts comments


class Tombstone(BaseModel):
    """All that is left of a removed petition. Built from the removal record, never from the petition, so there is
    nothing here to leave out: no title, body, image, signature count, comment or answer exists to be shown."""

    state: Literal["removed"] = "removed"
    code: str
    ground: Ground
    ground_words: str
    removed_at: str
    duplicate_of: str | None  # the open petition this one repeated
    previous_removals: int  # how many times this petition had been removed before



class RemovalCount(BaseModel):
    ground: Ground
    label: str
    count: int


class Removals(BaseModel):
    """How many petitions have come down, and on what grounds. Shown exactly: they count petitions, not residents."""

    total: int
    grounds: list[RemovalCount]


class PetitionPage(BaseModel):
    """One group of petitions. The removed group fills `removed` instead of `petitions`: there are no cards to
    show, only the tombstones, which carry nothing of the petitions they stand for."""

    petitions: list[PetitionCard]
    removed: list[Tombstone]  # empty in every other group, so the page never has to test for the field
    total: int
    counts: dict[str, int]  # how many stand in each group, so a tab says what it holds
    removals: Removals
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
    """Sent as a form, so the images arrive with the words in one request."""

    show_name: bool = False
    name: str | None = Field(None, max_length=NAME_MAX + 20)
    images: list[UploadFile] = Field(default_factory=list, max_length=IMAGES_MAX)


class EditRequest(DraftRequest):
    """An edit sends the words again, naming the images it keeps and attaching any new ones."""

    keep_images: list[str] = Field(default_factory=list, max_length=IMAGES_MAX)
    images: list[UploadFile] = Field(default_factory=list, max_length=IMAGES_MAX)


class ScreenRequest(BaseModel):
    title: str = Field(max_length=TITLE_MAX + 50)
    body: str = Field(max_length=BODY_MAX + 500)


class ScreenResult(BaseModel):
    stop: str | None  # it can't go as written, and why
    warning: str | None  # it can go, but the creator should know this first


class LedgerSearchRequest(ScreenRequest):
    topic: str


class RemovalNotice(BaseModel):
    """What the creator is told about their petition coming down. Not the contributor's note, which is internal,
    and not who removed it: a ground is a ground whoever names it."""

    ground: Ground
    label: str
    removed_at: str
    duplicate_of: str | None


class OwnPetition(PetitionCard):
    body: str
    images: list[str]
    topic_id: str
    ward_id: str | None
    issue_id: str | None
    document_ids: list[str]
    image_ids: list[str]  # so an edit can keep the images it isn't changing
    submitted_at: str | None
    removal: RemovalNotice | None
    actions: list[Literal["edit", "withdraw", "make_anonymous"]]


class OwnPetitionDetail(OwnPetition):
    """A petition as the person who started it reads it: everything its public page shows, and the record of a
    removal besides. Read by its number and the number that started it, so it answers for a removed petition too,
    whose public page is only a tombstone."""

    timeline: list[TimelineEntry]
    versions: list[VersionEntry]
    response: PetitionResponse | None
    shared_with: list[DepartmentShare]
    signatures_on_earlier_versions: int


class MyPetitions(BaseModel):
    number: str  # masked, e.g. +233…73
    petitions: list[OwnPetition]


class ReportRequest(BaseModel):
    ground: Ground
    duplicate_of: str | None = Field(None, max_length=20)
    note: str | None = Field(None, max_length=REPORT_NOTE_MAX + 100)


class ReportFiled(BaseModel):
    message: str  # says plainly that the petition stays up
    reported_at: str


class PetitionImage(BaseModel):
    """A photograph as a contributor meets it: a link to look at, and the name that takes it down."""

    id: str
    url: str  # short-lived


class ReportedPetition(BaseModel):
    id: str  # the report, for dismissing it
    reported_at: str
    ground: Ground
    ground_words: str
    duplicate_of: str | None
    note: str | None  # what the reader added, as they wrote it
    reports_on_this_petition: int
    petition: PetitionCard
    images: list[PetitionImage]  # what a contributor judging it can see, and take down one at a time


class Comment(BaseModel):
    """One comment as a reader meets it: what somebody wrote, or — where a contributor removed it — the notice
    that stands in its place. Never a phone number: a comment holds none."""

    id: str
    name: str | None  # the name its writer chose, or "Resident"; none on a removed comment
    text: str  # the comment, or the removal notice naming the ground
    at: str
    removed: bool


class CommentPage(BaseModel):
    comments: list[Comment]
    total: int  # every comment under the petition, however many this page holds


class CommentRequest(BaseModel):
    text: str = Field(max_length=COMMENT_MAX + 100)
    name: str | None = Field(None, max_length=NAME_MAX + 20)  # empty for "Resident"


class CommentReportRequest(BaseModel):
    """A comment is reported on the same four stored grounds a petition is, and names no other petition: a
    duplicate here repeats another comment on the same page."""

    ground: Ground
    note: str | None = Field(None, max_length=REPORT_NOTE_MAX + 100)


class ImageRemovalRequest(BaseModel):
    """The photo is named as the petition stores it, so a contributor removes the one they are looking at."""

    image_id: str = Field(max_length=200)
    ground: Ground


class CommentRemovalRequest(BaseModel):
    ground: Ground


class ReportedComment(BaseModel):
    id: str  # the report, for dismissing it
    reported_at: str
    ground: Ground
    ground_words: str  # in a comment's words: a duplicate repeats another comment
    note: str | None  # what the reader added, as they wrote it
    reports_on_this_comment: int
    code: str  # the petition the comment stands under
    comment: Comment


class ReportQueue(BaseModel):
    reports: list[ReportedPetition]
    comments: list[ReportedComment]  # reported comments reach the same contributor
    grounds: list[GroundOption]
    comment_grounds: list[GroundOption]  # the same ids, in the words a comment is judged by
    dismissal_reasons: list[DismissalOption]


class RemovalRequest(BaseModel):
    ground: Ground
    duplicate_of: str | None = Field(None, max_length=20)
    note: str | None = Field(None, max_length=REMOVAL_NOTE_MAX + 100)  # internal: the audit trail only


class DismissRequest(BaseModel):
    reason: DismissalReason


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
    version: int  # the version of the words this signature stands on


class MySignature(BaseModel):
    signed: bool
    named: bool
    name: str | None
    signed_at: str | None
    version: int | None  # which version of the words was signed


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


class ResponseRequest(BaseModel):
    kind: ResponseKind
    text: str = Field(max_length=RESPONSE_MAX + 500)
    department: str | None = None
    documents: list[str] = Field(default_factory=list, max_length=DOCUMENTS_MAX)


class ShareRequest(BaseModel):
    """The department the MCE sends the petition to, from /api/departments — the Assembly's one list of them."""

    department: str = Field(max_length=64)


class NoteRequest(BaseModel):
    text: str = Field(max_length=DEPARTMENT_NOTE_MAX + 100)


class SharedPetition(BaseModel):
    """A petition as the department it was shared with meets it, with the note it has written, if it has."""

    petition: PetitionCard
    shared_at: str
    note: str | None
    note_at: str | None


class ReplyRequest(BaseModel):
    text: str = Field(max_length=REPLY_MAX + 200)
