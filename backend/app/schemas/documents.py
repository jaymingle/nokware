"""Request and response shapes for the portal's document routes."""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, Field, HttpUrl, field_validator

from app.categories import category_names
from app.services.document_history import HistoryAction
from app.services.ledger_documents import EARLIEST_YEAR, IngestionState, LedgerStatus, SourceType, utc_now
from app.services.workflow import Action, Submission
from app.teams import DEPARTMENT_NAMES

NOTE_MAX = 2000
TITLE_MAX = 300
SOURCE_URL_MAX = 2048  # size of the sourceUrl attribute


def _blank_to_none(value: Any) -> Any:
    """Empty form fields arrive as ""; treat them as not given."""
    if isinstance(value, str) and not value.strip():
        return None
    return value.strip() if isinstance(value, str) else value


OptionalText = Annotated[str | None, BeforeValidator(_blank_to_none)]


class NewDocumentForm(BaseModel):
    """Multipart fields of an upload (the PDF itself is a separate file part)."""

    title: Annotated[str, Field(min_length=3, max_length=TITLE_MAX), BeforeValidator(_blank_to_none)]
    category: str
    document_year: Annotated[int | None, BeforeValidator(_blank_to_none)] = None
    department: OptionalText = None  # contributors choose; departments may omit it
    source_url: Annotated[HttpUrl | None, BeforeValidator(_blank_to_none)] = None

    @field_validator("category")
    @classmethod
    def known_category(cls, value: str) -> str:
        if value not in category_names():
            raise ValueError("choose one of the AMA's document categories")
        return value

    @field_validator("source_url")
    @classmethod
    def fits(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and len(str(value)) > SOURCE_URL_MAX:
            raise ValueError(f"use a web address of at most {SOURCE_URL_MAX} characters")
        return value

    @field_validator("document_year")
    @classmethod
    def plausible(cls, value: int | None) -> int | None:
        if value is not None and not EARLIEST_YEAR <= value <= utc_now().year:
            raise ValueError(f"give a year between {EARLIEST_YEAR} and this year")
        return value

    def to_submission(self) -> Submission:
        return Submission(
            title=self.title,
            category=self.category,
            document_year=self.document_year,
            department=self.department,
            source_url=str(self.source_url) if self.source_url else None,
        )


class ActionRequest(BaseModel):
    note: Annotated[str | None, Field(max_length=NOTE_MAX), BeforeValidator(_blank_to_none)] = None


class DocumentOut(BaseModel):
    id: str
    title: str
    category: str
    department: str
    department_name: str | None
    source_type: SourceType
    source_url: str | None
    document_year: int | None
    status: LedgerStatus
    uploaded_by: str
    uploaded_by_name: str | None
    created_at: str
    published_at: str | None
    held_until: str | None  # when the running clock (department or MCE) publishes it
    escalated_to_mce: bool
    dispute_reason: str | None
    disputed_by_name: str | None
    disputed_at: str | None
    contributor_response: str | None
    resubmission_count: int
    ingestion: IngestionState | None
    chunk_count: int | None
    allowed_actions: list[Action]  # exactly what the server would accept from the caller now

    @classmethod
    def from_record(
        cls, record: dict[str, Any], ingestion: IngestionState | None, allowed: list[Action], names: dict[str, str]
    ) -> "DocumentOut":
        return cls(
            id=record["$id"],
            title=record["title"],
            category=record["category"],
            department=record["department"],
            department_name=DEPARTMENT_NAMES.get(record["department"]),
            source_type=record["sourceType"],
            source_url=record.get("sourceUrl"),
            document_year=record.get("documentYear"),
            status=record.get("status") or LedgerStatus.HELD,
            uploaded_by=record["uploadedBy"],
            uploaded_by_name=names.get(record["uploadedBy"]),
            created_at=record["$createdAt"],
            published_at=record.get("publishedAt"),
            held_until=record.get("heldUntil"),
            escalated_to_mce=bool(record.get("escalatedToMce")),
            dispute_reason=record.get("disputeReason"),
            disputed_by_name=names.get(record.get("disputedBy") or ""),
            disputed_at=record.get("disputedAt"),
            contributor_response=record.get("contributorResponse"),
            resubmission_count=record.get("resubmissionCount") or 0,
            ingestion=ingestion,
            chunk_count=record.get("chunkCount"),
            allowed_actions=allowed,
        )


class HistoryEntryOut(BaseModel):
    action: HistoryAction
    actor_name: str
    actor_role: str
    from_status: LedgerStatus | None
    to_status: LedgerStatus
    note: str | None
    at: str

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> "HistoryEntryOut":
        return cls(
            action=entry["action"],
            actor_name=entry["actorName"],
            actor_role=entry["actorRole"],
            from_status=entry.get("fromStatus"),
            to_status=entry["toStatus"],
            note=entry.get("note"),
            at=entry["at"],
        )


class DocumentDetail(DocumentOut):
    history: list[HistoryEntryOut]


class DocumentPage(BaseModel):
    documents: list[DocumentOut]
    total: int


class FileLink(BaseModel):
    url: str
    expires_in: int  # seconds


class Option(BaseModel):
    id: str
    name: str


class JobResult(BaseModel):
    published: list[str]
    ingestion_queued: list[str]
