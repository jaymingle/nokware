"""Ask's live figures: counts of citizen reports, through tools the model can call.

When a question looks like it wants figures, a quick planning call offers the
model two tools. CountReports asks for one count (by topic, area, department,
status and period, optionally broken down); PersonalSafetyFigures is what it
calls when a resident asks for figures on reports about someone's safety, which
Nokware does not publish. The counting is stats.py's, so its rules hold here:
personal safety is never counted, and 1 to 4 reads "fewer than 5".

Each count becomes a source under an R label ([R1], [R2], ...) beside the
documents' S labels, so an answer says which figures are live report data and
which come from a document.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, ValidationError

from app.services import budget_figures, stats
from app.services.budget_figures import BudgetFigure, BudgetFigures
from app.services.llm import get_quick_model
from app.services.phrases import phrase
from app.services.report_taxonomy import TOPICS, Category
from app.services.stats import Period, ReportFilter, StatusGroup
from app.teams import RECIPIENT_NAMES
from app.wards import find_ward, sub_metros

logger = logging.getLogger(__name__)

SAFETY_FIGURES_ANSWER = phrase("ask.safety_figures")
# The refusal covers Nokware's own counts, not AMA's published documents: those are public, and anyone can download
# them from the Ledger. Saying so plainly matters either way, so nobody is left thinking figures are being withheld.
SAFETY_IN_DOCUMENTS = phrase("ask.safety_in_documents")
NO_SAFETY_DOCUMENTS = phrase("ask.no_safety_documents")
FIGURE_LABEL_PREFIX = "R"
MAX_FIGURES = 4
# Only a question that might want figures pays for the planning call. A comparison often names no count at all
# ("compare the approved budget for Public Works in 2022 and 2026"), so the budget words stand beside the counting ones.
FIGURE_WORDS = re.compile(
    r"\b(how many|how much|number of|count|figures?|statistics|stats|totals?|most|reports?|reported|cases?|"
    r"complaints?|open|resolved|escalated|filed|pending|outstanding|charts?|graphs?|plot|"
    r"budgets?|budget(ed|ing)?|approv(e|es|ed|al)|allocat(e|es|ed|ion)|spend(ing)?|spent|cedis|GH¢|GHS|"
    r"compare|comparison|against|versus|vs)\b",
    re.IGNORECASE,
)
_PUBLIC_TOPICS = [t for t in TOPICS if t.category != Category.PERSONAL_SAFETY]
TopicId = Literal[tuple(t.id for t in _PUBLIC_TOPICS)]  # type: ignore[valid-type]
SubMetroId = Literal[tuple(sub_metros())]  # type: ignore[valid-type]
RecipientId = Literal[tuple(RECIPIENT_NAMES)]  # type: ignore[valid-type]


class CountReports(BaseModel):
    """Count reports residents have filed with Nokware about problems in Accra. Returns a number only.

    Reports about someone's personal safety are never counted."""

    topic: TopicId | None = Field(None, description="The report topic, one of: " + "; ".join(f"{t.id} ({t.label})" for t in _PUBLIC_TOPICS))
    category: Literal["civic_service", "public_safety"] | None = Field(None, description="Everyday services, or dangers to the public.")
    status: Literal["open", "resolved", "escalated", "any"] = Field("any", description="open: not yet resolved.")
    electoral_area: str | None = Field(None, description="An electoral area (ward) as the resident named it, e.g. Kaneshie.")
    sub_metro: SubMetroId | None = Field(None, description="A sub-metro: " + "; ".join(f"{s.id} ({s.name})" for s in sub_metros().values()))
    department: RecipientId | None = Field(None, description="Who the reports went to: " + "; ".join(f"{k} ({v})" for k, v in RECIPIENT_NAMES.items()))
    period: Literal["today", "this_week", "this_month", "last_30_days", "this_year", "all_time"] = "all_time"
    group_by: Literal["none", "topic", "sub_metro", "month"] = Field(
        "none", description="Also break the count down: by topic, by sub-metro, or by month (for change over time).")


class PersonalSafetyFigures(BaseModel):
    """Call this when the resident asks for figures on reports about someone's safety: abuse or violence against
    a person, a child at risk, sexual violence, or a threat to someone's life. Nokware does not publish these."""

    asked_about: str = Field(description="What the resident asked for figures on, in a few words.")


_PLAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You decide whether a resident's question needs live counts of the reports residents have filed with "
            "Nokware, Accra's civic reporting service. Today is {today} (GMT).\n"
            "- For how many reports, cases or complaints were filed, are open, resolved or escalated (overall, or "
            "for a topic, electoral area, sub-metro, department or period), call CountReports once for each figure "
            "the answer needs (at most four).\n"
            "- If it asks for figures on reports about someone's personal safety (abuse, violence against a person, "
            "a child at risk, sexual violence, a threat to life), call PersonalSafetyFigures instead.\n"
            "- If the resident names a place, pass it as electoral_area exactly as they wrote it, even if you don't "
            "recognise it.\n"
            "- For which topic or sub-metro has the most reports, call CountReports once with group_by.\n"
            "- If the resident asks for a chart or graph of reports, give it something to plot: a group_by (topic or "
            "sub-metro to compare, month for change over time), or one CountReports per status or topic to compare "
            "(with the same group_by, to compare them across topics, sub-metros or months).\n"
            "- For how much the Assembly approved in its budget — overall, or for a department, programme or fund "
            "source, in one year — call BudgetFigures once for each figure the answer needs. Two calls compare two "
            "years, two departments, or a department across years. Nokware holds these budget years: {budget_years}. "
            "Call it with the year the resident asks about even when it isn't one of those, so the answer can say "
            "which years there are instead of leaving the gap unexplained.\n"
            "- Questions about fees, bye-laws, plans or what a document says in words need no tool: call nothing.",
        ),
        ("human", "{question}"),
    ]
)


@dataclass(frozen=True)
class Figure:
    """One count as a citable source: what was counted, the result as it may be shown, and when."""

    label: str
    description: str
    value: str
    rows: list[tuple[str, str]]  # a breakdown: (name, count as shown)
    counted_at: str
    grouped_by: str = "none"  # what the rows break the count down by: topic, sub_metro or month (oldest first)


@dataclass(frozen=True)
class FigurePlan:
    figures: list[Figure]
    safety_asked: bool  # the resident asked for personal-safety figures
    budget: list[BudgetFigure] = field(default_factory=list)  # approved amounts read from the budget documents
    budget_missing: list[str] = field(default_factory=list)  # what was asked for that Nokware doesn't hold

    @property
    def empty(self) -> bool:
        return not self.figures and not self.budget and not self.safety_asked


NO_FIGURES = FigurePlan([], False)


def wants_figures(question: str) -> bool:
    return bool(FIGURE_WORDS.search(question))


_STATUS_WORDS = {"open": "Open reports", "resolved": "Resolved reports", "escalated": "Escalated reports", "any": "Reports"}
_PERIOD_WORDS = {
    "today": "today", "this_week": "this week", "this_month": "this month",
    "last_30_days": "in the last 30 days", "this_year": "this year", "all_time": "since Nokware began",
}


def _describe(call: CountReports, ward_name: str | None) -> str:
    """What was counted, in words: "Open reports · Solid waste and dumping · Ablekuma South sub-metro · this month"."""
    parts = [_STATUS_WORDS[call.status]]
    if call.topic:
        parts.append(stats.topic_label(call.topic))
    elif call.category:
        parts.append("everyday services" if call.category == "civic_service" else "dangers to the public")
    if ward_name:
        parts.append(ward_name)
    if call.sub_metro:
        parts.append(f"{sub_metros()[call.sub_metro].name} sub-metro")
    if call.department:
        parts.append(f"sent to {RECIPIENT_NAMES[call.department]}")
    parts.append(_PERIOD_WORDS[call.period])
    return " · ".join(parts)


def _filter(call: CountReports, ward: str | None) -> ReportFilter:
    return ReportFilter(
        topic=call.topic,
        category=Category(call.category) if call.category else None,
        status=StatusGroup(call.status),
        ward=ward,
        sub_metro=call.sub_metro,
        recipient=call.department,
        period=Period(call.period),
    )


def _rows(cases: list[dict[str, Any]], call: CountReports, wanted: ReportFilter, now: datetime) -> list[tuple[str, str]]:
    """The breakdown, shown counts first and the "fewer than 5" ones after by name, so their order says nothing."""
    if call.group_by == "none":
        return []
    if call.group_by == "month":  # in time order, which says nothing about size
        return [(stats.month_label(key), stats.display(n)) for key, n in stats.by_month(cases, wanted, now)]
    name = stats.topic_label if call.group_by == "topic" else (lambda s: sub_metros()[s].name if s in sub_metros() else s)
    rows = [(name(key), n) for key, n in stats.breakdown(cases, wanted, call.group_by, now)]
    rows.sort(key=lambda r: (stats.shown(r[1]) is None, -r[1] if stats.shown(r[1]) else 0, r[0]))
    return [(label, stats.display(n)) for label, n in rows]


def count_figure(call: CountReports, label: str, cases: list[dict[str, Any]], now: datetime, counted_at: str) -> Figure:
    """Run one CountReports call against the shared case list."""
    ward = find_ward(call.electoral_area) if call.electoral_area else None
    if call.electoral_area and ward is None:
        return Figure(label, f"Reports in \"{call.electoral_area}\"", "no electoral area by that name in Nokware's list", [], counted_at)
    wanted = _filter(call, ward.id if ward else None)
    value = stats.display(stats.count(cases, wanted, now))
    rows = _rows(cases, call, wanted, now)
    return Figure(label, _describe(call, ward.name if ward else None), value, rows, counted_at, call.group_by if rows else "none")


def _tool_calls(question: str, now: datetime) -> list[dict[str, Any]]:
    model = get_quick_model().bind_tools([CountReports, PersonalSafetyFigures, BudgetFigures])
    message = (_PLAN_PROMPT | model).invoke({"question": question, "today": f"{now:%A %d %B %Y}",
                                             "budget_years": ", ".join(str(year) for year in budget_figures.years()) or "none"})
    return list(getattr(message, "tool_calls", []) or [])


def plan(question: str, now: datetime) -> FigurePlan:
    """The live figures a question needs, counted. A planning failure means no figures, never a failed answer."""
    if not wants_figures(question):
        return NO_FIGURES
    try:
        calls = _tool_calls(question, now)
    except Exception:
        logger.exception("Planning Ask's live figures failed; answering from documents only")
        return NO_FIGURES
    safety = any(c["name"] == PersonalSafetyFigures.__name__ for c in calls)
    counts = [CountReports.model_validate(c["args"]) for c in calls if c["name"] == CountReports.__name__][:MAX_FIGURES]
    budget, missing = _budget_figures([c for c in calls if c["name"] == BudgetFigures.__name__][:MAX_FIGURES])
    missing = _only_the_specific(list(dict.fromkeys(missing + _years_not_held(question))))
    if not counts:
        return FigurePlan([], safety, budget, missing)
    cases = stats.public_cases()
    at = datetime.fromtimestamp(stats.counted_at(), tz=UTC).isoformat()
    figures = [count_figure(call, f"{FIGURE_LABEL_PREFIX}{i}", cases, now, at) for i, call in enumerate(counts, 1)]
    return FigurePlan(figures, safety, budget, missing)


BUDGET_WORDS = re.compile(r"\b(budgets?|budget(ed|ing)?|approv(e|es|ed|al)|allocat(e|es|ed|ion)|spend(ing)?|spent|cedis|GH¢|GHS)\b", re.IGNORECASE)
_YEAR_ASKED = re.compile(r"\b(20[0-3]\d)\b")


def _only_the_specific(missing: list[str]) -> list[str]:
    """"Approved budget · 2024" adds nothing beside "Approved budget · 2024 · Waste Management"."""
    return [entry for entry in missing if not any(other != entry and other.startswith(entry) for other in missing)]


def _years_not_held(question: str) -> list[str]:
    """Budget years the resident named that Nokware doesn't hold. Found here rather than asked of the model: a gap
    the answer never mentions reads as though the figures were withheld."""
    if not BUDGET_WORDS.search(question):
        return []
    held = set(budget_figures.years())
    return [f"Approved budget · {year}" for year in sorted({int(y) for y in _YEAR_ASKED.findall(question)} - held)]


def _budget_figures(calls: list[dict[str, Any]]) -> tuple[list[BudgetFigure], list[str]]:
    """The budget figures asked for, and what was asked for that Nokware doesn't hold: a gap is said, not filled."""
    found, missing = [], []
    for index, call in enumerate(calls, 1):
        try:
            wanted = BudgetFigures.model_validate(call["args"])
        except ValidationError:
            continue
        figure = budget_figures.figure(wanted, f"{budget_figures.LABEL_PREFIX}{index}")
        if figure:
            found.append(figure)
        else:
            missing.append(budget_figures.describe(wanted))
    return found, missing


def _when(iso: str) -> str:
    """"14 September 2026, 02:30 GMT" (Accra keeps GMT all year)."""
    moment = datetime.fromisoformat(iso)
    return f"{moment.day} {moment:%B %Y, %H:%M} GMT"


def figure_context(figure: Figure) -> str:
    """One figure as the answering model sees it."""
    breakdown = "; ".join(f"{name}: {value}" for name, value in figure.rows)
    lines = [
        f"[{figure.label}] Live report data (reports residents filed with Nokware, counted {_when(figure.counted_at)}): "
        f"{figure.description}",
        f"Result: {figure.value}",
        *([f"Breakdown: {breakdown}"] if breakdown else []),
        "(Reports about someone's safety are never counted. Counts from 1 to 4 are given as \"fewer than 5\".)",
    ]
    return "\n".join(lines)
