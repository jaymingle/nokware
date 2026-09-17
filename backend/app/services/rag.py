"""Ask: answer a question from the Ledger with verifiable citations.

Retrieval (hybrid, edition-aware, de-duplicated) supplies up to eight chunks.
Each document is shown to gemini-2.5-flash under a short label ([S1], [S2], ...)
with its title, year, department and source type; raw document ids never appear
in the prompt. The model cites labels, and sanitize_citations() drops any label
that does not map to a retrieved document. The answer and its labelled sources
are returned together, so every citation resolves to a real document.

Years come from ``documentYear`` (the year of the document itself), never
``publishedAt``, which is when the document was added to the Ledger.

A question about reports residents have filed also gets live figures
(ask_figures.py), counted while retrieval runs. Each figure is a source under an
R label ([R1]) beside the documents, and the model is told to say when a figure
is live report data rather than a document. Personal-safety figures are never
given: the answer says so in fixed words.

answer_question() returns the whole answer at once; stream_answer() yields the
same pipeline's progress as events (searching, the sources found, the answer
text as it is written, then the checked answer), so a reader sees it working.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, TypedDict

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from app.services.ask_charts import (
    ChartDict,
    asks_for_chart,
    asks_for_spreadsheet,
    chart_for,
    document_chart,
)
from app.services.ask_document_charts import figures_to_chart
from app.services.ask_figures import (
    NO_FIGURES,
    SAFETY_FIGURES_ANSWER,
    Figure,
    FigurePlan,
    figure_context,
    wants_figures,
)
from app.services.ask_figures import plan as plan_figures
from app.services.ask_language import Asked, failed_note, read_question, translate_answer
from app.services.budget_figures import context as budget_context
from app.services.budget_figures import years as budget_years
from app.services.citations import make_label, sanitize_citations
from app.services.ledger_documents import Provenance, provenance, utc_now
from app.services.llm import get_chat_model
from app.services.phrases import Language, phrase
from app.services.retrieval import RetrievedChunk, retrieve
from app.teams import DEPARTMENT_NAMES

ANSWER_TEMPERATURE = 0.2
# Capped rather than off: halves answer latency versus unlimited thinking with no
# loss in completeness, while thinking=0 started citing other years' editions for
# single-document questions.
ANSWER_THINKING_BUDGET = 1024
NO_INFO_ANSWER = phrase("ask.no_information")
UNKNOWN_YEAR = "unknown"
# Fixed wording so readers, and the UI, can reliably spot conflicting sources.
DISAGREEMENT_LEAD = phrase("ask.disagreement_lead")

_SYSTEM_PROMPT = (
    "You are the Nokware Ledger assistant. Answer the resident's question using ONLY "
    "the sources below: excerpts from official Accra Metropolitan Assembly documents. "
    "Each source starts with a header line: its label in square brackets (e.g. [S1]), "
    "then the document's title, year, department and source type.\n\n"
    "How to answer:\n"
    "- Be complete. Use every relevant detail in the sources (figures, dates, names, "
    "steps, conditions, fees, deadlines), not just the first fact you find. Organise "
    "the answer as short paragraphs or bullet points.\n"
    "- Cite once per point, at the end of the point, with the label(s) it comes from, "
    "e.g. [S2] or [S1][S3]. Do not cite every sentence. Cite only labels listed below.\n"
    "- When a year matters, take it from the source header. If the header year is "
    f"{UNKNOWN_YEAR}, do not state or guess one.\n"
    '- Read "this year", "last month" and the like against today\'s date, given with the question. '
    "Never assume a different current year.\n"
    "- If sources disagree (different figures, dates or facts for the same thing), "
    "never pick one, merge them or average them. Start that point with the exact words "
    f'"{DISAGREEMENT_LEAD}" and give each version with the document it comes from, '
    f'named by title, e.g. "{DISAGREEMENT_LEAD} on 2023 revenue: the 2023 Monitoring and '
    'Evaluation Report gives X [S1]; the AMA Biweekly Newsletter gives Y [S2]."\n'
    f'- If the sources do not contain the answer, reply exactly: "{NO_INFO_ANSWER}"\n\n'
    "Some sources are figures rather than passages. Live report data, labelled [R1], [R2], are counts of the "
    "reports residents filed with Nokware. Budget figures, labelled [B1], [B2], are approved amounts read from a "
    "budget the Assembly published, and each says which document and year it comes from.\n"
    "For a budget figure: give it exactly as written, with its year and document; say it is the approved budget, "
    "not money released or spent; never add figures together, subtract one from another, work out a share or a "
    "percentage, or carry a figure from one year to another. Comparing two figures in words is fine: say what each "
    "one is and cite both.\n"
    "When you use a live report figure:\n"
    "- Say in words that the figure comes from Nokware's live report data as of the time given, not from "
    "a document, and cite its label.\n"
    '- Give each figure exactly as written, including "fewer than 5". A figure of "none" is zero: say it so the '
    'sentence reads naturally ("no reports about solid waste", "none were filed"), never as any other number.\n'
    "- Never work out a new figure from others: no adding, subtracting or comparing counts to get a number.\n"
    "- Keep document figures and live report data apart; one never confirms or corrects the other.\n"
    "- If the live figures can't settle the question (for example every count it needs is \"fewer than 5\"), say "
    "so plainly and cite them. Don't give the no-information reply when live figures were provided.\n\n"
    "If the resident asks for a chart or graph, just answer with the figures, and never mention charts or graphs at "
    "all. Never say you can't draw one, or explain how to draw one: Nokware draws the chart itself, beside your "
    "answer, from the figures you give, and says itself when it can't."
)

_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _SYSTEM_PROMPT), ("human", "Sources:\n\n{context}\n\nToday's date: {today}\n\nQuestion: {question}{length}")]
)


class AnswerLength(StrEnum):
    """How long an answer may be: in full on the web, shorter in a chat, a sentence or two by SMS."""

    WEB = "web"
    CHAT = "chat"
    SMS = "sms"


# Only the length changes between channels: the same sources, figures, citation and safety rules apply.
_LENGTH_RULES = {
    AnswerLength.WEB: "",
    AnswerLength.CHAT: (
        "\n\nThis answer goes to a phone chat: keep it under 1,000 characters. Give the most important points "
        "only, as short paragraphs or a few bullets, and still cite each one."
    ),
    AnswerLength.SMS: (
        "\n\nThis answer goes by SMS: at most 240 characters of plain text, one or two sentences with the single "
        "most important point, cited. No lists and no formatting."
    ),
}


AnswerStatus = Literal["answered", "no_information"]


class Source(TypedDict):
    label: str
    cited: bool
    document_id: str
    title: str | None
    chunk_text: str
    department: str | None
    department_name: str | None
    source_type: str | None
    provenance: Provenance | None
    source_url: str | None
    published_at: str | None
    document_year: int | None


class FigureSource(TypedDict):
    label: str  # "R1" for a live count, "B1" for a budget figure
    cited: bool
    description: str  # what it covers
    value: str  # as it may be shown: "12", "fewer than 5", "none", "GH¢ 124,760,805"
    rows: list[dict[str, str]]  # a breakdown: {"name", "value"}
    counted_at: str | None  # when the reports were counted; None for a figure read from a document
    grouped_by: str  # what the rows break it down by
    source: str  # "reports": counted by Nokware; "documents": read from a budget the Assembly published
    document_id: str | None
    document_title: str | None
    year: int | None
    coverage: str | None  # what the rows read come to as a share of what the document states it details


class RagAnswer(TypedDict):
    answer: str  # what the resident reads: their own language where it could be translated safely
    answer_english: str  # the answer as it was written and checked; the sources are in English
    language: str  # the language the answer is written in: "en", "fr" or "tw"
    translated: bool  # whether a machine translated it from the English
    status: AnswerStatus
    sources: list[Source]
    figures: list[FigureSource]
    search_queries: list[str]
    chart: ChartDict | None  # asked for in the question, drawn from the cited live figures (ask_charts)
    chart_note: str | None  # why the chart isn't the kind asked for, or why there is none


@dataclass(frozen=True)
class Prepared:
    """A question with its retrieved chunks, each document under its citation label."""

    question: str
    chunks: list[RetrievedChunk]
    labels: dict[str, str]  # {document_id: "S1", ...}
    queries: list[str]
    figures: FigurePlan = NO_FIGURES

    @property
    def has_sources(self) -> bool:
        """Whether there is anything to answer from: passages, live counts, budget figures, or a gap to explain."""
        return bool(self.chunks or self.figures.figures or self.figures.budget or self.figures.budget_missing)


def _assign_labels(chunks: list[RetrievedChunk]) -> dict[str, str]:
    """One label per document, numbered in retrieval order: {document_id: "S1", ...}."""
    labels: dict[str, str] = {}
    for retrieved in chunks:
        labels.setdefault(retrieved.chunk.document_id, make_label(len(labels) + 1))
    return labels


def _format_context(chunks: list[RetrievedChunk], labels: dict[str, str]) -> str:
    blocks = []
    for document_id, label in labels.items():
        document_chunks = [c for c in chunks if c.chunk.document_id == document_id]
        document = document_chunks[0].document
        header = (
            f"[{label}] {document.get('title') or 'Untitled'} | "
            f"year: {document.get('documentYear') or UNKNOWN_YEAR} | "
            f"department: {DEPARTMENT_NAMES.get(document.get('department') or '', 'unknown')} | "
            f"source: {document.get('sourceType')}"
        )
        excerpts = "\n[...]\n".join(c.chunk.text for c in document_chunks)
        blocks.append(f"{header}\n{excerpts}")
    return "\n\n".join(blocks)


def _source(retrieved: RetrievedChunk, label: str, cited: bool) -> Source:
    document: dict[str, Any] = retrieved.document
    department = document.get("department")
    return Source(
        label=label,
        cited=cited,
        document_id=retrieved.chunk.document_id,
        title=document.get("title"),
        chunk_text=retrieved.chunk.text,
        department=department,
        department_name=DEPARTMENT_NAMES.get(department) if department else None,
        source_type=document.get("sourceType"),
        provenance=provenance(document),
        source_url=document.get("sourceUrl"),
        published_at=document.get("publishedAt"),
        document_year=document.get("documentYear"),
    )


def _figure_source(figure: Figure, cited: set[str]) -> FigureSource:
    return FigureSource(
        label=figure.label,
        cited=figure.label in cited,
        description=figure.description,
        value=figure.value,
        rows=[{"name": name, "value": value} for name, value in figure.rows],
        counted_at=figure.counted_at,
        grouped_by=figure.grouped_by,
        source="reports",
        document_id=None,
        document_title=None,
        year=None,
        coverage=None,
    )


def _budget_source(figure: Any, cited: set[str]) -> FigureSource:
    return FigureSource(
        label=figure.label,
        cited=figure.label in cited,
        description=figure.description,
        value=figure.value,
        rows=[{"name": name, "value": value} for name, value in figure.rows],
        counted_at=None,
        grouped_by=figure.grouped_by,
        source="documents",
        document_id=figure.document_id,
        document_title=figure.document_title,
        year=figure.year,
        coverage=figure.coverage,
    )


def _to_figures(prepared: Prepared, cited: set[str]) -> list[FigureSource]:
    live = [_figure_source(f, cited) for f in prepared.figures.figures]
    return live + [_budget_source(f, cited) for f in prepared.figures.budget]


def _to_sources(chunks: list[RetrievedChunk], labels: dict[str, str], cited: set[str]) -> list[Source]:
    order = {document_id: position for position, document_id in enumerate(labels)}
    ordered = sorted(chunks, key=lambda c: order[c.chunk.document_id])  # stable: rank order within a document
    return [_source(c, labels[c.chunk.document_id], labels[c.chunk.document_id] in cited) for c in ordered]


def answer_status(answer: str) -> AnswerStatus:
    """Whether the Ledger answered, from the fixed no-information reply the model is told to give."""
    return "no_information" if answer.strip().startswith(NO_INFO_ANSWER) else "answered"


def prepare(question: str) -> Prepared:
    """Retrieve documents and, while that runs, count any live figures the question needs."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        planned = pool.submit(plan_figures, question, utc_now())
        retrieval = retrieve(question)
        figures = planned.result()
    return Prepared(question, retrieval.chunks, _assign_labels(retrieval.chunks), retrieval.queries, figures)


def _answer_chain() -> Runnable[dict[str, str], str]:
    return _PROMPT | get_chat_model(ANSWER_TEMPERATURE, thinking_budget=ANSWER_THINKING_BUDGET) | StrOutputParser()


def _prompt_input(prepared: Prepared, length: AnswerLength = AnswerLength.WEB) -> dict[str, str]:
    blocks = [_format_context(prepared.chunks, prepared.labels), *map(figure_context, prepared.figures.figures),
              *map(budget_context, prepared.figures.budget), _budget_gap(prepared)]
    return {
        "context": "\n\n".join(b for b in blocks if b),
        "today": f"{utc_now():%A %d %B %Y}",
        "question": prepared.question,
        "length": _LENGTH_RULES[length],
    }


def _budget_gap(prepared: Prepared) -> str:
    """What the resident asked for that Nokware holds no budget figures for: said plainly, never filled in."""
    missing = prepared.figures.budget_missing
    if not missing:
        return ""
    held = ", ".join(str(year) for year in budget_years()) or "none"
    return ("Nokware holds no budget figures for: " + "; ".join(missing) + f". The budget years it holds are {held}. "
            "Do not give the no-information reply here. Say plainly that the figures they asked for aren't "
            "available and name the budget years there are, so the gap is explained rather than left looking like "
            "the figures are being withheld. Never estimate them from another year, another department or a "
            "document not listed above.")


BODY = "\x00body"  # where the answer itself goes among the fixed sentences around it


def _notices(body: str, prepared: Prepared, question: str, chart: ChartDict | None, note: str | None,
             figures: list[FigureSource]) -> list[list[str]]:
    """The answer as paragraphs of catalogue keys around BODY, so each language writes its own fixed sentences.

    Nokware's safety figures are refused whatever else is said: the refusal covers its own report counts, which
    could identify a person, never AMA's documents, which are public and downloadable by anyone.
    """
    answered = answer_status(body) == "answered"
    if prepared.figures.safety_asked and SAFETY_FIGURES_ANSWER not in body:
        if not answered:  # no document answers it either, and saying so beats leaving figures looking withheld
            return [["ask.safety_figures", "ask.no_safety_documents"]]
        return [["ask.safety_figures"], ["ask.safety_in_documents"], [BODY]]
    paragraphs = []
    if answered and asks_for_chart(question) and chart is None and note is None:
        paragraphs.append(["ask.document_chart_refusal"])
    if answered and asks_for_spreadsheet(question) and not any(figure["cited"] for figure in figures):
        paragraphs.append(["ask.spreadsheet_refusal"])
    return [*paragraphs, [BODY]]


def _written(paragraphs: list[list[str]], body: str, language: Language) -> str:
    """The answer in one language: the body as written, every fixed sentence from the catalogue."""
    return "\n\n".join(" ".join(body if part == BODY else phrase(part, language) for part in paragraph)
                        for paragraph in paragraphs)


def _from_documents(prepared: Prepared, answer: str, sources: list[Source]) -> ChartDict | None:
    """A chart of the figures in the cited passages, drawn only where each one is proved against them."""
    passages = [source["chunk_text"] for source in sources if source["cited"]]
    plotted = figures_to_chart(prepared.question, answer, passages) if passages else None
    return document_chart(prepared.question, plotted) if plotted else None


def finish(prepared: Prepared, raw_answer: str, asked: Asked | None = None) -> RagAnswer:
    """The checked answer: only real citations kept, sources and figures marked cited or not, any chart, and —
    where the question wasn't in English — the answer in the language it was asked in, if every figure survives."""
    valid = (set(prepared.labels.values()) | {f.label for f in prepared.figures.figures}
             | {f.label for f in prepared.figures.budget})
    body, cited = sanitize_citations(raw_answer if prepared.has_sources else NO_INFO_ANSWER, valid)
    figures = _to_figures(prepared, cited)
    sources = _to_sources(prepared.chunks, prepared.labels, cited)
    chart, chart_note = chart_for(prepared.question, [dict(f) for f in figures if f["cited"]])
    if chart is None and chart_note is None and asks_for_chart(prepared.question):
        chart = _from_documents(prepared, body, sources)
    paragraphs = _notices(body, prepared, prepared.question, chart, chart_note, figures)
    in_english = _written(paragraphs, body, Language.ENGLISH)
    answer, language, translated = _in_the_language_asked(paragraphs, body, in_english, asked)
    return RagAnswer(
        answer=answer,
        answer_english=in_english,
        language=language.value,
        translated=translated,
        status=answer_status(in_english),
        sources=sources,
        figures=figures,
        search_queries=prepared.queries,
        chart=chart,
        chart_note=chart_note,
    )


def _in_the_language_asked(paragraphs: list[list[str]], body: str, in_english: str,
                           asked: Asked | None) -> tuple[str, Language, bool]:
    """The answer to show: the language asked for where every figure and citation survived, the English otherwise."""
    if asked is None or not asked.translated:
        return in_english, Language.ENGLISH, False
    if answer_status(body) == "no_information":  # the body is a fixed sentence: the catalogue has it already
        return _written(paragraphs, phrase("ask.no_information", asked.language), asked.language), asked.language, True
    translated = translate_answer(body, asked)
    if translated is None:
        return f"{failed_note(asked.language)}\n\n{in_english}", asked.language, False
    return _written(paragraphs, translated, asked.language), asked.language, True


def answer_question(question: str, length: AnswerLength = AnswerLength.WEB, languages: bool = False) -> RagAnswer:
    """Answer from the Ledger, at the length the channel allows. Every [S#] left maps to a returned source.

    With languages on (the web), a question in French or Twi is answered in that language: it is read into English
    first, so every rule in the pipeline still applies, and the answer is translated back only if its figures and
    citations survive. The channels answer in English, as they always have.
    """
    asked = read_question(question) if languages else None
    prepared = prepare(asked.english if asked else question)
    if not prepared.has_sources:
        return finish(prepared, NO_INFO_ANSWER, asked)
    return finish(prepared, _answer_chain().invoke(_prompt_input(prepared, length)), asked)


def stream_answer(question: str, languages: bool = False) -> Iterator[dict[str, Any]]:
    """The answer as events: stage, sources, deltas of raw text, then the checked answer.

    Deltas are the model's raw text, shown while it writes; the final "done"
    event carries the sanitized answer that replaces them, so a citation the
    checker removes never survives.
    """
    asked = read_question(question) if languages else None
    english_question = asked.english if asked else question
    yield {"type": "stage", "stage": "counting" if wants_figures(english_question) else "searching"}
    prepared = prepare(english_question)
    sources = _to_sources(prepared.chunks, prepared.labels, set())
    yield {"type": "sources", "sources": sources, "figures": _to_figures(prepared, set())}
    parts: list[str] = []
    if prepared.has_sources:
        yield {"type": "stage", "stage": "writing"}
        for piece in _answer_chain().stream(_prompt_input(prepared)):
            parts.append(piece)
            # An answer to be translated isn't shown as it is written: the reader would watch English appear and
            # then be replaced. They see it being translated instead.
            if not (asked and asked.translated):
                yield {"type": "delta", "text": piece}
    if asked and asked.translated and prepared.has_sources:
        yield {"type": "stage", "stage": "translating"}
    result = finish(prepared, "".join(parts), asked)
    cited = sorted({source["label"] for source in result["sources"] if source["cited"]})
    cited += sorted(figure["label"] for figure in result["figures"] if figure["cited"])
    yield {"type": "done", "answer": result["answer"], "answer_english": result["answer_english"],
           "language": result["language"], "translated": result["translated"], "status": result["status"],
           "cited": cited, "chart": result["chart"], "chart_note": result["chart_note"]}
