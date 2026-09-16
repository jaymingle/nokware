"""Budget figures for Ask: the same kind of question as the live report counts, over rows read from the documents.

The live figures answer "how many reports, broken down how". These answer "how
much was approved, broken down how" — by year, department, programme,
sub-programme, fund source or kind of spending, filtered on any of the same
things. A comparison is two calls: approved for Waste Management in 2022 and in
2026, or approved by department this year against last. Nothing here is special
to budgets as a topic; it is the same shape of question over a different set of
rows, which is what lets one answer compare the two.

What it will not do:

- **Invent a year.** Only the years in app/data/budget_lines.json exist (the
  Ledger holds no 2024 or 2025 budget), and a question about a year that isn't
  there is told so, not approximated from the years that are.
- **Hide what was left out.** Each figure says which document it comes from and
  what share of that document's own stated total the rows cover, so a share
  anyone takes is against a stated base.
- **Add across documents.** Each row belongs to one document, and totals are
  only ever within what that document details.

These are approved amounts. Released and actual spending are not in these
documents, and a question about them is answered as not available.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

DATA = Path(__file__).resolve().parents[1] / "data" / "budget_lines.json"
LABEL_PREFIX = "B"
NOT_AVAILABLE = "Nokware has no budget figures for that."
GROUPS = ("none", "year", "department", "program", "sub_program", "fund_source", "economic")
Grouping = Literal["none", "year", "department", "program", "sub_program", "fund_source", "economic"]


@lru_cache
def _data() -> dict[str, Any]:
    return json.loads(DATA.read_text()) if DATA.exists() else {"documents": [], "rows": []}


def rows() -> list[dict[str, Any]]:
    return list(_data()["rows"])


def years() -> list[int]:
    return sorted({int(row["year"]) for row in rows()})


def departments() -> list[str]:
    return sorted({str(row["department"]) for row in rows()})


def documents() -> list[dict[str, Any]]:
    return list(_data()["documents"])


def document_for(year: int) -> dict[str, Any] | None:
    return next((document for document in documents() if int(document["year"]) == year), None)


class BudgetFigures(BaseModel):
    """Approved budget amounts the Assembly published, for one year, broken down as asked.

    Call this once for each figure the answer needs: two calls compare two years, two departments, or the same
    department across years. Only the years Nokware holds can be asked for."""

    year: int = Field(description="The budget year the resident asks about. Call this even for a year Nokware may "
                                  "not hold: it will say which years it has rather than leave the gap unexplained.")
    department: str | None = Field(None, description="A department as the budget names it, e.g. Public Works.")
    program: str | None = Field(None, description="A programme, e.g. Management and Administration.")
    fund_source: str | None = Field(None, description="How it is paid for: GOG, IGF, DACF.")
    group_by: Grouping = Field("none", description="Break the amount down by year, department, program, "
                                                  "sub_program, fund_source or economic (the kind of spending).")


@dataclass(frozen=True)
class BudgetFigure:
    """One budget amount as a citable source: what it covers, the amount, and the document it is printed in."""

    label: str
    description: str
    value: str
    rows: list[tuple[str, str]]
    document_id: str
    document_title: str
    year: int
    coverage: str  # what the rows kept come to as a share of what the document says it details
    grouped_by: str = "none"


def cedis(amount: float) -> str:
    return f"GH¢ {amount:,.0f}"


def _matching(call: BudgetFigures) -> list[dict[str, Any]]:
    found = [row for row in rows() if int(row["year"]) == call.year]
    for field, value in (("department", call.department), ("program", call.program), ("fund_source", call.fund_source)):
        if value:
            wanted = value.strip().lower()
            found = [row for row in found if wanted in str(row[field]).lower()]
    return found


def describe(call: BudgetFigures) -> str:
    parts = ["Approved budget", str(call.year)]
    for value in (call.department, call.program, call.fund_source):
        if value:
            parts.append(value)
    if call.group_by != "none":
        parts.append(f"by {call.group_by.replace('_', ' ')}")
    return " · ".join(parts)


def _breakdown(found: list[dict[str, Any]], group_by: Grouping) -> list[tuple[str, str]]:
    if group_by == "none":
        return []
    totals: dict[str, float] = {}
    for row in found:
        key = str(row[group_by])
        totals[key] = totals.get(key, 0.0) + float(row["amount"])
    return [(name, cedis(amount)) for name, amount in sorted(totals.items(), key=lambda kv: -kv[1])]


def figure(call: BudgetFigures, label: str) -> BudgetFigure | None:
    """One budget figure, or None where Nokware holds nothing that answers it: a gap is said, never estimated."""
    document = document_for(call.year)
    found = _matching(call)
    if not document or not found:
        return None
    total = sum(float(row["amount"]) for row in found)
    return BudgetFigure(
        label=label,
        description=describe(call),
        value=cedis(total),
        rows=_breakdown(found, call.group_by),
        document_id=str(document["document_id"]),
        document_title=str(document["title"]),
        year=call.year,
        coverage=f"{float(document['coverage']):.0%}",
        grouped_by=call.group_by,
    )


def context(found: BudgetFigure) -> str:
    """How a budget figure is put to the model: a source in its own right, and plainly a document's figure."""
    lines = [f"[{found.label}] Approved budget figures, read from {found.document_title} ({found.year}).",
             f"{found.description}: {found.value}."]
    if found.rows:
        lines += [f"  {name}: {value}" for name, value in found.rows]
    lines.append(f"These rows are {found.coverage} of what that document states it details. They are approved "
                 f"amounts, not money released or spent. Give each figure exactly as written; never add figures "
                 f"together, work out a share or a difference, or carry a figure from one year to another.")
    return "\n".join(lines)
