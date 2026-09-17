"""The petition clock: what happens to a petition when no one acts.

Every change re-reads the petition under its lock first, in case someone acted a moment before.
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from appwrite.query import Query

from app.services import petition_updates, petitions
from app.services.locks import record_lock
from app.services.petition_rules import (
    PetitionAction,
    PetitionStatus,
    PublishedBy,
    closing_due,
    publish_fields,
    response_overdue,
    review_expired,
)
from app.services.petition_updates import Update

logger = logging.getLogger(__name__)

JOB_BATCH = 100
Step = tuple[Callable[[dict[str, Any], datetime], bool], Callable[[dict[str, Any], datetime], dict[str, Any]], PetitionAction, Update]


def _due(queries: list[str]) -> list[dict[str, Any]]:
    found, _ = petitions.list_petitions([*queries, Query.limit(JOB_BATCH)])
    return found


def _apply(candidate: dict[str, Any], now: datetime, step: Step) -> bool:
    is_due, changes, action, update = step
    with record_lock(candidate["$id"]):
        petition = petitions.find(candidate["code"])
        if not is_due(petition, now):
            return False
        updated = petitions.update_petition(petition["$id"], changes(petition, now))
        petitions.record_history(updated, action, petitions.SYSTEM, petition["status"])
    petition_updates.notify_quietly(updated, update)
    return True


AUTO_PUBLISH: Step = (review_expired, lambda p, now: publish_fields(p, PublishedBy.AUTOMATIC, now, petitions.threshold_of(p)),
                      PetitionAction.AUTO_PUBLISHED, Update.AUTO_PUBLISHED)
CLOSE: Step = (closing_due, lambda p, now: petitions.finish_fields(PetitionStatus.CLOSED, now), PetitionAction.CLOSED, Update.CLOSED)
NO_RESPONSE: Step = (response_overdue, lambda p, now: {"noResponseAt": now.isoformat()}, PetitionAction.NO_RESPONSE, Update.NO_RESPONSE)


def run_clock(now: datetime) -> dict[str, list[str]]:
    at = now.isoformat()
    due = {
        "published": (_due([Query.equal("status", PetitionStatus.IN_REVIEW.value), Query.less_than_equal("reviewDeadline", at)]), AUTO_PUBLISH),
        "closed": (_due([Query.equal("status", PetitionStatus.OPEN.value), Query.less_than_equal("closesAt", at)]), CLOSE),
        "unanswered": (_due([Query.equal("status", PetitionStatus.AWAITING_RESPONSE.value), Query.less_than_equal("responseDue", at),
                             Query.is_null("noResponseAt")]), NO_RESPONSE),
    }
    done = {kind: [p["code"] for p in candidates if _apply(p, now, step)] for kind, (candidates, step) in due.items()}
    if any(done.values()):
        logger.info("Petition clock: %s", ", ".join(f"{len(codes)} {kind}" for kind, codes in done.items()))
    return done
