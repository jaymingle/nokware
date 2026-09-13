"""Shared helpers for portal routes: presenting records and reading uploaded PDFs."""

from typing import Any

from fastapi import HTTPException, UploadFile, status

from app.schemas.documents import DocumentOut
from app.services.auth import Principal
from app.services.ledger_documents import ingestion_state, utc_now
from app.services.portal_queries import display_names
from app.services.workflow import allowed_actions

MAX_PDF_BYTES = 50 * 1024 * 1024
PDF_SIGNATURE = b"%PDF-"
PDF_SIGNATURE_WINDOW = 1024  # readers accept the signature anywhere in the first 1 KB


def present(records: list[dict[str, Any]], principal: Principal) -> list[DocumentOut]:
    """Records as the caller sees them, including the actions open to them."""
    now = utc_now()
    names = display_names(user_id for r in records for user_id in (r.get("uploadedBy"), r.get("disputedBy")))
    return [
        DocumentOut.from_record(record, ingestion_state(record), allowed_actions(record, principal, now), names)
        for record in records
    ]


def read_pdf(upload: UploadFile) -> bytes:
    """The uploaded file's bytes, if it is a PDF within the size limit."""
    data = upload.file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The PDF is larger than 50 MB.")
    if PDF_SIGNATURE not in data[:PDF_SIGNATURE_WINDOW]:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "That file isn't a valid PDF. Choose the original PDF and try again.")
    return data
