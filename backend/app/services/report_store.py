"""Reads and writes for citizen reports and their assignments.

A report is stored under its case ID (a UUID), so it is found without a query;
its short reference is unique and indexed for lookups by citizens.
"""

from typing import Any

from appwrite.exception import AppwriteException
from appwrite.id import ID
from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, as_record, find_record, get_databases
from app.services.citizen_reports import ASSIGNMENTS_COLLECTION, REPORTS_COLLECTION

QUEUE_LIMIT = 200


class DuplicateReference(Exception):
    """The random reference is already taken (vanishingly rare); draw another."""


def create_report(case_id: str, data: dict[str, Any]) -> dict[str, Any]:
    try:
        return as_record(get_databases().create_document(DATABASE_ID, REPORTS_COLLECTION, case_id, data))
    except AppwriteException as exc:
        if exc.code == 409:
            raise DuplicateReference from exc
        raise


def find_case(case_id: str) -> dict[str, Any] | None:
    return find_record(REPORTS_COLLECTION, case_id)


def find_by_reference(reference: str) -> dict[str, Any] | None:
    listing = get_databases().list_documents(
        DATABASE_ID, REPORTS_COLLECTION, queries=[Query.equal("reference", reference), Query.limit(1)]
    )
    return as_record(listing.documents[0]) if listing.documents else None


def update_case(case_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    return as_record(get_databases().update_document(DATABASE_ID, REPORTS_COLLECTION, case_id, changes))


def create_assignment(data: dict[str, Any]) -> dict[str, Any]:
    return as_record(get_databases().create_document(DATABASE_ID, ASSIGNMENTS_COLLECTION, ID.unique(), data))


def assignments_for(case_id: str) -> list[dict[str, Any]]:
    listing = get_databases().list_documents(
        DATABASE_ID, ASSIGNMENTS_COLLECTION, queries=[Query.equal("caseId", case_id), Query.limit(20)]
    )
    return [as_record(document) for document in listing.documents]


def update_assignment(assignment_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    return as_record(get_databases().update_document(DATABASE_ID, ASSIGNMENTS_COLLECTION, assignment_id, changes))
