"""An Ask answer as an Excel workbook: the live report figures as a sheet you can work with, and its chart.

Three sheets. **Answer** carries the notice, the question, the answer and the
documents it cites. **Figures** is the working sheet: one block per live figure,
its total and each line of its breakdown, the count in its own column as a
number. **Chart** holds an Excel chart of the same cells — a real chart tied to
the data, not a picture of one, so changing a cell moves the bar.

Two rules keep a spreadsheet from saying more than Nokware knows:

- "Fewer than 5" is never a number. Its count cell stays empty and the text goes
  in "Shown as", so nobody can total a column and reveal a suppressed count. The
  same for a figure that is a range.
- Only live report figures become cells. Numbers quoted from documents stay in
  the answer's text, because what an answer sets out is a few passages, not a
  whole table: a sheet invites sums across rows the Ledger can't yet support.
  That is why the export is offered only for an answer with live figures, and
  why a question asking for budget figures as a spreadsheet is told so plainly
  (ask_charts.SPREADSHEET_REFUSAL). A chart of document figures can be drawn
  where every bar is proved (ask_document_charts.py); a sheet of them waits for
  the table extraction.

A cell that would start a formula (=, +, -, @) is prefixed with an apostrophe:
the question is the resident's own words.
"""

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.schemas.ask import AskChart, AskFigure
from app.services.ask_export import HEADER_NOTICE, LIVE_DATA_NOTE, Content, chart_footnote
from app.services.export_csv import answer_text, count_value

INK = "FF17242B"
TEAL = "FF1F6F5C"
HEADING = Font(bold=True, color=INK)
WHITE_HEADING = Font(bold=True, color="FFFFFFFF")
SMALL = Font(size=9, color="FF4A5A5F")
FILL = PatternFill("solid", fgColor=TEAL)
WRAP = Alignment(wrap_text=True, vertical="top")
_FORMULA = ("=", "+", "-", "@", "\t", "\r")
MAX_ROWS_CHARTED = 24  # a chart of more categories than this is unreadable; the cells still hold every row


def _safe(value: object) -> object:
    return f"'{value}" if isinstance(value, str) and str(value).startswith(_FORMULA) else value


def _write(sheet: Worksheet, row: int, values: list[object], font: Font | None = None) -> int:
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=column, value=_safe(value))
        if font:
            cell.font = font
    return row + 1


def _widths(sheet: Worksheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _answer_sheet(sheet: Worksheet, content: Content) -> None:
    sheet.sheet_properties.tabColor = TEAL
    _widths(sheet, [22, 70, 28, 30])
    row = _write(sheet, 1, [HEADER_NOTICE], SMALL)
    row = _write(sheet, row + 1, ["Question", content.question], HEADING)
    row = _write(sheet, row, ["Answered", content.answered])
    row += 1
    sheet.cell(row=row, column=1, value="Answer").font = HEADING
    answer = sheet.cell(row=row, column=2, value=_safe(answer_text(content)))
    answer.alignment = WRAP
    sheet.row_dimensions[row].height = 220
    row += 2
    for note in (content.no_information, content.chart_note, content.chart.note if content.chart else None):
        if note:
            row = _write(sheet, row, ["Note", note], SMALL)
    if content.sources:
        row = _write(sheet, row + 1, ["Sources"], HEADING)
        row = _write(sheet, row, ["Cited", "Document", "Department", "Year", "Published at", "Nokware's copy"], HEADING)
        for number, source, provenance in content.sources:
            row = _write(sheet, row, [f"[S{number}]", source.title, source.department_name, source.document_year,
                                      source.source_url, source.ledger_url])
            if provenance:
                row = _write(sheet, row, ["", provenance], SMALL)


def _figure_block(sheet: Worksheet, row: int, number: int, figure: AskFigure) -> tuple[int, tuple[int, int] | None]:
    """One figure: its heading, a header row, its total and its breakdown. Returns the next row and the rows charted."""
    row = _write(sheet, row, [f"F{number}", figure.description], HEADING)
    row = _write(sheet, row, ["Counted", figure.counted_at], SMALL)
    header = row
    for column, title in enumerate(["Category", "Count", "Shown as"], start=1):
        cell = sheet.cell(row=header, column=column, value=title)
        cell.font, cell.fill = WHITE_HEADING, FILL
    row = _write(sheet, header + 1, ["Total", count_value(figure.value), figure.value])
    first = row
    for line in figure.rows:
        row = _write(sheet, row, [line.name, count_value(line.value), line.value])
    return row + 1, (first, row - 1) if figure.rows else None


def _figures_sheet(sheet: Worksheet, content: Content) -> dict[str, tuple[int, int]]:
    """The working sheet. Returns each figure's breakdown rows, by label, for the chart to point at."""
    sheet.freeze_panes = "A2"
    _widths(sheet, [44, 12, 18])
    row = _write(sheet, 1, ["Live report figures: counts of the reports residents filed with Nokware"], HEADING)
    row = _write(sheet, row, [LIVE_DATA_NOTE], SMALL)
    row += 1
    ranges: dict[str, tuple[int, int]] = {}
    for number, figure in content.figures:
        row, rows = _figure_block(sheet, row, number, figure)
        if rows:
            ranges[figure.label] = rows
    return ranges


def _chart(chart: AskChart) -> BarChart | LineChart | PieChart:
    """An Excel chart of the kind Nokware drew, so the workbook says what the page said."""
    if chart.kind == "line":
        return LineChart()
    if chart.kind in ("pie", "donut"):
        return PieChart()
    drawn = BarChart()
    drawn.type = "bar" if chart.horizontal else "col"
    if chart.kind == "stacked_bar":
        drawn.grouping, drawn.overlap = "stacked", 100
    return drawn


def _chart_sheet(sheet: Worksheet, figures: Worksheet, chart: AskChart, charted: list[tuple[int, int]]) -> None:
    """The chart Nokware drew, over the cells on the Figures sheet: a real chart, not a picture of one."""
    first, last = charted[0][0], min(charted[0][1], charted[0][0] + MAX_ROWS_CHARTED - 1)
    drawn = _chart(chart)
    drawn.title = chart.title
    drawn.legend = None
    drawn.height, drawn.width = 10, 20
    drawn.add_data(Reference(figures, min_col=2, min_row=first, max_row=last))
    drawn.set_categories(Reference(figures, min_col=1, min_row=first, max_row=last))
    sheet.add_chart(drawn, "A4")
    _widths(sheet, [110])
    row = _write(sheet, 1, [chart.title], HEADING)
    _write(sheet, row, [chart_footnote(chart)], SMALL)


def xlsx(content: Content) -> bytes:
    """The answer as an Excel workbook. Only an answer with live figures is worth one (see the module docstring)."""
    book = Workbook()
    book.properties.creator = "Nokware (not an official AMA document)"
    book.properties.title = content.question[:255]
    answer: Any = book.active
    answer.title = "Answer"
    _answer_sheet(answer, content)
    figures = book.create_sheet("Figures")
    ranges = _figures_sheet(figures, content)
    charted = [ranges[label] for label in content.chart.figures if label in ranges] if content.chart else []
    if content.chart and charted:
        _chart_sheet(book.create_sheet("Chart"), figures, content.chart, charted)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()
