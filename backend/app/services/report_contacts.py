"""A citizen's phone numbers: kept apart from the report, for notifications only.

Numbers live in report_contacts, encrypted at rest, and are read only to send
a message or, with the citizen's explicit callback consent, by the case's
recipients. They never appear in the report, its audit trail or the outbox,
and are deleted 30 days after the case closes.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, as_record, find_record, get_databases
from app.services.citizen_reports import CONTACTS_COLLECTION

GHANA_CODE = "233"
_GHANA_MOBILE = re.compile(r"^\+233[25]\d{8}$")  # MTN, Telecel and AT numbers start 02x or 05x
_INTERNATIONAL = re.compile(r"^\+[1-9]\d{7,14}$")  # E.164


class InvalidNumber(ValueError):
    """The number can't be used; the message is safe to show the citizen."""


def _digits(raw: str) -> str:
    return re.sub(r"[\s().-]", "", raw.strip())


def normalise_phone(raw: str) -> str:
    """Accepts 024…, 233… or +233…; returns +233XXXXXXXXX."""
    number = _digits(raw)
    if number.startswith("0") and len(number) == 10:
        number = f"+{GHANA_CODE}{number[1:]}"
    elif number.startswith(GHANA_CODE):
        number = f"+{number}"
    if not _GHANA_MOBILE.match(number):
        raise InvalidNumber("Enter a Ghanaian mobile number, for example 024 123 4567.")
    return number


def normalise_whatsapp(raw: str) -> str:
    """WhatsApp also takes any international number written with its + code."""
    number = _digits(raw)
    if not number.startswith("+"):
        return normalise_phone(number)
    if not _INTERNATIONAL.match(number):
        raise InvalidNumber("Enter the WhatsApp number with its country code, for example +233 24 123 4567.")
    return number


def masked(number: str) -> str:
    """For logs: the country code and last two digits only."""
    return f"{number[:4]}…{number[-2:]}"


@dataclass(frozen=True)
class ContactChoice:
    """What the citizen gave and agreed to, already validated."""

    phone: str | None
    whatsapp: str | None
    notify: bool  # send the submitted / resolved / escalated messages
    callback_consent: bool  # recipients may call the citizen about this case

    @property
    def given(self) -> bool:
        return bool(self.phone or self.whatsapp)


def save_contact(case_id: str, choice: ContactChoice) -> None:
    """Stored under the case's own ID: one contact per case, found without a query."""
    get_databases().create_document(
        DATABASE_ID,
        CONTACTS_COLLECTION,
        case_id,
        {
            "caseId": case_id,
            "phone": choice.phone,
            "whatsapp": choice.whatsapp,
            "notify": choice.notify,
            "callbackConsent": choice.callback_consent,
        },
    )


def contact_for(case_id: str) -> dict[str, Any] | None:
    return find_record(CONTACTS_COLLECTION, case_id)


def update_contact(case_id: str, changes: dict[str, Any]) -> None:
    get_databases().update_document(DATABASE_ID, CONTACTS_COLLECTION, case_id, changes)


def contacts_due_for_deletion(now: datetime, limit: int = 100) -> list[dict[str, Any]]:
    listing = get_databases().list_documents(
        DATABASE_ID,
        CONTACTS_COLLECTION,
        queries=[Query.less_than_equal("purgeAt", now.isoformat()), Query.limit(limit)],
    )
    return [as_record(document) for document in listing.documents]


def delete_contact(case_id: str) -> None:
    get_databases().delete_document(DATABASE_ID, CONTACTS_COLLECTION, case_id)
