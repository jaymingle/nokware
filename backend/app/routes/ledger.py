"""The public Ledger: what anyone can open without signing in."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.services import portal_queries

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


@router.get("/{document_id}/file", response_class=RedirectResponse, status_code=307)
def published_file(document_id: str) -> RedirectResponse:
    """Redirects to a fresh 10-minute link to a published document's PDF; 404 for anything else."""
    return RedirectResponse(portal_queries.public_file_link(document_id), status_code=307)
