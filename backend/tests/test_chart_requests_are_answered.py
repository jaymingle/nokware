"""Every request for a chart gets an answer: the chart, or the reason there isn't one.

A request that produced neither — no chart and no word about it — left the reader unable to tell whether Nokware
had failed or had never tried. The matcher was also a list of blessed phrases ("visually" and "show me" missed it
entirely), and a total set aside from its own parts refused with "there's only one count here", which is not what
happened.
"""

from typing import Any

import pytest

from app.services import ask_charts, rag
from app.services.ask_charts import TOTAL_AND_PARTS, asks_for_chart, chart_for
from app.services.ask_figures import FigurePlan
from app.services.phrases import Language, phrase
from app.services.retrieval import Chunk, Retrieval, RetrievedChunk
from tests.test_ask_export import figure

SAFETY = FigurePlan(figures=[], safety_asked=True)
NOTHING = FigurePlan(figures=[], safety_asked=False)


@pytest.mark.parametrize("question", [
    "Generate the answer in a chart", "answer this visually", "give me a visual", "summarise in a graphic",
    "draw it", "show me the reports by topic", "in graphic form", "visualise this", "a diagram please",
    "Plot the budget by department", "I'd like a pie of that", "illustrate the figures",
])
def test_anything_that_plainly_means_i_want_to_see_this_asks_for_a_chart(question: str) -> None:
    assert asks_for_chart(question)


@pytest.mark.parametrize("question", [
    "How many reports were filed?", "What does the 2026 budget say about waste collection?",
    "Which department handles drains?",
])
def test_a_question_that_asks_for_no_picture_is_left_alone(question: str) -> None:
    assert not asks_for_chart(question)


def test_a_total_beside_its_parts_says_what_actually_happened() -> None:
    """The total is set aside so it can't read as a peer of its parts; with one part left there is nothing to draw."""
    figures = [figure("B1", "Approved budget · 2026", "GH¢ 48,289,588"),
               figure("B2", "Approved budget · 2026 · Public Works", "GH¢ 20,232,848")]
    chart, note = chart_for("Chart the 2026 budget", figures)
    assert chart is None and note == TOTAL_AND_PARTS
    assert note != ask_charts.ONE_COUNT and "one count" not in note


def _answered(monkeypatch: pytest.MonkeyPatch, question: str, text: str, plan: FigurePlan = NOTHING,
              cited: bool = True) -> dict[str, Any]:
    class Model:
        def invoke(self, prompt_input: dict[str, str]) -> str:
            return text

    chunk = RetrievedChunk(chunk=Chunk(1, "d1", 0, "Budget text"), score=1.0,
                           document={"title": "2026 Budget", "department": "dept-finance"})
    monkeypatch.setattr(rag, "figures_to_chart", lambda q, a, passages: None)
    monkeypatch.setattr(rag, "retrieve", lambda q: Retrieval(queries=[q], chunks=[chunk] if cited else []))
    monkeypatch.setattr(rag, "plan_figures", lambda q, now: plan)
    monkeypatch.setattr(rag, "_answer_chain", lambda: Model())
    return dict(rag.answer_question(question))


def test_a_chart_asked_of_a_question_the_ledger_cannot_answer_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _answered(monkeypatch, "Show me the ferry timetables for Lake Volta", rag.NO_INFO_ANSWER)
    assert result["status"] == "no_information" and result["chart"] is None
    assert result["chart_note"] == rag.NO_ANSWER_TO_CHART


def test_a_chart_asked_where_the_answer_holds_no_figures_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answered, but citing nothing and counting nothing: there is no figure to draw, and that is worth saying."""
    result = _answered(monkeypatch, "Show me which department handles drains", "Works handles drains.")
    assert result["chart"] is None and result["chart_note"] == rag.NO_FIGURES_TO_CHART


def test_a_chart_asked_alongside_safety_figures_is_accounted_for_too(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _answered(monkeypatch, "Chart the domestic violence reports by area", "Nothing here.", SAFETY)
    assert result["chart"] is None
    assert phrase("ask.safety_figures") in result["answer"] and phrase("ask.no_safety_chart") in result["answer"]


def test_the_same_question_without_a_chart_asked_says_nothing_about_charts(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _answered(monkeypatch, "Which department handles drains?", "Works handles drains.")
    assert result["chart"] is None and result["chart_note"] is None


def test_the_reason_is_given_in_the_language_the_question_was_asked_in() -> None:
    assert rag._note_in(rag.NO_ANSWER_TO_CHART, Language.FRENCH) == phrase("ask.no_answer_to_chart", Language.FRENCH)
    assert rag._note_in(TOTAL_AND_PARTS, Language.FRENCH).startswith("Les seuls chiffres")
    assert rag._note_in("Only the 20 largest of 24 are drawn", Language.FRENCH) == "Only the 20 largest of 24 are drawn"
