"""How the MCE has handled petitions over the last twelve months, for the departmental responsiveness page.

Two parts:
- the review: petitions sent, published by the MCE, published automatically
  because the MCE let 72 hours pass, and refused, by reason (decisions made in
  the period, from the trail);
- the response: every petition that reached its threshold in the period, and
  where it stands: answered within 30 days, answered late, not answered after 30
  days, or still within them. The four add up to the number that reached it.

Exact counts, not "fewer than 5": they count the MCE's decisions on public
petitions, not residents, so there is no one to protect by hiding a small
number, and hiding it would hide exactly the silence the page exists to show.
"""

from collections import Counter
from datetime import datetime
from typing import Any

from appwrite.query import Query

from app.services.appwrite_client import every_record
from app.services.ledger_documents import parse_datetime
from app.services.petition_rules import REFUSALS, PetitionAction, PetitionStatus, responded_late
from app.services.petitions import HISTORY_COLLECTION, NOT_TEST, PETITIONS_COLLECTION, test_petition_ids

REVIEW_ACTIONS = (PetitionAction.SUBMITTED, PetitionAction.PUBLISHED, PetitionAction.AUTO_PUBLISHED, PetitionAction.REFUSED)
RESPONSE_FIELDS = ["status", "thresholdReachedAt", "responseDue", "respondedAt", "noResponseAt"]


def _in(moment: str | None, start: datetime) -> bool:
    at = parse_datetime(moment)
    return at is not None and at >= start


def standing(petition: dict[str, Any], now: datetime) -> str:
    """Where a petition that reached its threshold stands with the MCE."""
    if petition.get("status") == PetitionStatus.RESPONDED:
        return "answered_late" if responded_late(petition) else "answered_in_time"
    due = parse_datetime(petition.get("responseDue"))
    return "unanswered" if due is not None and due <= now else "waiting"


def build(history: list[dict[str, Any]], reached: list[dict[str, Any]], start: datetime, now: datetime) -> dict[str, Any]:
    decisions = Counter(e["action"] for e in history if _in(e.get("at"), start))
    refusals = Counter(e.get("reason") for e in history if e["action"] == PetitionAction.REFUSED and _in(e.get("at"), start))
    standings = Counter(standing(p, now) for p in reached if _in(p.get("thresholdReachedAt"), start))
    return {
        "sent": decisions[PetitionAction.SUBMITTED], "published_by_mce": decisions[PetitionAction.PUBLISHED],
        "published_automatically": decisions[PetitionAction.AUTO_PUBLISHED], "refused": decisions[PetitionAction.REFUSED],
        "refusals": [{"reason": key, "label": r.label, "count": refusals.get(key, 0)} for key, r in REFUSALS.items()],
        "reached_threshold": sum(standings.values()), "answered_in_time": standings["answered_in_time"],
        "answered_late": standings["answered_late"], "unanswered": standings["unanswered"], "waiting": standings["waiting"],
    }


def figures(start: datetime, now: datetime) -> dict[str, Any]:
    """The MCE's handling of residents' petitions, test petitions left out: a count of the MCE deciding fixtures would
    be a record of decisions that were never about a resident's petition."""
    tests = test_petition_ids()
    history = [row for row in every_record(HISTORY_COLLECTION, [Query.equal("action", [a.value for a in REVIEW_ACTIONS]),
                                                                 Query.select(["action", "reason", "at", "petitionId"])])
               if row.get("petitionId") not in tests]
    reached = every_record(PETITIONS_COLLECTION, [Query.is_not_null("thresholdReachedAt"), NOT_TEST, Query.select(RESPONSE_FIELDS)])
    return build(history, reached, start, now)
