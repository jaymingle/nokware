"""Aggregate statistics over citizen reports (Appwrite).

These are plain, typed functions that return only aggregate counts — never raw
case content. They are designed so a thin MCP wrapper can expose them later
without changing their internals.

Privacy rule (baked in): the ``personal_safety`` category is never broken down
by ward. ``count_reports_by_ward`` therefore excludes personal-safety cases, so
a ward-level count can never expose (or single out) a personal-safety report.
City-wide personal-safety totals remain available via the category/top helpers.
"""

from datetime import datetime, timedelta, timezone

from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, get_databases

COLLECTION_ID = "citizen_reports"
PERSONAL_SAFETY = "personal_safety"
CATEGORIES = ("civic_service", "public_safety", PERSONAL_SAFETY)
_LAST_MONTH_DAYS = 30


def _count(queries: list[str]) -> int:
    """Return the total number of reports matching ``queries``.

    Appwrite reports the full match count in ``total`` regardless of the page
    size, so we fetch a single document and read ``total``. The SDK returns a
    ``DocumentList`` model (``total`` is a float), hence attribute access and
    the ``int`` cast.
    """
    result = get_databases().list_documents(
        DATABASE_ID, COLLECTION_ID, queries=[*queries, Query.limit(1)]
    )
    return int(result.total)


def count_reports_by_category(category: str, since: datetime | None = None) -> int:
    queries = [Query.equal("category", category)]
    if since is not None:
        queries.append(Query.greater_than_equal("createdAt", since.isoformat()))
    return _count(queries)


def count_reports_by_status(status: str, department: str | None = None) -> int:
    queries = [Query.equal("status", status)]
    if department is not None:
        queries.append(Query.equal("assignedDepartment", department))
    return _count(queries)


def count_reports_by_ward(ward: str, since: datetime | None = None) -> int:
    # Personal-safety cases are excluded so ward-level counts never expose them.
    queries = [
        Query.equal("wardLocation", ward),
        Query.not_equal("category", PERSONAL_SAFETY),
    ]
    if since is not None:
        queries.append(Query.greater_than_equal("createdAt", since.isoformat()))
    return _count(queries)


def top_categories_last_month(limit: int = 5) -> list[dict]:
    """City-wide category counts over the last 30 days, highest first."""
    since = datetime.now(timezone.utc) - timedelta(days=_LAST_MONTH_DAYS)
    counts = [
        {"category": category, "count": count_reports_by_category(category, since)}
        for category in CATEGORIES
    ]
    counts.sort(key=lambda row: row["count"], reverse=True)
    return counts[:limit]
