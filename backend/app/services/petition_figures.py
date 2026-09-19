"""What has happened to petitions over the last twelve months, for the departmental responsiveness page.

Two different things are counted here, and the page keeps them apart. What residents and contributors did —
petitions published, republished, removed and on which ground — nobody in the Assembly decides. What the MCE did is
the answering: in time, late, or not at all.

Exact counts, not "fewer than 5": they count public petitions and public decisions, not residents, so there is no
one to protect by hiding a small number, and hiding it would hide exactly the silence the page exists to show.
"""

from collections import Counter
from datetime import datetime
from typing import Any

from appwrite.query import Query

from app.services.appwrite_client import every_record
from app.services.ledger_documents import parse_datetime
from app.services.petition_grounds import Ground, in_plain_words
from app.services.petition_rules import PetitionAction, PetitionStatus, responded_late
from app.services.petitions import HISTORY_COLLECTION, NOT_TEST, PETITIONS_COLLECTION, test_petition_ids

COUNTED_ACTIONS = (PetitionAction.PUBLISHED, PetitionAction.REPUBLISHED, PetitionAction.REMOVED)
RESPONSE_FIELDS = ["status", "thresholdReachedAt", "responseDue", "respondedAt", "noResponseAt"]


def _in(moment: str | None, start: datetime) -> bool:
    at = parse_datetime(moment)
    return at is not None and at >= start


def standing(petition: dict[str, Any], now: datetime) -> str:
    if petition.get("status") == PetitionStatus.RESPONDED:
        return "answered_late" if responded_late(petition) else "answered_in_time"
    due = parse_datetime(petition.get("responseDue"))
    return "unanswered" if due is not None and due <= now else "waiting"


def build(history: list[dict[str, Any]], reached: list[dict[str, Any]], start: datetime, now: datetime) -> dict[str, Any]:
    steps = Counter(e["action"] for e in history if _in(e.get("at"), start))
    grounds = Counter(e.get("reason") for e in history if e["action"] == PetitionAction.REMOVED and _in(e.get("at"), start))
    standings = Counter(standing(p, now) for p in reached if _in(p.get("thresholdReachedAt"), start))
    return {
        "published": steps[PetitionAction.PUBLISHED], "republished": steps[PetitionAction.REPUBLISHED],
        "removed": steps[PetitionAction.REMOVED],
        "removals": [{"ground": g.value, "label": in_plain_words(g), "count": grounds.get(g.value, 0)} for g in Ground],
        "reached_threshold": sum(standings.values()), "answered_in_time": standings["answered_in_time"],
        "answered_late": standings["answered_late"], "unanswered": standings["unanswered"], "waiting": standings["waiting"],
    }


def figures(start: datetime, now: datetime) -> dict[str, Any]:
    """Test petitions are left out: what happened to a fixture never happened to a resident's petition."""
    tests = test_petition_ids()
    history = [row for row in every_record(HISTORY_COLLECTION, [Query.equal("action", [a.value for a in COUNTED_ACTIONS]),
                                                                 Query.select(["action", "reason", "at", "petitionId"])])
               if row.get("petitionId") not in tests]
    reached = every_record(PETITIONS_COLLECTION, [Query.is_not_null("thresholdReachedAt"), NOT_TEST, Query.select(RESPONSE_FIELDS)])
    return build(history, reached, start, now)
