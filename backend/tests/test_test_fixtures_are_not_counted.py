"""A test report is filed and worked like any other, and counted in no public figure.

A dashboard of scripted reports presented as what residents reported is the same
fabrication as a backdated history, just laundered through a prefix nobody sees on
the public page — descriptions never appear there, so "[TEST]" would be invisible.
"""

from typing import Any

import pytest

from app.services import issue_voices, stats
from app.services.citizen_reports import TEST_PREFIX

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
