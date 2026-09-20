"""Which published documents the deadline job re-ingests."""

from datetime import UTC, datetime, timedelta

from app.services.portal_actions import INGESTION_GRACE, INGESTION_RETRY_AFTER, needs_ingestion

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def record(**fields: object) -> dict[str, object]:
    return {"status": "published", "ingestedAt": None, "ingestionError": None, **fields}


def ago(delta: timedelta) -> str:
    return (NOW - delta).isoformat()


def test_a_fresh_publication_gets_time_to_finish() -> None:
    assert not needs_ingestion(record(publishedAt=ago(INGESTION_GRACE - timedelta(minutes=1))), NOW)
    assert needs_ingestion(record(publishedAt=ago(INGESTION_GRACE)), NOW)


def test_a_failure_is_retried_only_after_the_retry_interval() -> None:
    failed = {"ingestionError": "RuntimeError: embed failed", "publishedAt": ago(timedelta(days=1))}
    assert not needs_ingestion(record(**failed, **{"$updatedAt": ago(timedelta(minutes=5))}), NOW)
    assert needs_ingestion(record(**failed, **{"$updatedAt": ago(INGESTION_RETRY_AFTER)}), NOW)


def test_indexed_or_unpublished_documents_are_left_alone() -> None:
    assert not needs_ingestion(record(ingestedAt=ago(timedelta(days=1)), publishedAt=ago(timedelta(days=1))), NOW)
    assert not needs_ingestion(record(status="held", publishedAt=None), NOW)
