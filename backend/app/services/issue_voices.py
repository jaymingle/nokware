"""Add your voice: residents saying an open civic issue affects them too. A count, not a petition.

Only civic-service issues, and only while open: never public safety, never
personal safety. The public sees each issue's topic, electoral area,
department, status and count, never the citizen's words or photos. A voice is
anonymous unless the resident adds a name; a name reaches the handling
department only, and is deleted 30 days after the case closes, on the same
schedule as the citizen's numbers.

One voice per browser per issue: the browser sends a random token it keeps,
and only a hash of token and case is stored, under a unique index. The counts
are not verified signatures, and the page says so.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Any

from appwrite.exception import AppwriteException
from appwrite.id import ID
from appwrite.query import Query

from app.services import report_store
from app.services.appwrite_client import DATABASE_ID, as_record, every_record, get_databases
from app.services.citizen_reports import REPORTS_COLLECTION, VOICE_NAME_MAX, VOICES_COLLECTION
from app.services.locks import record_lock
from app.services.report_taxonomy import Category
from app.services.stats import OPEN
from app.services.workflow import WrongState

logger = logging.getLogger(__name__)

ISSUE_FIELDS = ["publicId", "category", "isSensitive", "topic", "wardLocation", "subMetro", "recipients", "status",
                "createdAt", "voiceCount"]
TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


class IssueNotFound(Exception):
    """No public issue has that ID: it doesn't exist, or it isn't a civic-service report."""


class InvalidVoice(ValueError):
    """The voice can't be taken as sent (a name too long, a malformed browser token)."""


def is_public_issue(case: dict[str, Any]) -> bool:
    """Civic service, not private, open, and given a public ID."""
    return (
        case.get("category") == Category.CIVIC_SERVICE
        and not case.get("isSensitive")
        and case.get("status") in OPEN
        and bool(case.get("publicId"))
    )


def list_issues(sub_metro: str | None, topic: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    """Open civic issues, most supported first, then newest."""
    queries = [
        Query.equal("category", Category.CIVIC_SERVICE.value),
        Query.equal("isSensitive", False),
        Query.equal("status", [s.value for s in OPEN]),
        Query.is_not_null("publicId"),
        *([Query.equal("subMetro", sub_metro)] if sub_metro else []),
        *([Query.equal("topic", topic)] if topic else []),
        Query.select(ISSUE_FIELDS),
        Query.order_desc("voiceCount"),
        Query.order_desc("createdAt"),
        Query.limit(limit),
        Query.offset(offset),
    ]
    listing = get_databases().list_documents(DATABASE_ID, REPORTS_COLLECTION, queries=queries)
    return [as_record(d) for d in listing.documents], int(listing.total)


def find_issue(public_id: str) -> dict[str, Any]:
    """An open civic issue by its public ID. Anything that isn't a civic-service report is simply not found."""
    listing = get_databases().list_documents(
        DATABASE_ID, REPORTS_COLLECTION, queries=[Query.equal("publicId", public_id), Query.limit(1)]
    )
    case = as_record(listing.documents[0]) if listing.documents else None
    if case is None or case.get("category") != Category.CIVIC_SERVICE or case.get("isSensitive"):
        raise IssueNotFound(public_id)
    if not is_public_issue(case):
        raise WrongState("This issue has been resolved, so it no longer takes new voices.")
    return case


def device_hash(case_id: str, token: str) -> str:
    return hashlib.sha256(f"{case_id}:{token}".encode()).hexdigest()


def _clean(token: str, name: str | None) -> str | None:
    if not TOKEN.match(token):
        raise InvalidVoice("This browser couldn't be recognised. Reload the page and try again.")
    given = (name or "").strip() or None
    if given and len(given) > VOICE_NAME_MAX:
        raise InvalidVoice(f"Keep the name under {VOICE_NAME_MAX} characters.")
    return given


def voices_total(case_id: str) -> int:
    listing = get_databases().list_documents(
        DATABASE_ID, VOICES_COLLECTION, queries=[Query.equal("caseId", case_id), Query.limit(1)]
    )
    return int(listing.total)


def _record_voice(case_id: str, token: str, name: str | None, now: datetime) -> bool:
    """Store one voice; False if this browser already added one to this issue."""
    data = {"caseId": case_id, "named": name is not None, "name": name, "deviceHash": device_hash(case_id, token),
            "createdAt": now.isoformat()}
    try:
        get_databases().create_document(DATABASE_ID, VOICES_COLLECTION, ID.unique(), data)
    except AppwriteException as exc:
        if exc.code == 409:
            return False
        raise
    return True


def add_voice(public_id: str, token: str, name: str | None, now: datetime) -> tuple[int, bool]:
    """Add a resident's voice to an open civic issue. Returns (the issue's count, whether this one was new)."""
    given = _clean(token, name)
    case = find_issue(public_id)
    with record_lock(case["$id"]):
        added = _record_voice(case["$id"], token, given, now)
        count = voices_total(case["$id"])  # recounted, so the stored count heals itself
        report_store.update_case(case["$id"], {"voiceCount": count})
    return count, added


def _named_rows(case_id: str) -> list[dict[str, Any]]:
    # Filtered on the "named" flag: an encrypted attribute (the name) can't be queried.
    return every_record(VOICES_COLLECTION, [Query.equal("caseId", case_id), Query.equal("named", True), Query.select(["name"])])


def named_voices(case_id: str) -> list[str]:
    """The names residents gave, for the handling department only."""
    return [row["name"] for row in _named_rows(case_id) if row.get("name")]  # a deleted name leaves None


def sync_voice_retention(case_id: str, purge_at: datetime | None) -> None:
    """Names given with a case's voices are deleted when its citizen's numbers are: 30 days after it closes."""
    change = {"purgeAt": purge_at.isoformat() if purge_at else None}
    for row in _named_rows(case_id):
        get_databases().update_document(DATABASE_ID, VOICES_COLLECTION, row["$id"], change)


def purge_expired_voice_names(now: datetime) -> int:
    """Delete every name whose retention has ended. The voice itself, anonymous now, still counts."""
    queries = [Query.equal("named", True), Query.is_not_null("purgeAt"), Query.less_than_equal("purgeAt", now.isoformat())]
    rows = every_record(VOICES_COLLECTION, [*queries, Query.select(["caseId"])])
    for row in rows:
        get_databases().update_document(DATABASE_ID, VOICES_COLLECTION, row["$id"], {"name": None, "purgeAt": None})
    if rows:
        logger.info("Deleted %d name(s) given with voices on closed cases", len(rows))
    return len(rows)
