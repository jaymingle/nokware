"""Figures the Assembly's documents once reported and haven't since.

Each finding in app/data/reporting_gaps.json carries its passage and what was searched for and when, so a reader
can check it rather than take it on trust. Each writes its own headline: a sentence composed out of a label once
read "domestic violence cases in accra figures are 8 years old". They are Nokware's own reading, not a statutory
list: a gap says what the newest published figure is, never that the Assembly broke a duty.
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
    found = [gap for entry in _data()["gaps"] if (gap := _gap(entry, now))]
    return sorted(found, key=lambda gap: gap.latest_year)
