"""Ask: answer a question from the Ledger with cited sources. Public, no sign-in.

POST /api/ask returns the whole answer at once. POST /api/ask/stream sends the
same answer as newline-delimited JSON events (see AskStreamEvent), so the page
can show progress during the 6-13 seconds an answer takes. Each answer comes with
its export view, signed; POST /api/ask/export takes one back and returns it as a
PDF, a Word document or a CSV (ask_export.py).
"""

import logging
from collections.abc import Iterator

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.dependencies import rate_limited
from app.schemas.ask import AskExportRequest, AskRequest, AskResponse, AskStreamEvent, ExportView
from app.services import ask_export, rate_limit, read_aloud
from app.services.ask_export import Answered, export_view
from app.services.export_csv import csv_bytes
from app.services.export_docx import docx
from app.services.export_pdf import pdf
from app.services.ledger_documents import utc_now
from app.services.rag import answer_question, stream_answer

router = APIRouter(prefix="/api", tags=["ask"])
logger = logging.getLogger(__name__)

BUSY_MESSAGE = "Ask is busy right now. Try again in a minute."
FAILED_MESSAGE = "Something went wrong while answering. Try again."
_BUSY_MARKERS = ("429", "RESOURCE_EXHAUSTED", "ResourceExhausted", "quota")


# Plain defs (not async): the pipeline blocks on Postgres and Gemini, so FastAPI
# runs it in its threadpool instead of stalling the event loop.
FORMATS = {
    "pdf": (pdf, "application/pdf", "pdf"),
    "docx": (docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "csv": (csv_bytes, "text/csv; charset=utf-8", "csv"),
}
Exports = Depends(rate_limited(rate_limit.EXPORTS))


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    result = answer_question(request.question)
    answered = Answered(request.question, result["answer"], result["status"], list(result["sources"]), list(result["figures"]),
                        result["chart"], result["chart_note"])
    speakable = read_aloud.may_speak_answer(request.question, result["answer"])
    return AskResponse.model_validate({**result, "export": export_view(answered, utc_now()), "speakable": speakable})


def error_message(error: Exception) -> str:
    """What to tell the reader: busy (rate limited) or a plain failure; never internals."""
    text = f"{type(error).__name__} {error}"
    return BUSY_MESSAGE if any(marker in text for marker in _BUSY_MARKERS) else FAILED_MESSAGE


def _line(event: dict[str, object]) -> str:
    return AskStreamEvent.model_validate(event).model_dump_json() + "\n"


def _signed(question: str, event: dict[str, Any], seen: dict[str, Any]) -> dict[str, Any]:
    """The final event with the answer's export view: the sources and figures sent earlier, marked as cited."""
    if event["type"] == "sources":
        seen.update(sources=event["sources"], figures=event["figures"])
    if event["type"] != "done":
        return event
    cited = set(event["cited"])
    marked = {name: [{**item, "cited": item["label"] in cited} for item in seen.get(name, [])] for name in ("sources", "figures")}
    answered = Answered(question, event["answer"], event["status"], marked["sources"], marked["figures"], event["chart"], event["chart_note"])
    speakable = read_aloud.may_speak_answer(question, event["answer"])
    return {**event, "export": export_view(answered, utc_now()), "speakable": speakable}


def ndjson_events(question: str) -> Iterator[str]:
    """The stream's lines. A failure mid-answer ends it with an error event, not a broken stream."""
    seen: dict[str, Any] = {}
    try:
        for event in stream_answer(question):
            yield _line(_signed(question, event, seen))
    except Exception as error:
        logger.exception("Ask failed")
        yield _line({"type": "error", "message": error_message(error)})


@router.post(
    "/ask/stream",
    response_class=StreamingResponse,
    responses={200: {"model": AskStreamEvent, "description": "Newline-delimited JSON: one AskStreamEvent per line."}},
)
def ask_stream(request: AskRequest) -> StreamingResponse:
    return StreamingResponse(
        ndjson_events(request.question),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/ask/export", dependencies=[Exports], response_class=Response,
             responses={200: {"content": {m: {} for _, m, _ in FORMATS.values()}, "description": "The file, as an attachment."}})
def export(request: AskExportRequest) -> Response:
    """An answer Ask gave, as a PDF, a Word document or a CSV. Only a view the API signed is rendered."""
    view: ExportView = request.view
    if not ask_export.verified(view):
        raise HTTPException(status_code=403, detail="This answer can't be exported: it doesn't match an answer Ask gave.")
    render, media_type, extension = FORMATS[request.format]
    content = ask_export.content(view, get_settings().public_site_url.rstrip("/"))
    headers = {"Content-Disposition": f'attachment; filename="{ask_export.filename(view, extension)}"', "Cache-Control": "no-store"}
    return Response(render(content), media_type=media_type, headers=headers)
