"""Every version of a petition's words, kept.

A petition can be edited after people have signed it, which is only honest if what they signed is still readable.
So each publication — the first, every edit, every republication after a removal — writes a row here and nothing
overwrites one. The petition itself carries the latest version's words and its number; a signature carries the
number it was signed on, so a page can say how many signatures stand on words that have since changed.
"""

from datetime import datetime
from typing import Any

from appwrite.id import ID
from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, every_record, get_databases

VERSIONS_COLLECTION = "petition_versions"
# The words a version is made of. A change to any of them is a new version; everything else about a petition — its
# signatures, its status, the MCE's answer — belongs to the petition, not to one wording of it.
VERSIONED = ("title", "body", "topic", "scope", "wardLocation", "imageIds")


def record_version(petition_id: str, fields: dict[str, Any], number: int, at: datetime) -> None:
    """Callers hold the petition's lock: a version is written in the same breath as the change it records."""
    words = {key: fields.get(key) for key in VERSIONED}
    get_databases().create_document(DATABASE_ID, VERSIONS_COLLECTION, ID.unique(),
                                    {**words, "petitionId": petition_id, "version": number, "at": at.isoformat()})


def versions_of(petition_id: str) -> list[dict[str, Any]]:
    """Oldest first, as an edit history reads."""
    return every_record(VERSIONS_COLLECTION, [Query.equal("petitionId", petition_id), Query.order_asc("version")])


def what_changed(earlier: dict[str, Any] | None, version: dict[str, Any]) -> list[str]:
    """Which of the words changed, for a history that says "the reasons were rewritten" rather than only "edited"."""
    if earlier is None:
        return []
    return [key for key in VERSIONED if (earlier.get(key) or None) != (version.get(key) or None)]


def history(petition_id: str) -> list[tuple[dict[str, Any], list[str]]]:
    """Each version with what it changed from the one before it."""
    versions = versions_of(petition_id)
    return [(version, what_changed(versions[position - 1] if position else None, version))
            for position, version in enumerate(versions)]
