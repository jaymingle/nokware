"""The publishing record: what the Assembly is required to publish, against what the Ledger holds, year by year.

Accountability rather than retrieval: it shows the gaps as well as the contents.
The required documents, their groups, cadences and title patterns are in
app/data/statutory_documents.json. Each period (a year, a quarter, or a 4-year
plan period) is one of:

- held: the Ledger holds the document itself;
- related: it holds documents about the same thing, but not the document itself
  (a monitoring and evaluation report is not an Annual Progress Report);
- missing: neither, once the document is expected;
- not_due: not yet expected, by our conservative assumption of when it is due
  ("expected" in the data file), which is not a statutory deadline.

A missing document is "not found in ama.gov.gh's Documents Centre and not in
The Ledger", never "does not exist": it may exist and simply not be online. The
Ledger holds everything imported from the Documents Centre, so absent from the
Ledger means absent from the Documents Centre when it was last checked. Beside a
gap, the record lists what the Ledger does hold from the same departments or
categories that year.

Titles mislead: the file titled "2022 Composite Budget" is the budget's chart-of-
account annex. Where the data file gives "cover" rules, a document's own first
page decides what it is, and says why ("Its first page reads …"). Each document
also says where its year came from (its first page, its title, the Ledger's
record, or a person), so a year taken from the Ledger's record rather than the
document can be marked as such. Documents issued by someone else (the Auditor-General,
Parliament) say so; a Public Accounts Committee report has no fixed schedule, so
no year of it is ever called missing.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from appwrite.query import Query

from app.services import ledger_documents
from app.services.appwrite_client import every_record
from app.services.ledger_documents import LedgerStatus, plausible_year, year_from_title
from app.services.report_dashboard import _Cache
from app.services.vectorstore import first_chunks
from app.teams import DEPARTMENT_NAMES

DATA = Path(__file__).resolve().parents[1] / "data" / "statutory_documents.json"
NEARBY_SHOWN = 6
CACHE = _Cache(600)
_QUARTERS = (
    (1, re.compile(r"\b(first|1st|q1)\b|\bjan(uary)?\b.{0,6}\bmar(ch)?\b", re.IGNORECASE)),
    (2, re.compile(r"\b(second|2nd|q2)\b|\bapr(il)?\b.{0,6}\bjune?\b", re.IGNORECASE)),
    (3, re.compile(r"\b(third|3rd|q3)\b|\bjul(y)?\b.{0,6}\bsep(t|tember)?\b", re.IGNORECASE)),
    (4, re.compile(r"\b(fourth|forth|4th|q4)\b|\boct(ober)?\b.{0,6}\bdec(ember)?\b", re.IGNORECASE)),
)


@dataclass(frozen=True)
class Period:
    label: str  # "2024", "Q2 2024", "2022–2025"
    year: int  # the first year it covers
    quarter: int | None
    start: datetime
    end: datetime  # the first moment after it


@lru_cache
def rules() -> dict[str, Any]:
    return json.loads(DATA.read_text())


def _moment(year: int, month: int = 1) -> datetime:
    return datetime(year + (month - 1) // 12, (month - 1) % 12 + 1, 1, tzinfo=timezone.utc)


def periods(requirement: dict[str, Any], now: datetime) -> list[Period]:
    """The periods the record covers: from the first year to now (a plan period reaching into this range counts)."""
    first, last = rules()["first_year"], now.year
    if requirement["cadence"] == "annual":
        return [Period(str(y), y, None, _moment(y), _moment(y + 1)) for y in range(first, last + 1)]
    if requirement["cadence"] == "quarterly":
        return [Period(f"Q{q} {y}", y, q, _moment(y, 3 * q - 2), _moment(y, 3 * q + 1)) for y in range(first, last + 1) for q in range(1, 5)]
    if requirement["cadence"] == "plan_period":
        span = requirement["plan_years"]
        starts = [s for s in requirement["plan_starts"] if s + span - 1 >= first and s <= last]
        return [Period(f"{s}–{s + span - 1}", s, None, _moment(s), _moment(s + span)) for s in starts]
    return []  # as issued: no schedule, so no period can be missing


def expected_from(requirement: dict[str, Any], period: Period) -> datetime | None:
    """When the document counts as expected: our conservative assumption, not a statutory deadline."""
    rule = requirement.get("expected")
    if not rule:
        return None
    if rule["from"] == "start":
        return period.start
    months = rule.get("months", 0)
    return _moment(period.end.year, period.end.month + months)


def expected_note(requirement: dict[str, Any]) -> str | None:
    rule = requirement.get("expected")
    if not rule:
        return None
    unit = {"annual": "year", "quarterly": "quarter", "plan_period": "plan period"}[requirement["cadence"]]
    if rule["from"] == "start":
        return f"Expected from the start of the {unit} it covers"
    months = rule.get("months", 0)
    return f"Expected by the end of the {unit}" if months == 0 else f"Expected {months} months after the {unit} ends"


def year_and_source(document: dict[str, Any]) -> tuple[int | None, str | None]:
    """The year a document covers, and where that came from: a person, its first page, its title (a report filed
    later still covers its own year), or the Ledger's record."""
    for source, year in (("confirmed", document.get("_confirmed_year")), ("cover", document.get("_cover_year")),
                         ("title", year_from_title(document.get("title") or "")), ("ledger", plausible_year(document.get("documentYear")))):
        if year:
            return year, source
    return None, None


def document_year(document: dict[str, Any]) -> int | None:
    return year_and_source(document)[0]


def quarter_of(title: str) -> int | None:
    return next((q for q, pattern in _QUARTERS if pattern.search(title)), None)


def _brief(document: dict[str, Any]) -> dict[str, Any]:
    year, source = year_and_source(document)
    return {"id": document["$id"], "title": document["title"].strip(), "year": year, "year_source": source,
            "department_name": DEPARTMENT_NAMES.get(document.get("department") or ""), "note": document.get("_note")}


def _in_period(document: dict[str, Any], period: Period, requirement: dict[str, Any]) -> bool:
    year = document_year(document)
    if requirement["cadence"] == "quarterly":
        return year == period.year and quarter_of(document["title"]) == period.quarter
    last = period.end.year - 1 if period.end.month == 1 else period.end.year
    return year is not None and period.start.year <= year <= last


def _pattern(requirement: dict[str, Any], key: str) -> re.Pattern[str] | None:
    return re.compile(requirement[key], re.IGNORECASE) if requirement.get(key) else None


def _by_cover(requirement: dict[str, Any], document: dict[str, Any], first_page: str | None) -> tuple[str, dict[str, Any]] | None:
    """What the document's own first page says it is, where the requirement has cover rules: ("own" or "near",
    the document with its year and why), or None to fall back on its title."""
    cover = requirement.get("cover")
    if not cover or not first_page:
        return None
    text = " ".join(first_page.split())
    held = re.search(cover["match"], text, re.IGNORECASE)
    if held:
        return "own", {**document, "_cover_year": int(held.group(1)), "_note": cover["held_note"].format(year=held.group(1))}
    if re.search(cover["related"], text, re.IGNORECASE):
        return "near", {**document, "_note": cover["related_note"]}
    return None


def classify(requirement: dict[str, Any], documents: list[dict[str, Any]],
             first_pages: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The requirement's own documents and its related ones: a person's confirmation first, then the document's own
    first page, then its title."""
    confirmed = rules()["confirmed"]
    match, related = _pattern(requirement, "match"), _pattern(requirement, "related")
    own, near = [], []
    for document in documents:
        decided = confirmed.get(document["$id"], ...)
        if decided is not ...:
            if decided and decided[0] == requirement["id"]:
                own.append({**document, "_confirmed_year": decided[1]})
            continue
        by_cover = _by_cover(requirement, document, (first_pages or {}).get(document["$id"]))
        if by_cover:
            (own if by_cover[0] == "own" else near).append(by_cover[1])
        elif match and match.search(document["title"]):
            own.append(document)
        elif related and related.search(document["title"]):
            near.append(document)
    return own, near


def _nearby(requirement: dict[str, Any], year: int, documents: list[dict[str, Any]], shown: set[str]) -> list[dict[str, Any]]:
    """What the Ledger does hold that year from the requirement's departments or categories."""
    return [d for d in documents if d["$id"] not in shown and document_year(d) == year
            and (d.get("department") in requirement["departments"] or d.get("category") in requirement["categories"])]


def _period_row(requirement: dict[str, Any], period: Period, own: list[dict[str, Any]], near: list[dict[str, Any]],
                documents: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    held = [d for d in own if _in_period(d, period, requirement)]
    related = [d for d in near if _in_period(d, period, requirement)]
    if requirement["cadence"] == "quarterly":  # a report for the year whose quarter isn't stated is related, not held
        related += [d for d in own if document_year(d) == period.year and quarter_of(d["title"]) is None]
    expected = expected_from(requirement, period)
    state = "held" if held else "not_due" if expected and now < expected else "related" if related else "missing"
    nearby = [] if held else _nearby(requirement, period.year, documents, {d["$id"] for d in [*own, *near]})
    return {
        "label": period.label, "year": period.year, "quarter": period.quarter, "state": state,
        "expected_from": expected.date().isoformat() if expected else None,
        "documents": [_brief(d) for d in held], "related": [_brief(d) for d in related],
        "nearby": [_brief(d) for d in nearby[:NEARBY_SHOWN]], "nearby_total": len(nearby),
    }


def _requirement_row(requirement: dict[str, Any], documents: list[dict[str, Any]], now: datetime,
                     first_pages: dict[str, str]) -> dict[str, Any]:
    own, near = classify(requirement, documents, first_pages)
    rows = [_period_row(requirement, p, own, near, documents, now) for p in periods(requirement, now)]
    undated = [d for d in own if document_year(d) is None]
    return {
        "id": requirement["id"], "name": requirement["name"], "cadence": requirement["cadence"],
        "issued_by": requirement.get("issued_by"), "expected_note": expected_note(requirement),
        "nearby_scope": _scope(requirement), "periods": rows, "undated": [_brief(d) for d in undated],
        "held": [_brief(d) for d in own] if requirement["cadence"] == "as_issued" else [],
    }


def _scope(requirement: dict[str, Any]) -> str:
    """Where "what the Ledger holds" looks: "Budget & Rating, Finance or Budget And Fee Fixing"."""
    names = [DEPARTMENT_NAMES[d] for d in requirement["departments"]] + list(requirement["categories"])
    return ", ".join(names[:-1]) + (f" or {names[-1]}" if len(names) > 1 else "".join(names))


def _summary(groups: list[dict[str, Any]]) -> dict[str, int]:
    states = [p["state"] for g in groups for r in g["requirements"] for p in r["periods"]]
    return {"due": sum(s != "not_due" for s in states), **{s: states.count(s) for s in ("held", "related", "missing", "not_due")}}


def published_documents() -> list[dict[str, Any]]:
    """The Ledger's published documents, test documents left out."""
    records = every_record(ledger_documents.COLLECTION_ID, [Query.equal("status", LedgerStatus.PUBLISHED.value)])
    return [r for r in records if not (r.get("title") or "").lstrip().startswith("[TEST]")]


def build(documents: list[dict[str, Any]], now: datetime, first_pages: dict[str, str] | None = None) -> dict[str, Any]:
    data = rules()
    pages = first_pages or {}
    groups = [{"id": g["id"], "name": g["name"],
               "requirements": [_requirement_row(r, documents, now, pages) for r in data["requirements"] if r["group"] == g["id"]]}
              for g in data["groups"]]
    return {
        "generated_at": now.isoformat(), "documents_centre": data["documents_centre"],
        "documents_centre_checked": data["documents_centre_checked"], "first_year": data["first_year"],
        "last_year": now.year, "groups": groups, "summary": _summary(groups),
    }


def publishing_record(now: datetime) -> dict[str, Any]:
    """The record, at most ten minutes old."""
    return CACHE.get(lambda: build(published_documents(), now, first_chunks()))
