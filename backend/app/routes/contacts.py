"""The public contact directory: who to call, grouped by service, each number with its source. No sign-in."""

from fastapi import APIRouter

from app import contacts
from app.schemas.contacts import ContactDirectory

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("", response_model=ContactDirectory)
def directory() -> ContactDirectory:
    return contacts.directory()
