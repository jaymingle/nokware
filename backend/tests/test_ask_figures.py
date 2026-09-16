"""Ask's live figures: counted by stats.py's rules, cited as R sources, and never about someone's safety."""

from datetime import datetime, timezone
from typing import Any

import pytest

from app.services import ask_figures, rag, stats
from app.services.ask_figures import CountReports, FigurePlan, count_figure, plan, wants_figures
from app.services.retrieval import Chunk, Retrieval, RetrievedChunk

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
AT = NOW.isoformat()


def case(topic: str = "solid_waste", ward: str = "kinka", sub_metro: str = "ashiedu-keteke", status: str = "assigned",
         **fields: Any) -> dict[str, Any]:
    return {"category": "civic_service", "isSensitive": False, "topic": topic, "wardLocation": ward, "subMetro": sub_metro,
            "recipients": ["dept-waste-management"], "status": status, "createdAt": "2026-09-10T09:00:00+00:00", **fields}


SAFETY = case("abuse", category="personal_safety", isSensitive=True, ward=None, sub_metro="ablekuma-south")


def test_only_a_question_that_might_want_figures_pays_for_planning() -> None:
    assert wants_figures("How many cases are still open?") and wants_figures("waste reports from Ablekuma this month")
    # A budget question wants figures now: the budget rows answer "how much was approved", as the counts answer "how many".
    assert wants_figures("What does the 2026 budget say about Kaneshie market?")
    assert not wants_figures("Who is the mayor of Accra?") and not wants_figures("Where do I pay a permit?")


def test_a_count_follows_the_public_rules() -> None:
    cases = [*[case() for _ in range(6)], case(status="resolved"), SAFETY, SAFETY]
    open_waste = count_figure(CountReports(topic="solid_waste", status="open"), "R1", cases, NOW, AT)
    assert (open_waste.value, open_waste.description) == ("6", "Open reports · Solid waste and dumping · since Nokware began")
    everything = count_figure(CountReports(), "R2", cases, NOW, AT)
    assert everything.value == "7"  # the two safety reports are in no count, not even the total
    resolved = count_figure(CountReports(status="resolved"), "R3", cases, NOW, AT)
    assert resolved.value == "fewer than 5"
    assert count_figure(CountReports(topic="roads"), "R4", cases, NOW, AT).value == "none"


def test_an_area_by_any_spelling_and_a_clear_answer_for_an_unknown_one() -> None:
    cases = [case(topic="roads", ward="bubuashie", sub_metro="okaikoi-south") for _ in range(5)]
    assert count_figure(CountReports(electoral_area="Bubuashie"), "R1", cases, NOW, AT).value == "5"
    assert "Bubiashie" in count_figure(CountReports(electoral_area="bubiashie"), "R1", cases, NOW, AT).description
    assert "no electoral area" in count_figure(CountReports(electoral_area="Madina"), "R1", cases, NOW, AT).value


def test_a_breakdown_lists_small_counts_last_and_by_name() -> None:
    cases = [*[case(topic="drainage") for _ in range(7)], case(topic="roads"), case(topic="agriculture")]
    rows = count_figure(CountReports(group_by="topic"), "R1", cases, NOW, AT).rows
    assert rows == [("Drainage and flooding", "7"), ("Animals and urban farming", "fewer than 5"), ("Roads and potholes", "fewer than 5")]


def test_planning_turns_tool_calls_into_labelled_figures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [{"name": "CountReports", "args": {"status": "open"}}, {"name": "PersonalSafetyFigures", "args": {"asked_about": "abuse"}}]
    monkeypatch.setattr(ask_figures, "_tool_calls", lambda question, now: calls)
    monkeypatch.setattr(stats.CASES, "get", lambda: (NOW.timestamp(), [case() for _ in range(5)]))
    planned = plan("How many open cases, and how many abuse reports?", NOW)
    assert [f.label for f in planned.figures] == ["R1"] and planned.figures[0].value == "5" and planned.safety_asked


def test_a_planning_failure_means_no_figures_not_a_failed_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(question: str, now: datetime) -> list[dict[str, Any]]:
        raise TimeoutError("planner timed out")

    monkeypatch.setattr(ask_figures, "_tool_calls", broken)
    assert plan("How many cases are open?", NOW) == ask_figures.NO_FIGURES


class Recorder:
    def __init__(self, answer: str) -> None:
        self.answer, self.inputs = answer, []

    def invoke(self, values: dict[str, str]) -> str:
        self.inputs.append(values)
        return self.answer


def chunk(text: str, title: str = "Social Welfare Annual Report 2025") -> RetrievedChunk:
    return RetrievedChunk(chunk=Chunk(1, "d1", 0, text), score=1.0, document={"title": title, "department": "dept-social-welfare"})


def answer_with(monkeypatch: pytest.MonkeyPatch, figures: FigurePlan, model_answer: str,
                chunks: list[RetrievedChunk] | None = None) -> tuple[dict[str, Any], Recorder]:
    model = Recorder(model_answer)
    monkeypatch.setattr(rag, "retrieve", lambda question: Retrieval(queries=[question], chunks=chunks or []))
    monkeypatch.setattr(rag, "plan_figures", lambda question, now: figures)
    monkeypatch.setattr(rag, "_answer_chain", lambda: model)
    return dict(rag.answer_question("How many cases are still open?")), model


def test_live_figures_answer_even_when_no_document_does(monkeypatch: pytest.MonkeyPatch) -> None:
    figure = count_figure(CountReports(status="open"), "R1", [case() for _ in range(9)], NOW, AT)
    result, model = answer_with(monkeypatch, FigurePlan([figure], False), "Nokware's live report data shows 9 open [R1][R7].")
    assert result["answer"] == "Nokware's live report data shows 9 open [R1]." and result["status"] == "answered"
    assert result["figures"][0]["cited"] and result["figures"][0]["value"] == "9"
    assert "[R1] Live report data" in model.inputs[0]["context"] and "never counted" in model.inputs[0]["context"]


def test_personal_safety_figures_are_refused_in_fixed_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nokware's own counts are refused; where no document covers it either, the answer says so rather than
    leaving the reader thinking figures are being withheld."""
    result, model = answer_with(monkeypatch, FigurePlan([], True), "unused")
    assert result["answer"] == f"{ask_figures.SAFETY_FIGURES_ANSWER} {ask_figures.NO_SAFETY_DOCUMENTS}" and not model.inputs
    figure = count_figure(CountReports(), "R1", [case() for _ in range(5)], NOW, AT)
    result, _ = answer_with(monkeypatch, FigurePlan([figure], True), "There are 5 reports in all [R1].")
    assert result["answer"].startswith(ask_figures.SAFETY_FIGURES_ANSWER) and result["answer"].endswith("[R1].")


def test_a_safety_question_still_gets_what_the_documents_say(monkeypatch: pytest.MonkeyPatch) -> None:
    """AMA's documents are public and downloadable by anyone: the refusal covers Nokware's counts, not the Ledger."""
    answer = "The Social Welfare Department handled 40 domestic violence cases in 2025 [S1]."
    result, _ = answer_with(monkeypatch, FigurePlan([], True), answer, chunks=[chunk("Domestic violence cases handled: 40.")])
    assert result["answer"].startswith(ask_figures.SAFETY_FIGURES_ANSWER)
    assert ask_figures.SAFETY_IN_DOCUMENTS in result["answer"] and result["answer"].endswith(answer)
    assert result["status"] == "answered" and result["sources"][0]["cited"]
