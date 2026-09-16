"""Figures the Assembly's documents once reported and haven't since.

The publishing record asks whether a required document exists. This asks a
different question: the document exists, it carries a figure the public needs,
and nothing published since gives that figure again. Accra's most recent
published domestic violence figures are from 2018, in the 2020 Voluntary Local
Review; Ask found them, and found nothing newer.

The findings are in app/data/reporting_gaps.json, each with the passage it comes
from, what was searched for and when, so a reader can check it rather than take
it on trust. Each writes its own headline, with {years} for the only part that
changes with time; a sentence is never composed out of a label, which is how
"domestic violence cases in Accra" once became "…domestic violence cases in
accra figures are 8 years old". They are Nokware's own reading, not a statutory list: a gap says
what the newest published figure is, never that the Assembly broke a duty. A gap
is shown only while its document is still published in the Ledger, so the
quotation always has a document behind it.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.ledger_documents import LedgerStatus, find_document

DATA = Path(__file__).resolve().parents[1] / "data" / "reporting_gaps.json"


YEARS = "{years}"


@dataclass(frozen=True)
class Gap:
    id: str
    subject: str  # a short label for the finding, never slotted into a sentence
    headline: str
    latest_year: int
    years_since: int
    figures: str
    quote: str
    document_id: str
    document_title: str
    searched: list[str]
    checked: str
    why: str


@lru_cache
def _data() -> dict[str, Any]:
    return json.loads(DATA.read_text())


def about() -> str:
    return str(_data()["about"])


def _headline(entry: dict[str, Any], years: int) -> str:
    """The finding's own sentence, with the one part that changes with time filled in."""
    return str(entry["headline"]).replace(YEARS, f"{years} years" if years != 1 else "a year")


def _gap(entry: dict[str, Any], now: datetime) -> Gap | None:
    record = find_document(entry["document_id"])
    if not record or record.get("status") != LedgerStatus.PUBLISHED:
        return None  # never quote a document a reader can't open
    years_since = now.year - int(entry["latest_year"])
    return Gap(
        id=entry["id"],
        subject=entry["subject"],
        headline=_headline(entry, years_since),
        latest_year=entry["latest_year"],
        years_since=years_since,
        figures=entry["figures"],
        quote=entry["quote"],
        document_id=entry["document_id"],
        document_title=record.get("title") or "Untitled",
        searched=list(entry["searched"]),
        checked=entry["checked"],
        why=entry["why"],
    )


def gaps(now: datetime) -> list[Gap]:
    """Each finding whose document is still published, oldest figures first."""
    found = [gap for entry in _data()["gaps"] if (gap := _gap(entry, now))]
    return sorted(found, key=lambda gap: gap.latest_year)
