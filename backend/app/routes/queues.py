"""The lists each role works from.

Included before routes/documents.py so /documents/library and /documents/mine
are matched before /documents/{document_id}.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import require_roles
from app.routes.presenters import present
from app.schemas.documents import DocumentOut, DocumentPage
from app.services import portal_queries
from app.services.auth import Principal, Role

router = APIRouter(prefix="/api", tags=["queues"])

Department = Annotated[Principal, Depends(require_roles(Role.DEPARTMENT))]
Contributor = Annotated[Principal, Depends(require_roles(Role.CONTRIBUTOR))]
Mce = Annotated[Principal, Depends(require_roles(Role.MCE))]


@router.get("/review-queue", response_model=list[DocumentOut])
def review_queue(principal: Department) -> list[DocumentOut]:
    """Held documents for the caller's department (soonest deadline first), then its open disputes."""
    return present(portal_queries.review_queue(principal), principal)


@router.get("/documents/library", response_model=DocumentPage)
def library(
    principal: Department,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    records, total = portal_queries.library(principal, limit, offset)
    return DocumentPage(documents=present(records, principal), total=total)


@router.get("/documents/mine", response_model=list[DocumentOut])
def my_submissions(principal: Contributor) -> list[DocumentOut]:
    return present(portal_queries.submissions(principal), principal)


@router.get("/escalations", response_model=list[DocumentOut])
def escalations(principal: Mce) -> list[DocumentOut]:
    return present(portal_queries.escalations(), principal)
