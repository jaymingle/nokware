"""Budget figures for Ask: the same shape of question as the live report counts, over rows read from the documents.

- A year that isn't in app/data/budget_lines.json is said to be missing, never approximated from the years that are.
- Each figure says what share of its document's own stated total the rows cover, so any share is against a stated
  base.
- Totals never cross documents.

These are approved amounts: released and actual spending aren't in the documents.
"""

import json
import re
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


# Words that name no department on their own. The model asks for "the Department of Education" where the budget
# says "Education", and for "Health" where it says "Metro. Health Directorate": a plain substring match found
# neither, and the answer then reported a gap that wasn't there.
_GENERIC = frozenset({"the", "of", "and", "department", "departments", "metro", "unit", "units", "directorate",
                      "office", "ama", "assembly", "accra", "metropolitan", "for"})


def _significant(name: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]+", name.lower()) if word not in _GENERIC}


def _names(wanted: str, held: str) -> bool:
    """Every meaningful word of what was asked for is in the name the budget uses."""
    asked, has = _significant(wanted), _significant(held)
    return bool(asked) and asked <= has


def _matching(call: BudgetFigures) -> list[dict[str, Any]]:
    found = [row for row in rows() if int(row["year"]) == call.year]
    for field, value in (("department", call.department), ("program", call.program)):
        if value:
            found = [row for row in found if _names(value, str(row[field]))]
    if call.fund_source:  # a code or a short tag, matched as written
        wanted = call.fund_source.strip().lower()
        found = [row for row in found if wanted in str(row["fund_source"]).lower()]
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
    """None where Nokware holds nothing that answers it: a gap is said, never estimated."""
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
    lines = [f"[{found.label}] Approved budget figures, read from {found.document_title} ({found.year}).",
             f"{found.description}: {found.value}."]
    if found.rows:
        lines += [f"  {name}: {value}" for name, value in found.rows]
    lines.append(f"These rows are {found.coverage} of what that document states it details. They are approved "
                 f"amounts, not money released or spent. Give each figure exactly as written; never add figures "
                 f"together, work out a share or a difference, or carry a figure from one year to another.")
    return "\n".join(lines)
