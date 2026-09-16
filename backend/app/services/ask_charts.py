"""Charts in Ask: asked for in the question, drawn from the answer's figures, never with a false value.

"Give me a pie chart of reports by topic" or "show this as a graph" asks for one.
Ask's live report figures are exact counts and chart directly. A document's
figures chart only when each one can be tied to its label in a cited passage
(ask_document_charts.py checks that in code): pypdf flattens a table's columns,
so a value can lose its row, and a chart inside a PDF comes through as its axis
ticks. Where that check doesn't pass, the answer gets DOCUMENT_CHART_REFUSAL, a
plain sentence saying why, and the figures stay in the text.

The kind is the one the question names, unless that kind can't show the data
honestly: then the nearest honest kind, with one line saying why. Unnamed, it is
a line for change over time, and bars otherwise (horizontal when labels are
long; several counts side by side). "Fewer than 5" is a range, 1 to 4, never a
value: bars draw it hatched across the range, a line as a dashed span. So a pie
or donut (a slice needs a size) and a stacked bar (an unknown segment moves every
segment above it) are never drawn with one in the set. This module decides; the
web (answer-chart.tsx) and the exports (export_chart.py) only draw.
"""

import math
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from app.services.ask_document_charts import PARTIAL_NOTE, Plotted
from app.services.phrases import phrase
from app.services.stats import FEWER_THAN_SMALL, SMALL

DOCUMENT_CHART_REFUSAL = phrase("ask.document_chart_refusal")
SPREADSHEET_REFUSAL = phrase("ask.spreadsheet_refusal")
ASKS_FOR_SPREADSHEET = re.compile(r"\b(spread ?sheets?|excel|xlsx?|workbook|csv|\.xls)\b", re.IGNORECASE)
ASKS_FOR_CHART = re.compile(
    r"\b(charts?|graphs?|plot(ted)?|visuali[sz](e|ation)|diagram|pie|donut|doughnut|histogram|infographic|stacked|"
    r"(bar|line|column)s? (chart|graph|diagram))\b", re.IGNORECASE)
# The kinds a question can name, most specific first. Anything else charted is drawn as the nearest of these.
NAMED = (
    ("stacked_bar", re.compile(r"\bstack(ed)?\b", re.IGNORECASE)),
    ("donut", re.compile(r"\b(donut|doughnut|ring)\b", re.IGNORECASE)),
    ("pie", re.compile(r"\bpie\b", re.IGNORECASE)),
    ("line", re.compile(r"\bline\b", re.IGNORECASE)),
    ("bar", re.compile(r"\b(bars?|columns?|histogram|horizontal)\b", re.IGNORECASE)),
    ("unsupported", re.compile(r"\b(scatter|area|radar|spider|bubble|tree ?map|funnel|gauge|waterfall|heat ?map)\b", re.IGNORECASE)),
)
HORIZONTAL = re.compile(r"\bhorizontal\b", re.IGNORECASE)
UPRIGHT = re.compile(r"\b(bars?|columns?|vertical)\b", re.IGNORECASE)  # a plain "bar chart" or "column chart" stands up
# A document's labels are names, not places: only an explicit ask stands a long-labelled chart upright.
UPRIGHT_ASKED = re.compile(r"\b(columns?|vertical|upright)\b", re.IGNORECASE)
LONG_LABEL = 16  # characters: longer category names read better on horizontal bars
MAX_CATEGORIES = 20  # more bars than this can't be read; the rest stay in the answer, and the chart says so
MANY_CATEGORIES = "Only the {shown} largest of {total} are drawn; they are all in the answer."
ONE_COUNT = phrase("ask.one_count")
ONE_MONTH = phrase("ask.one_month")
ALL_ZERO = phrase("ask.all_zero")
ChartDict = dict[str, Any]


@dataclass(frozen=True)
class _Data:
    title: str
    categories: list[str]
    series: list[tuple[str, list[tuple[str, float, float]]]]  # (name, [(shown, low, high)]): low == high when exact
    over_time: bool
    parts_of_a_whole: bool  # one breakdown of one count: its rows add up to it
    figures: list[str]
    counted_at: str | None  # when the counts were taken; None for figures read from documents
    source: str = "reports"  # "reports": live counts; "documents": figures proved against cited passages

    @property
    def suppressed(self) -> bool:
        return any(low != high for _, values in self.series for _, low, high in values)


def asks_for_chart(question: str) -> bool:
    return bool(ASKS_FOR_CHART.search(question))


def asks_for_spreadsheet(question: str) -> bool:
    return bool(ASKS_FOR_SPREADSHEET.search(question))


def _named(question: str) -> str | None:
    return next((kind for kind, pattern in NAMED if pattern.search(question)), None)


def _value(shown: str) -> tuple[str, float, float] | None:
    """A figure as shown, with the range it stands for: "fewer than 5" is 1 to 4, "none" is 0, an amount itself."""
    if shown == FEWER_THAN_SMALL:
        return shown, 1, SMALL - 1
    if shown == "none":
        return shown, 0, 0
    digits = shown.replace("GH¢", "").replace("GHS", "").replace(",", "").strip()
    try:
        return shown, float(digits), float(digits)
    except ValueError:
        return None


def _names(descriptions: list[str]) -> tuple[str, list[str]]:
    """What the counts share (the title) and what tells them apart (each one's name)."""
    parts = [description.split(" · ") for description in descriptions]
    common = [part for part in parts[0] if all(part in other for other in parts)]
    names = [" · ".join(p for p in these if p not in common) or "Reports" for these in parts]
    title = " · ".join(common)
    if "reports" in title.lower() or "budget" in title.lower():
        return title, names
    return " · ".join(["Reports", *common]), names


def _months_in_order(categories: list[str]) -> list[str]:
    return sorted(categories, key=lambda name: datetime.strptime(name, "%b %Y"))


def _breakdown(figures: list[dict[str, Any]]) -> _Data | None:
    """Counts broken down the same way (by topic, sub-metro or month): categories, one series per count."""
    grouped = [f for f in figures if f["rows"]]
    if not grouped:
        return None
    same = [f for f in grouped if f["grouped_by"] == grouped[0]["grouped_by"]]
    over_time = same[0]["grouped_by"] == "month"
    categories = list(dict.fromkeys(row["name"] for f in same for row in f["rows"]))
    categories = _months_in_order(categories) if over_time else categories
    title, names = _names([f["description"] for f in same])
    series = []
    for name, figure in zip(names, same):
        rows = {row["name"]: row["value"] for row in figure["rows"]}
        series.append((name, [_value(rows.get(c, "none")) or ("none", 0, 0) for c in categories]))
    return _Data(title, categories, series, over_time, len(same) == 1, [f["label"] for f in same], same[0].get("counted_at"))


def _separate(figures: list[dict[str, Any]]) -> _Data | None:
    """Two or more single counts, compared: each is a category of one series."""
    counted = [(f, _value(f["value"])) for f in figures]
    usable = [(f, v) for f, v in counted if v is not None]
    if len(usable) < 2:
        return None
    title, names = _names([f["description"] for f, _ in usable])
    values = [v for _, v in usable]
    return _Data(title, names, [("Figures", values)], False, False, [f["label"] for f, _ in usable], usable[0][0].get("counted_at"))


def _largest(data: _Data) -> tuple[_Data, str | None]:
    """Too many bars can't be read: keep the largest, and say so rather than quietly dropping the rest. A series
    over time is never cut — a line with months missing from the middle would be a different claim."""
    if data.over_time or len(data.categories) <= MAX_CATEGORIES:
        return data, None
    order = sorted(range(len(data.categories)), key=lambda i: -max(values[i][2] for _, values in data.series))
    keep = sorted(order[:MAX_CATEGORIES])
    kept = replace(data, categories=[data.categories[i] for i in keep],
                   series=[(name, [values[i] for i in keep]) for name, values in data.series])
    return kept, MANY_CATEGORIES.format(shown=MAX_CATEGORIES, total=len(data.categories))


def _default(data: _Data) -> str:
    return "line" if data.over_time else "bar"


def _honest(kind: str, data: _Data) -> tuple[str, str | None]:
    """The kind to draw and, when it isn't the one asked for, why, in one line."""
    fallback = _default(data)
    if kind in ("pie", "donut"):
        if len(data.series) > 1:
            return fallback, "A pie holds one set of numbers and this compares several, so here they are side by side."
        if not data.parts_of_a_whole:
            return fallback, "A pie needs parts of one whole, and these are separate counts that can overlap, so here's a bar chart."
        if data.suppressed:
            return fallback, ('A pie can\'t show "fewer than 5" without inventing a slice size, so here\'s a bar chart '
                              "with that range drawn hatched.")
    if kind == "stacked_bar":
        if len(data.series) == 1:
            return fallback, "There's one set of numbers here, so there's nothing to stack."
        if data.suppressed:
            return "bar", ('A "fewer than 5" segment would shift every segment above it, so the counts are side by '
                           "side instead.")
    if kind == "line" and not data.over_time:
        return "bar", "A line would suggest a trend between categories that aren't in any order, so here's a bar chart."
    if kind == "unsupported":
        shape = "a line chart" if data.over_time else "a bar chart"
        return fallback, f"I can draw bar, line, stacked bar, pie and donut charts; the type you asked for doesn't fit counts like these, so here's {shape}."
    return kind, None


def _scale(kind: str, data: _Data) -> tuple[float, list[float]]:
    """A round top for the value axis (above the tallest stack, for a stacked bar), and its ticks."""
    columns = [[values[i][2] for _, values in data.series] for i in range(len(data.categories))]
    top = max((sum(c) if kind == "stacked_bar" else max(c) for c in columns), default=0)
    step = 1
    while math.ceil(top / step) > 5:
        step = _next_step(step)
    axis_max = max(step, math.ceil(top / step) * step)
    return axis_max, [step * n for n in range(int(axis_max / step) + 1)]


def _next_step(step: int) -> int:
    """1, 2, 5, 10, 20, 50, ..."""
    magnitude = 10 ** (len(str(step)) - 1)
    lead = step // magnitude
    return {1: 2, 2: 5, 5: 10}[lead] * magnitude


def _as_dict(kind: str, horizontal: bool, data: _Data, note: str | None) -> ChartDict:
    axis_max, ticks = _scale(kind, data) if kind not in ("pie", "donut") else (0, [])
    return {
        "kind": kind, "horizontal": horizontal, "title": data.title, "categories": data.categories,
        "series": [{"name": name, "values": [{"shown": s, "low": lo, "high": hi} for s, lo, hi in values]}
                   for name, values in data.series],
        "over_time": data.over_time, "figures": data.figures, "counted_at": data.counted_at, "source": data.source,
        "axis_max": axis_max, "ticks": ticks, "note": note,
    }


def chart_for(question: str, figures: list[dict[str, Any]]) -> tuple[ChartDict | None, str | None]:
    """The chart a question asks for, from the answer's cited figures — live counts or budget amounts read from a
    document — and any note about it. (None, None) when no chart was asked for; (None, note) when one was but
    can't be drawn from these figures."""
    if not asks_for_chart(question) or not figures:
        return None, None
    data = _breakdown(figures) or _separate(figures)
    if data is None or sum(len(values) for _, values in data.series) < 2:  # one count, or one month so far
        return None, ONE_MONTH if data is not None and data.over_time else ONE_COUNT
    if all(high == 0 for _, values in data.series for _, _, high in values):
        return None, ALL_ZERO
    data, cap = _largest(data)
    named = _named(question)
    kind, note = _honest(named, data) if named else (_default(data), None)
    note = " ".join(part for part in (note, cap) if part) or None
    long_labels = max(len(c) for c in data.categories) > LONG_LABEL
    lying = bool(HORIZONTAL.search(question)) or (long_labels and not UPRIGHT.search(question))
    horizontal = kind in ("bar", "stacked_bar") and lying
    if all(figure.get("source") == "documents" for figure in figures):
        data = replace(data, source="documents", counted_at=None)
    return _as_dict(kind, horizontal, data, note), None


# A document's figures are separate amounts, one per label: a bar chart, however the question asked for them.
_DOCUMENT_NOTES = {
    "pie": "A pie needs parts of one whole, and these are separate figures from the documents, so here's a bar chart.",
    "donut": "A ring needs parts of one whole, and these are separate figures from the documents, so here's a bar chart.",
    "stacked_bar": "There's one set of figures here, so there's nothing to stack.",
    "line": "A line would suggest a trend between things that aren't in any order, so here's a bar chart.",
    "unsupported": "I can draw bar, line, stacked bar, pie and donut charts; the type you asked for doesn't fit "
                   "figures like these, so here's a bar chart.",
}


def document_chart(question: str, plotted: Plotted) -> ChartDict:
    """A bar chart of figures read from the documents. Every pair is already proved against a cited passage."""
    categories = [label for label, _, _ in plotted.pairs]
    values = [(shown, value, value) for _, shown, value in plotted.pairs]
    data = _Data(plotted.title, categories, [("Figures", values)], False, False, [], None, source="documents")
    named = _named(question)
    note = _DOCUMENT_NOTES.get(named or "")
    note = f"{note} {PARTIAL_NOTE}" if note and plotted.partial else (PARTIAL_NOTE if plotted.partial else note)
    horizontal = bool(HORIZONTAL.search(question)) or (max(len(c) for c in categories) > LONG_LABEL and not UPRIGHT_ASKED.search(question))
    return _as_dict("bar", horizontal, data, note)
