"""What a citizen can do after filing, with only the case reference: follow it, escalate it once,
and (straight after filing) answer the question about messages. Also the deletion of numbers
whose retention has ended.

Anyone holding a reference can open its status, so a personal-safety case's
status says only how far along it is: no category, service, place or note.
"""

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services import case_history, report_store
from app.services.case_history import CITIZEN, SYSTEM, CaseEntry, CaseHistoryAction
from app.services.case_workflow import (
    ESCALATION_WINDOW,
    CaseStatus,
    contact_purge_at,
    escalate,
    escalation_open,
)
from app.services.ledger_documents import parse_datetime
from app.services.report_contacts import contact_for, contacts_due_for_deletion, delete_contact, update_contact
from app.services.report_intake import token_hash
from app.services.report_rules import normalise_reference
from app.services.report_taxonomy import TOPICS_BY_ID
from app.services.workflow import NotAllowed
from app.teams import RECIPIENT_NAMES
from app.wards import sub_metros, wards

logger = logging.getLogger(__name__)

# The only progress words a personal-safety status shows.
PRIVATE_STAGES = {
    CaseStatus.SUBMITTED: "received",
    CaseStatus.ASSIGNED: "received",
    CaseStatus.IN_PROGRESS: "in_progress",
    CaseStatus.ESCALATED: "in_progress",
    CaseStatus.RESOLVED: "completed",
}


class CaseNotFound(Exception):
    """No case has that reference (or ID)."""


def find(reference_or_id: str) -> dict[str, Any]:
    """A case by its short reference, as typed, or by its case ID."""
    reference = normalise_reference(reference_or_id)
    case = report_store.find_by_reference(reference) if reference else None
    if case is None and _is_uuid(reference_or_id):
        case = report_store.find_case(reference_or_id.strip().lower())
    if case is None:
        raise CaseNotFound(reference_or_id)
    return case


def _is_uuid(text: str) -> bool:
    try:
        uuid.UUID(text.strip())
    except ValueError:
        return False
    return True


def _escalate_until(case: dict[str, Any], now: datetime) -> str | None:
    resolved_at = parse_datetime(case.get("resolvedAt"))
    return (resolved_at + ESCALATION_WINDOW).isoformat() if resolved_at and escalation_open(case, now) else None


def _resolution_notes(assignments: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"recipient": RECIPIENT_NAMES.get(a["recipient"], a["recipient"]), "note": a["resolutionNote"]}
        for a in assignments
        if a.get("active", True) and a.get("resolutionNote")
    ]


def public_status(case: dict[str, Any], assignments: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """What the citizen (or anyone with the reference) sees."""
    common = {
        "reference": case["reference"],
        "case_id": case["$id"],
        "submitted_at": case["createdAt"],
        "escalated": bool(case.get("escalatedAt")),
        "escalate_until": _escalate_until(case, now),
    }
    if case.get("isSensitive"):
        return {**common, "private": True, "stage": PRIVATE_STAGES[CaseStatus(case["status"])]}
    ward, sub_metro = wards().get(case.get("wardLocation") or ""), sub_metros().get(case.get("subMetro") or "")
    return {
        **common,
        "private": False,
        "status": case["status"],
        "topic": TOPICS_BY_ID[case["topic"]].label,
        "recipients": [RECIPIENT_NAMES.get(r, r) for r in case["recipients"]],
        "ward": ward.name if ward else None,
        "sub_metro": sub_metro.name if sub_metro else None,
        "resolved_at": case.get("resolvedAt"),
        "resolution_notes": _resolution_notes(assignments),
    }


def escalate_case(reference_or_id: str, note: str | None, now: datetime) -> dict[str, Any]:
    """The citizen's one escalation to the MCE. The numbers are kept while the case is open again."""
    case = find(reference_or_id)
    changes = escalate(case, (note or "").strip() or None, now)
    updated = report_store.update_case(case["$id"], changes)
    # A personal-safety case's escalation note is the citizen's own words: kept on the
    # case for its recipients, never copied into the trail the MCE reads.
    trail_note = "The citizen escalated the case." if case.get("isSensitive") else changes["escalationNote"]
    entry = CaseEntry(
        CaseHistoryAction.ESCALATED, CITIZEN, from_status=case["status"], to_status=changes["status"], note=trail_note
    )
    case_history.record(case["$id"], entry)
    sync_contact_retention(updated)
    return updated


@dataclass(frozen=True)
class Preferences:
    notify: bool
    callback_consent: bool


def set_preferences(reference_or_id: str, token: str, choice: Preferences, now: datetime) -> tuple[dict[str, Any], bool]:
    """The citizen's answer about messages and calls, for a report the classifier filed as personal safety.
    Once only, within the hour, with the token from the receipt. Returns the case and whether messages are now on."""
    case = find(reference_or_id)
    contact = contact_for(case["$id"])
    expires = parse_datetime(contact.get("preferencesExpiresAt")) if contact else None
    stored = (contact or {}).get("preferencesTokenHash") or ""
    if not contact or not expires or now > expires or not hmac.compare_digest(stored, token_hash(token)):
        raise NotAllowed("This choice can only be made on the confirmation page, within an hour of reporting.")
    changes = {
        "notify": choice.notify,
        "callbackConsent": choice.callback_consent,
        "preferencesTokenHash": None,  # used once
        "preferencesExpiresAt": None,
    }
    update_contact(case["$id"], changes)
    return case, choice.notify


def sync_contact_retention(case: dict[str, Any]) -> None:
    """Keep the numbers' deletion date in step with the case: none while open, 30 days after it closes."""
    contact = contact_for(case["$id"])
    if contact is None:
        return
    purge_at = contact_purge_at(case)
    update_contact(case["$id"], {"purgeAt": purge_at.isoformat() if purge_at else None})


def purge_expired_contacts(now: datetime) -> int:
    """Delete every citizen's numbers whose retention has ended; the trail records that it happened."""
    deleted = 0
    for contact in contacts_due_for_deletion(now):
        delete_contact(contact["$id"])
        note = "The citizen's contact numbers were deleted: 30 days after the case closed."
        case_history.record(contact["caseId"], CaseEntry(CaseHistoryAction.CONTACT_DELETED, SYSTEM, note=note))
        deleted += 1
    if deleted:
        logger.info("Deleted contact numbers for %d closed case(s)", deleted)
    return deleted

