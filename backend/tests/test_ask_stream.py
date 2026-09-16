"""Ask's streamed answer, its sources and no-information status, and the public PDF link."""

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import ask as ask_route
from app.services import portal_queries, rag
from app.services.ledger_documents import Provenance
from app.services.portal_queries import DocumentNotFound
from app.services.retrieval import Chunk, Retrieval, RetrievedChunk

IMPORTED = {"title": "AMA Bye-Laws", "department": "dept-finance", "sourceType": "agency", "origin": "ama_website",
            "sourceUrl": "https://ama.gov.gh/documents/bye-laws.pdf", "documentYear": 2017}
CONTRIBUTED = {"title": "Market tolls", "department": "dept-works", "sourceType": "contributor", "origin": "portal",
               "sourceUrl": "https://example.org/tolls.pdf", "documentYear": None}


def retrieved(document_id: str, document: dict[str, Any], index: int = 0) -> RetrievedChunk:
    chunk = Chunk(chunk_id=index, document_id=document_id, chunk_index=index, text=f"{document['title']} text {index}")
    return RetrievedChunk(chunk=chunk, score=1.0, document=document)


class FakeChain:
    def __init__(self, pieces: list[str]) -> None:
        self.pieces = pieces
        self.calls = 0
        self.inputs: list[dict[str, str]] = []

    def stream(self, prompt_input: dict[str, str]) -> Iterator[str]:
        self.calls += 1
        self.inputs.append(prompt_input)
        yield from self.pieces

    def invoke(self, prompt_input: dict[str, str]) -> str:
        self.calls += 1
        self.inputs.append(prompt_input)
        return "".join(self.pieces)


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch):
    """Stub retrieval and the model; returns a function that sets what they produce."""

    def configure(chunks: list[RetrievedChunk], pieces: list[str]) -> FakeChain:
        chain = FakeChain(pieces)
        monkeypatch.setattr(rag, "retrieve", lambda question: Retrieval(queries=[question], chunks=chunks))
        monkeypatch.setattr(rag, "_answer_chain", lambda: chain)
        monkeypatch.setattr(rag, "plan_figures", lambda question, now: rag.NO_FIGURES)  # never a live model call
        return chain

    return configure


def test_stream_sends_progress_then_the_checked_answer(pipeline) -> None:
    pipeline([retrieved("ama-1", IMPORTED), retrieved("doc-2", CONTRIBUTED, 1)], ["Fees rise [S1]", " and [S9]."])
    events = list(rag.stream_answer("What are the fees?"))

    assert [e["type"] for e in events] == ["stage", "sources", "stage", "delta", "delta", "done"]
    assert [e.get("stage") for e in events if e["type"] == "stage"] == ["searching", "writing"]
    assert not any(source["cited"] for source in events[1]["sources"])  # nothing is cited before it is written
    done = events[-1]
    assert done == {"type": "done", "answer": "Fees rise [S1] and.", "answer_english": "Fees rise [S1] and.",
                    "language": "en", "translated": False, "status": "answered", "cited": ["S1"],
                    "chart": None, "chart_note": None}


def test_the_model_is_told_todays_date_so_this_year_means_this_year(pipeline, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag, "utc_now", lambda: datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc))
    chain = pipeline([retrieved("ama-1", IMPORTED)], ["Fees [S1]."])
    list(rag.stream_answer("How many cases this year?"))
    assert chain.inputs[-1]["today"] == "Monday 14 September 2026"


def test_sources_carry_department_name_provenance_and_url(pipeline) -> None:
    pipeline([retrieved("ama-1", IMPORTED), retrieved("doc-2", CONTRIBUTED, 1)], ["x [S1]"])
    first, second = rag.answer_question("q")["sources"]

    assert (first["label"], first["department_name"], first["provenance"]) == ("S1", "Finance", Provenance.AMA_WEBSITE)
    assert first["source_url"] == "https://ama.gov.gh/documents/bye-laws.pdf"
    assert (second["label"], second["provenance"], second["document_year"]) == ("S2", Provenance.CONTRIBUTOR, None)


def test_no_sources_means_no_information_without_asking_the_model(pipeline) -> None:
    chain = pipeline([], ["should not be used"])
    events = list(rag.stream_answer("Who won the 1966 World Cup?"))

    assert [e["type"] for e in events] == ["stage", "sources", "done"]
    assert events[-1]["status"] == "no_information"
    assert events[-1]["answer"] == rag.NO_INFO_ANSWER
    assert chain.calls == 0


def test_the_model_saying_it_has_nothing_is_no_information(pipeline) -> None:
    pipeline([retrieved("ama-1", IMPORTED)], [rag.NO_INFO_ANSWER])
    result = rag.answer_question("q")
    assert result["status"] == "no_information"
    assert rag.answer_status("The fee is GHS 5 [S1].") == "answered"


def test_a_failure_mid_answer_ends_the_stream_with_a_readable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(_: str, languages: bool = False) -> Iterator[dict[str, Any]]:
        yield {"type": "stage", "stage": "searching"}
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

    monkeypatch.setattr(ask_route, "stream_answer", failing)
    lines = [json.loads(line) for line in ask_route.ndjson_events("q")]

    assert lines == [{"type": "stage", "stage": "searching"}, {"type": "error", "message": ask_route.BUSY_MESSAGE}]
    assert ask_route.error_message(ValueError("boom")) == ask_route.FAILED_MESSAGE


def test_stream_route_sends_one_json_event_per_line(pipeline) -> None:
    pipeline([retrieved("ama-1", IMPORTED)], ["Yes [S1]."])
    response = TestClient(app).post("/api/ask/stream", json={"question": "Is it?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    types = [json.loads(line)["type"] for line in response.text.splitlines()]
    assert types == ["stage", "sources", "stage", "delta", "done"]


def test_public_file_link_serves_published_documents_only(monkeypatch: pytest.MonkeyPatch) -> None:
    records = {"pub": {"status": "published", "fileId": "ama/x.pdf"}, "held": {"status": "held", "fileId": "portal/y.pdf"}}
    monkeypatch.setattr(portal_queries, "load", lambda document_id: records[document_id])
    monkeypatch.setattr(portal_queries, "get_ledger_file_url", lambda file_id, expires: f"https://files.test/{file_id}")

    assert portal_queries.public_file_link("pub") == "https://files.test/ama/x.pdf"
    with pytest.raises(DocumentNotFound):
        portal_queries.public_file_link("held")

    client = TestClient(app)
    redirect = client.get("/api/ledger/pub/file", follow_redirects=False)
    assert (redirect.status_code, redirect.headers["location"]) == (307, "https://files.test/ama/x.pdf")
    assert client.get("/api/ledger/held/file", follow_redirects=False).status_code == 404
