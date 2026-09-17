"""Budget rows read from the Assembly's PBB documents: a block proves itself or it is dropped, and a gap is said."""

from typing import Any

import pytest

from app.services import budget_figures
from app.services.budget_extract import MIN_VERIFIED, read_pdf
from app.services.budget_figures import BudgetFigures, context, describe, figure

# One block as the PBB documents print it: the amount repeats at every level, and the rows that matter are the
# sub-programmes. The stated fund-source total is what the block must add up to.
BLOCK = """BUDGET DETAILS BY CHART OF ACCOUNT, 2026
Amount (GH¢)
Institution 01 Government of Ghana Sector
Fund Type/Source 12200 IGF Total By Fund Source 161,050
Function Code 70111 Exec. & leg. Organs (cs)
Organisation 1010101006 Accra Metropolitan Assembly - Accra_Administration_Administration (Assembly
Office)_Metro Planning Unit_Greater Accra
Location Code 0304001 Accra Metropolis - Accra
Compensation of employees [GFS] 8,050
Objective 000000 Compensation of Employees
8,050
Program 93001 Management and Administration
8,050
Sub-Program 93001004 SP1.4: Planning, Coordination and Statistics 8,050
Operation 000000 0.0 0.0 0.0 8,050
Wages and salaries [GFS] 8,050
2111102 Monthly paid and casual labour 8,050
Use of goods and services 153,000
Objective 410501 16.7 Ensure resp. incl. participatory rep. decision making
153,000
Program 93001 Management and Administration
153,000
Sub-Program 93001004 SP1.4: Planning, Coordination and Statistics 153,000
Operation 910101 910101 - INTERNAL MANAGEMENT OF THE ORGANISATION 1.0 1.0 1.0 30,000
Use of goods and services 30,000
2210101 Printed Material and Stationery 5,000
"""
ROWS = [
    {"year": 2026, "fund_source": "IGF", "sector": "Administration", "department": "Public Works",
     "program": "Infrastructure Delivery and Management", "sub_program": "SP2.1: Public Works Service",
     "economic": "Use of goods and services", "amount": 2000000.0, "page": 3},
    {"year": 2026, "fund_source": "GOG", "sector": "Administration", "department": "Metro Finance Department",
     "program": "Management and Administration", "sub_program": "SP1.2: Finance and Audit",
     "economic": "Compensation of employees [GFS]", "amount": 500000.0, "page": 4},
    {"year": 2022, "fund_source": "IGF", "sector": "Administration", "department": "Public Works",
     "program": "Infrastructure Delivery and Management", "sub_program": "SP2.1: Public Works Service",
     "economic": "Use of goods and services", "amount": 250000.0, "page": 9},
]
DOCUMENTS = [
    {"document_id": "ama-2026", "title": "2026 AMA Budget", "year": 2026, "coverage": 0.964},
    {"document_id": "ama-2022", "title": "2022 REVISED PROGRAMME BASED BUDGET", "year": 2022, "coverage": 0.933},
]


@pytest.fixture(autouse=True)
def rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(budget_figures, "_data", lambda: {"documents": DOCUMENTS, "rows": ROWS})


def pdf_of(text: str) -> bytes:
    """A one-page PDF carrying this text, so the reader is exercised as it is in life."""
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen.canvas import Canvas

    out = io.BytesIO()
    canvas = Canvas(out, pagesize=A4)
    y = A4[1] - 40
    for line in text.splitlines():
        canvas.setFont("Helvetica", 8)
        canvas.drawString(30, y, line)
        y -= 11
    canvas.save()
    return out.getvalue()


def test_a_block_that_adds_up_to_its_stated_total_is_kept() -> None:
    found = read_pdf(pdf_of(BLOCK), "ama-2026")
    assert found.blocks == 1 and found.verified_blocks == 1 and found.publishable
    assert [row.amount for row in found.rows] == [8050.0, 153000.0]  # the sub-programmes, not the repeats
    assert sum(row.amount for row in found.rows) == 161050.0  # what the block says its fund source comes to
    row = found.rows[0]
    assert (row.year, row.fund_source, row.department) == (2026, "IGF", "Metro Planning Unit")
    assert row.program == "Management and Administration" and row.economic == "Compensation of employees [GFS]"


def test_a_block_that_does_not_add_up_is_dropped_whole() -> None:
    """Never partly kept and never rounded to fit: a half-read budget is worse than none."""
    broken = BLOCK.replace("Total By Fund Source 161,050", "Total By Fund Source 261,050")
    found = read_pdf(pdf_of(broken), "ama-2026")
    assert found.blocks == 1 and found.verified_blocks == 0 and found.rows == []
    assert not found.publishable and found.share == 0.0


def test_a_document_is_published_only_when_nearly_every_block_reconciles() -> None:
    from app.services.budget_extract import Extracted

    assert Extracted("d", [], 100, 96).publishable and Extracted("d", [], 100, 96).share >= MIN_VERIFIED
    assert not Extracted("d", [], 100, 94).publishable
    assert not Extracted("d", [], 0, 0).publishable  # nothing read is not the same as nothing to read


def test_figures_answer_the_same_shapes_of_question_as_the_live_counts() -> None:
    one = figure(BudgetFigures(year=2026, department="Public Works"), "B1")
    assert one and one.value == "GH¢ 2,000,000" and one.description == "Approved budget · 2026 · Public Works"
    grouped = figure(BudgetFigures(year=2026, group_by="department"), "B1")
    assert grouped and grouped.rows == [("Public Works", "GH¢ 2,000,000"), ("Metro Finance Department", "GH¢ 500,000")]
    earlier = figure(BudgetFigures(year=2022, department="Public Works"), "B2")
    assert earlier and earlier.value == "GH¢ 250,000"  # the same question of another year: a comparison is two calls


@pytest.mark.parametrize("call", [
    BudgetFigures(year=2024),  # the Ledger holds no 2024 budget
    BudgetFigures(year=2026, department="Space Programme"),  # no such department
    BudgetFigures(year=2026, fund_source="DACF"),  # a fund source these rows don't carry
])
def test_what_nokware_does_not_hold_comes_back_as_nothing_never_an_estimate(call: BudgetFigures) -> None:
    assert figure(call, "B1") is None
    assert describe(call)  # and it can still be named, so the answer can say what is missing


def test_a_figure_says_which_document_it_is_read_from_and_what_it_leaves_out() -> None:
    found = figure(BudgetFigures(year=2026, group_by="department"), "B1")
    assert found and found.document_title == "2026 AMA Budget" and found.coverage == "96%"
    written = context(found)
    assert "2026 AMA Budget" in written and "96% of what that document states it details" in written
    assert "approved amounts, not money released or spent" in written
    assert "never add figures together, work out a share or a difference" in written


def test_the_rows_in_the_data_file_are_what_the_service_reads() -> None:
    """The published rows are in the repository: what Nokware says about a budget is reviewable in a diff."""
    import json

    data: dict[str, Any] = json.loads(budget_figures.DATA.read_text())
    assert data["rows"] and data["documents"]
    years = sorted({int(row["year"]) for row in data["rows"]})
    assert years == [document["year"] for document in sorted(data["documents"], key=lambda d: d["year"])]
    assert all(0 < document["coverage"] <= 1 for document in data["documents"])
    assert all(row["amount"] > 0 and row["department"] and row["program"] for row in data["rows"])


def test_a_year_the_resident_names_that_nokware_lacks_is_reported_as_a_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Found in code, not asked of the model: a gap the answer never mentions reads as though figures were withheld."""
    from app.services import ask_figures

    monkeypatch.setattr(budget_figures, "years", lambda: [2022, 2026])
    assert ask_figures._years_not_held("What was approved for waste in 2024?") == ["Approved budget · 2024"]
    assert ask_figures._years_not_held("How much was budgeted in 2022?") == []
    assert ask_figures._years_not_held("What happened in 2024?") == []  # no budget words: not a budget question


def test_the_specific_gap_stands_for_the_general_one() -> None:
    from app.services.ask_figures import _only_the_specific

    assert _only_the_specific(["Approved budget · 2024 · Waste Management", "Approved budget · 2024"]) == [
        "Approved budget · 2024 · Waste Management"]


def test_too_many_bars_are_cut_to_the_largest_and_the_chart_says_so() -> None:
    from app.services.ask_charts import MAX_CATEGORIES, chart_for

    rows = [{"name": f"Department {n}", "value": f"GH¢ {n * 1000:,}"} for n in range(1, 31)]
    figures = [{"label": "B1", "cited": True, "source": "documents", "description": "Approved budget · 2026 · by department",
                "value": "GH¢ 465,000", "rows": rows, "grouped_by": "department", "counted_at": None}]
    chart, _ = chart_for("2026 budget by department as a chart", figures)
    assert chart and len(chart["categories"]) == MAX_CATEGORIES
    assert "20 largest of 30" in chart["note"] and "all in the answer" in chart["note"]
    assert "Department 30" in chart["categories"] and "Department 1" not in chart["categories"]


def budget(label: str, description: str, value: str) -> dict[str, Any]:
    return {"label": label, "cited": True, "source": "documents", "description": description, "value": value,
            "rows": [], "grouped_by": "none", "counted_at": None}


def test_a_total_figure_is_not_charted_beside_the_figures_it_is_the_total_of() -> None:
    """"Approved budget · 2026" is narrowed by "· Public Works": the first is the total, and drawn among its parts
    it would read as the biggest of them."""
    from app.services.ask_charts import chart_for

    figures = [budget("B1", "Approved budget · 2026", "GH¢ 124,760,805"),
               budget("B2", "Approved budget · 2026 · Public Works", "GH¢ 20,232,848"),
               budget("B3", "Approved budget · 2026 · Education", "GH¢ 7,786,630")]
    chart, _ = chart_for("Show the 2026 budget as a chart", figures)
    assert chart and chart["figures"] == ["B2", "B3"]
    assert chart["note"].startswith("Approved budget · 2026 (GH¢ 124,760,805) is left out of the chart")


def test_the_same_thing_in_two_years_is_charted_as_peers() -> None:
    """Neither narrows the other, so neither is a total: a comparison across years is exactly what should chart."""
    from app.services.ask_charts import chart_for

    figures = [budget("B1", "Approved budget · 2022 · Public Works", "GH¢ 2,595,053"),
               budget("B2", "Approved budget · 2026 · Public Works", "GH¢ 20,232,848")]
    chart, _ = chart_for("Compare them as a chart", figures)
    assert chart and chart["figures"] == ["B1", "B2"] and "left out" not in (chart["note"] or "")
