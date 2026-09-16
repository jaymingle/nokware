"""A test report or document goes through the real pipeline, and reaches the public nowhere.

A dashboard of scripted reports presented as what residents reported, or an answer
citing a test document as the Assembly's, is the same fabrication as a backdated
history, just laundered through a prefix nobody sees on the public page.
"""

from typing import Any

import pytest

from app.services import issue_voices, stats
from app.services.test_fixtures import TEST_PREFIX, is_test

EXCLUDED = '{"method":"notStartsWith","attribute":"description","values":["[TEST]"]}'


def test_the_prefix_is_the_one_every_test_script_writes() -> None:
    assert TEST_PREFIX == "[TEST]"


def test_the_public_figures_never_read_a_test_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """One fetch feeds the dashboard, the map of areas, Ask's live counts, the MCP and the responsiveness page."""
    asked: list[list[str]] = []
    monkeypatch.setattr(stats, "every_record", lambda collection, queries: asked.append(queries) or [])
    stats._fetch_public_cases()
    assert EXCLUDED in asked[0]


def test_the_issues_residents_raised_list_no_test_report(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[list[str]] = []

    class Listing:
        documents: list[Any] = []
        total = 0

    class Databases:
        def list_documents(self, database: str, collection: str, queries: list[str]) -> Listing:
            asked.append(queries)
            return Listing()

    monkeypatch.setattr(issue_voices, "get_databases", lambda: Databases())
    issue_voices.list_issues(None, None, 10, 0)
    assert EXCLUDED in asked[0]


def test_a_prefixed_title_or_description_is_a_fixture_and_nothing_else_is() -> None:
    assert is_test("[TEST] Annual Report 2024") and is_test("  [TEST] drain") and not is_test("The [TEST] of time")
    assert not is_test(None) and not is_test("")


def test_a_test_document_is_never_a_public_document() -> None:
    """The portal's lifecycle test publishes documents so ingestion is tested for real. Without this an answer could
    cite "[TEST] Annual Report" to a resident as the Assembly's."""
    from app.services.ledger_documents import LedgerStatus, is_public_document

    assert is_public_document({"status": LedgerStatus.PUBLISHED, "title": "2026 AMA Budget"})
    assert not is_public_document({"status": LedgerStatus.PUBLISHED, "title": "[TEST] Annual Report 2024"})
    assert not is_public_document({"status": LedgerStatus.HELD, "title": "2026 AMA Budget"})
    assert not is_public_document(None)


def test_answers_never_retrieve_a_test_document(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import ledger_documents, retrieval
    from app.services.ledger_documents import LedgerStatus
    from app.services.retrieval import Chunk

    chunks = [(Chunk("c1", "real", 0, "Stall fees are GH¢ 50."), 1.0), (Chunk("c2", "fixture", 0, "Stall fees are GH¢ 999."), 0.9)]
    monkeypatch.setattr(retrieval, "expand_query", lambda question: [question])
    monkeypatch.setattr(retrieval, "ranked_lists", lambda queries: ([[c for c, _ in chunks]], []))
    monkeypatch.setattr(retrieval, "fuse", lambda lists: chunks)
    monkeypatch.setattr(ledger_documents, "get_documents", lambda ids: {
        "real": {"status": LedgerStatus.PUBLISHED, "title": "2026 Fee-Fixing Resolution"},
        "fixture": {"status": LedgerStatus.PUBLISHED, "title": "[TEST] 2026 Fee-Fixing Resolution"},
    })
    found = retrieval.retrieve("What do stalls cost?")
    assert [hit.chunk.document_id for hit in found.chunks] == ["real"]


def test_the_count_of_documents_published_leaves_test_documents_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is the "164 documents" on the landing page and the dashboard, and the dashboard's recent documents."""
    from app.services import ledger_documents, report_dashboard

    asked: list[list[str]] = []
    monkeypatch.setattr(ledger_documents, "list_documents", lambda queries: asked.append(queries) or ([], 0))
    monkeypatch.setattr(report_dashboard, "every_record", lambda collection, queries: asked.append(queries) or [])
    report_dashboard.ledger_figures()
    excluded = '{"method":"notStartsWith","attribute":"title","values":["[TEST]"]}'
    assert all(excluded in queries for queries in asked) and len(asked) == 2
