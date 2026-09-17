"""An Ask answer as CSV: one file, a row per thing, and every live figure as rows a spreadsheet can use.

"Fewer than 5" leaves `value` empty and says so in `shown_as`, so a spreadsheet can't add it up as if it were a
number. Numbers quoted from documents other than budgets stay in the answer's text.

Written with a byte-order mark, so Excel shows GH¢ and ₵. A cell that would start a formula is prefixed with an
apostrophe: the question is the resident's own words.
"""

import csv
import io
import re

from app.schemas.ask import AskFigure
from app.services.ask_export import HEADER_NOTICE, Content, figure_footnote, figures_notes

COLUMNS = ["section", "number", "item", "category", "value", "shown_as", "detail", "department", "year", "source_url",
           "nokware_copy", "counted_at"]
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object) -> object:
    return f"'{value}" if isinstance(value, str) and value.startswith(_FORMULA) else value


_AMOUNT = re.compile(r"^(?:GH¢|GHS|₵)?\s*(\d[\d,]*(?:\.\d+)?)$")


def figure_value(shown: str) -> int | float | str:
    """An amount's currency stays in "shown as". "Fewer than 5" is never a number: the cell stays empty."""
    if shown == "none":
        return 0
    found = _AMOUNT.match(shown.strip())
    if not found:
        return ""
    number = found[1].replace(",", "")
    return float(number) if "." in number else int(number)


def _figure_rows(number: int, figure: AskFigure) -> list[dict[str, object]]:
    base = {"section": "figure", "number": f"F{number}", "item": figure.description,
            "counted_at": figure.counted_at, "detail": figure_footnote(figure)}
    rows = [{**base, "category": "Total", "value": figure_value(figure.value), "shown_as": figure.value}]
    return rows + [{**base, "category": row.name, "value": figure_value(row.value), "shown_as": row.value} for row in figure.rows]


def answer_text(content: Content) -> str:
    marks = {"bullet": "• ", "numbered": "- ", "heading": "", "paragraph": ""}
    return "\n".join(marks[block.kind] + "".join(text for text, _ in block.runs) for block in content.blocks)


def csv_bytes(content: Content) -> bytes:
    rows: list[dict[str, object]] = [
        {"section": "notice", "item": HEADER_NOTICE},
        {"section": "question", "item": content.question, "detail": f"Answered {content.answered}"},
        {"section": "answer", "item": answer_text(content)},
    ]
    rows += [{"section": "note", "item": note} for note in (content.no_information, content.chart_note,
                                                            content.chart.note if content.chart else None) if note]
    rows += [{"section": "source", "number": n, "item": s.title, "detail": provenance, "department": s.department_name,
              "year": s.document_year, "source_url": s.source_url, "nokware_copy": s.ledger_url}
             for n, s, provenance in content.sources]
    for number, figure in content.figures:
        rows += _figure_rows(number, figure)
    rows += [{"section": "note", "item": note} for note in figures_notes(content.figures)]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _safe(value) for key, value in row.items() if value is not None})
    return out.getvalue().encode("utf-8-sig")
