"""Portal document routes.

Routes are plain defs because Appwrite, MinIO and ingestion calls block, so FastAPI runs them in its threadpool.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.dependencies import CurrentPrincipal
from app.routes.presenters import present, read_pdf
from app.schemas.documents import (
    NOTE_MAX,
    ActionRequest,
    DocumentDetail,
    DocumentOut,
    FileLink,
    HistoryEntryOut,
    NewDocumentForm,
)
from app.services import document_history, portal_actions, portal_queries
from app.services.ledger_documents import LedgerStatus
from app.services.portal_queries import FILE_LINK_SECONDS
from app.services.workflow import Action

router = APIRouter(prefix="/api/documents", tags=["documents"])


def new_document_form(
    title: Annotated[str, Form()],
    category: Annotated[str, Form()],
    document_year: Annotated[str | None, Form()] = None,
    department: Annotated[str | None, Form(description="Contributors only: the department it belongs to")] = None,
    source_url: Annotated[str | None, Form(description="Required from contributors")] = None,
) -> NewDocumentForm:
    """A Form() model can't share a request with a file part, hence the fields one by one."""
    fields = {
        "title": title,
        "category": category,
        "document_year": document_year,
        "department": department,
        "source_url": source_url,
    }
    try:
        return NewDocumentForm.model_validate(fields)
    except ValidationError as exc:
        raise RequestValidationError(
            [{**error, "loc": ("body", *error["loc"])} for error in exc.errors(include_url=False)]
        ) from None


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload(
    principal: CurrentPrincipal,
    form: Annotated[NewDocumentForm, Depends(new_document_form)],
    file: Annotated[UploadFile, File(description="The document, as a PDF of at most 50 MB")],
    tasks: BackgroundTasks,
) -> DocumentOut:
    """Departments publish their own documents; contributors submit one for a department's review."""
    record = portal_actions.create(principal, form.to_submission(), read_pdf(file))
    if record["status"] == LedgerStatus.PUBLISHED:
        tasks.add_task(portal_actions.ingest_quietly, record["$id"])
    return present([record], principal)[0]


@router.get("/{document_id}", response_model=DocumentDetail)
def detail(principal: CurrentPrincipal, document_id: str) -> DocumentDetail:
    record = portal_queries.load_visible(principal, document_id)
    history = [HistoryEntryOut.from_entry(entry) for entry in document_history.entries_for(document_id)]
    return DocumentDetail(**present([record], principal)[0].model_dump(), history=history)


@router.get("/{document_id}/file", response_model=FileLink)
def file_link(principal: CurrentPrincipal, document_id: str) -> FileLink:
    return FileLink(url=portal_queries.file_link(principal, document_id), expires_in=FILE_LINK_SECONDS)


@router.post("/{document_id}/resubmit", response_model=DocumentOut)
def resubmit(
    principal: CurrentPrincipal,
    document_id: str,
    file: Annotated[UploadFile, File(description="The revised PDF")],
    note: Annotated[str | None, Form(max_length=NOTE_MAX)] = None,
) -> DocumentOut:
    """Send a revised file back to the department after a dispute (once per document)."""
    record, _ = portal_actions.act(
        principal, document_id, Action.RESUBMIT, note=(note or "").strip() or None, pdf=read_pdf(file)
    )
    return present([record], principal)[0]


@router.post("/{document_id}/{action}", response_model=DocumentOut)
def take_action(
    principal: CurrentPrincipal,
    document_id: str,
    action: Action,
    tasks: BackgroundTasks,
    request: ActionRequest | None = None,
) -> DocumentOut:
    """accept or dispute (department), accept-dispute or escalate (contributor), uphold or overrule (MCE)."""
    note = request.note if request else None
    record, published = portal_actions.act(principal, document_id, action, note=note)
    if published:
        tasks.add_task(portal_actions.ingest_quietly, document_id)
    return present([record], principal)[0]
