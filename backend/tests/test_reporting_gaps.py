"""Figures the Assembly's documents once reported and haven't since: shown with their evidence, or not at all."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.services import reporting_gaps
from app.services.ledger_documents import LedgerStatus

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
VLR = {"title": "The City of Accra 2020 Voluntary Local Review", "status": LedgerStatus.PUBLISHED}


def found(monkeypatch: pytest.MonkeyPatch, record: dict[str, Any] | None) -> list[reporting_gaps.Gap]:
    monkeypatch.setattr(reporting_gaps, "find_document", lambda document_id: record)
    return reporting_gaps.gaps(NOW)


def test_the_domestic_violence_gap_says_how_old_the_newest_figures_are(monkeypatch: pytest.MonkeyPatch) -> None:
    gap = found(monkeypatch, VLR)[0]
    assert gap.headline == "Accra's most recent published domestic violence figures are 8 years old"
    assert gap.subject == "Domestic violence" and gap.latest_year == 2018 and gap.years_since == 8
    assert "12 cases in 2016" in gap.quote and gap.document_title == VLR["title"]
    assert "DOVVSU" in gap.searched and gap.checked == "2026-09-16"


@pytest.mark.parametrize("record", [None, {"title": "Withdrawn", "status": LedgerStatus.DISPUTED}])
def test_a_gap_whose_document_a_reader_cannot_open_is_not_shown(monkeypatch: pytest.MonkeyPatch, record: dict[str, Any] | None) -> None:
    """The quotation always has a published document behind it, or the finding isn't made."""
    assert found(monkeypatch, record) == []


def test_every_gap_carries_what_was_searched_and_when(monkeypatch: pytest.MonkeyPatch) -> None:
    for gap in found(monkeypatch, VLR):
        assert gap.searched and gap.checked and gap.quote and gap.why
        assert gap.years_since == NOW.year - gap.latest_year


def test_each_finding_writes_its_own_sentence_rather_than_having_one_composed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A headline built by slotting a label into a template read "…domestic violence cases in accra figures are…"."""
    for entry in reporting_gaps._data()["gaps"]:
        assert entry["headline"].count("{") == 1 and reporting_gaps.YEARS in entry["headline"]
    for gap in found(monkeypatch, VLR):
        assert "{" not in gap.headline and "}" not in gap.headline
        assert gap.headline[0].isupper() and gap.headline[-1].isalnum()


def test_one_year_reads_as_a_year_not_1_years() -> None:
    entry = reporting_gaps._data()["gaps"][0]
    assert reporting_gaps._headline(entry, 1).endswith("are a year old")
    assert reporting_gaps._headline(entry, 3).endswith("are 3 years old")
