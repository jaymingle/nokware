"""Ask in French or Twi: read into English, answered and checked there, translated back only if the figures survive."""

from typing import Any

import pytest

from app.services import ask_language, rag
from app.services.ask_figures import FigurePlan, NO_FIGURES
from app.services.ask_language import Asked, figures_and_labels, survives
from app.services.phrases import Language, english, phrase
from app.services.retrieval import Chunk, Retrieval, RetrievedChunk

FRENCH = Asked("Combien coûte une place au marché de Kaneshie ?", "How much does a stall at Kaneshie market cost?",
               Language.FRENCH, "French")
ANSWER = "A stall costs **GH¢ 1,234.56** a year [S1], set in 2026 [S2]."
GOOD = "Une place coûte **GH¢ 1,234.56** par an [S1], fixé en 2026 [S2]."


def chunks() -> list[RetrievedChunk]:
    """Two documents, so an answer citing [S1] and [S2] keeps both through the citation check."""
    return [RetrievedChunk(chunk=Chunk(n, f"d{n}", 0, "Stall fees"), score=1.0, document={"title": f"Document {n}"})
            for n in (1, 2)]


class Translator:
    """Gemini, stubbed at the point the translation is asked for, so the real check still runs over what it says."""

    def __init__(self, says: str | None) -> None:
        self.says = says

    def invoke(self, prompt: str) -> Any:
        if self.says is None:
            raise TimeoutError("the model timed out")
        return type("Reply", (), {"content": self.says})


def answered(monkeypatch: pytest.MonkeyPatch, asked: Asked, body: str, translation: str | None,
             figures: FigurePlan = NO_FIGURES) -> dict[str, Any]:
    monkeypatch.setattr(rag, "read_question", lambda question: asked)
    monkeypatch.setattr(rag, "retrieve", lambda question: Retrieval(queries=[question], chunks=chunks()))
    monkeypatch.setattr(rag, "plan_figures", lambda question, now: figures)
    monkeypatch.setattr(rag, "_answer_chain", lambda: type("Model", (), {"invoke": lambda self, values: body})())
    monkeypatch.setattr(ask_language, "get_quick_model", lambda: Translator(translation))
    return dict(rag.answer_question(asked.question, languages=True))


def test_the_pipeline_runs_on_the_english_so_every_rule_still_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    asked_for: list[str] = []
    monkeypatch.setattr(rag, "read_question", lambda question: FRENCH)
    monkeypatch.setattr(rag, "retrieve", lambda question: asked_for.append(question) or Retrieval(queries=[], chunks=chunks()))
    monkeypatch.setattr(rag, "plan_figures", lambda question, now: asked_for.append(question) or NO_FIGURES)
    monkeypatch.setattr(rag, "_answer_chain", lambda: type("Model", (), {"invoke": lambda self, values: ANSWER})())
    monkeypatch.setattr(ask_language, "get_quick_model", lambda: Translator(GOOD))
    rag.answer_question(FRENCH.question, languages=True)
    assert asked_for == [FRENCH.english, FRENCH.english]  # never the French: the word tests are written in English


def test_an_answer_comes_back_in_the_language_asked_with_the_english_beside_it(monkeypatch: pytest.MonkeyPatch) -> None:
    result = answered(monkeypatch, FRENCH, ANSWER, GOOD)
    assert result["translated"] and result["language"] == "fr"
    assert result["answer"] == GOOD and result["answer_english"] == ANSWER
    # The answer says nothing about being translated: the page says that once, beside the way back to the English.
    assert phrase("ask.machine_translated", Language.FRENCH) not in result["answer"]


@pytest.mark.parametrize("translation", [
    "Une place coûte **GH¢ 1 234,56** par an [S1], fixé en 2026 [S2].",  # the figure rewritten in French style
    "Une place coûte **GH¢ 1,234.56** par an, fixé en 2026 [S2].",  # a citation dropped
    "Une place coûte **GH¢ 1,234.50** par an [S1], fixé en 2026 [S2].",  # a figure changed
    None,  # the model failed
])
def test_a_translation_that_changes_a_figure_or_loses_a_citation_is_not_shown(monkeypatch: pytest.MonkeyPatch,
                                                                             translation: str | None) -> None:
    """A wrong figure is worse than a language the reader has to read twice."""
    if translation is not None:
        assert not survives(ANSWER, translation)
    result = answered(monkeypatch, FRENCH, ANSWER, translation)
    assert not result["translated"] and result["answer"].endswith(ANSWER)
    assert result["answer"].startswith(phrase("ask.translation_failed", Language.FRENCH))


def test_the_fixed_sentences_come_from_the_catalogue_never_from_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nokware's own sentences are written by hand in each language; only the answer itself is translated."""
    result = answered(monkeypatch, FRENCH, rag.NO_INFO_ANSWER, "n'importe quoi")
    assert result["answer"] == phrase("ask.no_information", Language.FRENCH) != english("ask.no_information")
    assert result["status"] == "no_information" and result["translated"]
    safety = answered(monkeypatch, FRENCH, ANSWER, GOOD, FigurePlan([], True))
    assert safety["answer"].startswith(phrase("ask.safety_figures", Language.FRENCH))
    assert phrase("ask.safety_in_documents", Language.FRENCH) in safety["answer"]


def test_twi_falls_back_to_the_english_sentences_it_has_not_written(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twi carries no catalogue text yet, so its fixed sentences read in English until a speaker writes them."""
    twi = Asked("Sɛn na Kaneshie dwam stall bo yɛ?", "How much does a stall at Kaneshie market cost?", Language.TWI, "Twi")
    result = answered(monkeypatch, twi, rag.NO_INFO_ANSWER, "biribiara")
    assert result["language"] == "tw" and result["answer"] == english("ask.no_information")


def test_a_question_already_in_english_costs_no_extra_call() -> None:
    asked = ask_language.read_question("What fees does AMA charge for market stalls?")
    assert asked.language is Language.ENGLISH and asked.english == asked.question and not asked.translated


def test_a_language_nokware_cannot_write_back_is_answered_in_english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ask_language, "get_quick_model", lambda: type("Model", (), {
        "with_structured_output": lambda self, schema: type("Structured", (), {
            "invoke": lambda self, prompt: ask_language._Read(language="Spanish", english="What does a stall cost?")})()})())
    asked = ask_language.read_question("¿Cuánto cuesta un puesto en el mercado?")
    assert asked.language is Language.ENGLISH and asked.named == "Spanish" and asked.english == "What does a stall cost?"


def test_figures_are_compared_as_a_set_not_in_order() -> None:
    assert survives("12 then 30 [S1]", "30 puis 12 [S1]")  # order may change; the figures may not
    assert not survives("12 then 30 [S1]", "12 then 30 [S1][S1]")
    numbers, labels = figures_and_labels("GH¢ 1,234.56 in 2026 [S1][R2]")
    assert numbers["1234.56"] == 1 and numbers["2026"] == 1 and labels == {"S1": 1, "R2": 1}
