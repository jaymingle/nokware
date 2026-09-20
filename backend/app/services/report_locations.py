"""A precise location a personal-safety reporter chose to share so that help can come.

The one exception to the coarse-location rule (a sub-metro at most), on the citizen's explicit opt-in only. It is
kept with the citizen's numbers, encrypted at rest, deleted with them or at once when the citizen asks, and never
held in Redis on the way.

Only a Police or Social Welfare account actively handling the case can open it, one deliberate view at a time, and
each view is shown to the citizen. It never reaches the MCE, another department (even after a reassignment), a
list, a message, the outbox, the logs, Ask or the dashboard.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services import case_history
from app.services.auth import Principal, Role
from app.services.case_history import CITIZEN, CaseEntry, CaseHistoryAction, actor
from app.services.report_contacts import contact_for, update_contact
from app.services.report_taxonomy import POLICE, Category
from app.services.workflow import NotAllowed
from app.teams import RECIPIENT_NAMES

RESPONDERS = frozenset({POLICE, "dept-social-welfare"})
ADDRESS_MAX = 400


class NoLocation(LookupError):
    """No location was shared for this case, or it has been removed."""


@dataclass(frozen=True)
class SharedLocation:
    address: str | None  # as typed, or the place name WhatsApp sent with a pin
    latitude: float | None
    longitude: float | None
    shared_at: str


def _is_responder_case(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> bool:
    team = principal.recipient
    if case.get("category") != Category.PERSONAL_SAFETY or principal.role not in (Role.DEPARTMENT, Role.AGENCY):
        return False
    return team in RESPONDERS and any(a["recipient"] == team and a.get("active", True) for a in assignments)


def share(case_id: str, address: str | None, latitude: float | None, longitude: float | None, now: datetime) -> None:
    """The trail notes that a location was shared, never what."""
    text = (address or "").strip()[:ADDRESS_MAX] or None
    if text is None and (latitude is None or longitude is None):
        raise ValueError("A location needs an address or a pin.")
    stored = json.dumps({"address": text, "latitude": latitude, "longitude": longitude})
    update_contact(case_id, {"exactLocation": stored, "exactLocationAt": now.isoformat()})
    note = "The citizen shared a precise location, for the Police and Social Welfare only."
    case_history.record(case_id, CaseEntry(CaseHistoryAction.LOCATION_SHARED, CITIZEN, note=note))


def remove(case_id: str) -> bool:
    """True only once a fresh read shows it is gone."""
    update_contact(case_id, {"exactLocation": None, "exactLocationAt": None})
    gone = not (contact_for(case_id) or {}).get("exactLocation")
    if gone:
        case_history.record(case_id, CaseEntry(CaseHistoryAction.LOCATION_REMOVED, CITIZEN, note="The citizen removed the location they shared."))
    return gone


def shared_at(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> str | None:
    if not _is_responder_case(principal, case, assignments):
        return None
    return (contact_for(case["$id"]) or {}).get("exactLocationAt")


def open_location(principal: Principal, case: dict[str, Any], assignments: list[dict[str, Any]]) -> SharedLocation:
    if not _is_responder_case(principal, case, assignments):
        raise NotAllowed("Only the Police or Social Welfare handling this case can see a shared location.")
    contact = contact_for(case["$id"]) or {}
    if not contact.get("exactLocation"):
        raise NoLocation(case["$id"])
    team = principal.recipient or ""
    note = f"Location viewed by {RECIPIENT_NAMES.get(team, team)}."
    entry = CaseEntry(CaseHistoryAction.LOCATION_VIEWED, actor(principal), to_recipient=team, note=note)
    case_history.record(case["$id"], entry)
    stored = json.loads(contact["exactLocation"])
    return SharedLocation(stored.get("address"), stored.get("latitude"), stored.get("longitude"), contact["exactLocationAt"])


def views(case_id: str) -> list[dict[str, str]]:
    """The service, never the person."""
    return [
        {"by": RECIPIENT_NAMES.get(entry.get("toDept") or "", "A responding service"), "at": entry["timestamp"]}
        for entry in case_history.entries_for(case_id)
        if entry["action"] == CaseHistoryAction.LOCATION_VIEWED
    ]
