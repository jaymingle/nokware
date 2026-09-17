"""Ask: answer a question from the Ledger with cited sources. Public, no sign-in.

The stream exists so the page can show progress during the 6-13 seconds an answer takes. Exports render only a view
the API signed. A spoken question's recording is held in memory only: never stored, and its words never logged.
"""

import logging
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.dependencies import rate_limited
from app.schemas.ask import MAX_QUESTION_LENGTH, AskExportRequest, AskHeard, AskRequest, AskResponse, AskStreamEvent, ExportView
from app.services import ask_export, rate_limit, read_aloud
from app.services.ask_export import Answered, export_view
from app.services.export_csv import csv_bytes
from app.services.export_docx import docx
from app.services.export_pdf import pdf
from app.services.export_xlsx import xlsx
from app.services.ledger_documents import utc_now
from app.services.rag import answer_question, stream_answer
from app.services.voice_audio import AudioRejected
from app.services.voice_transcribe import TranscriptionFailed, Unusable, listen, understood

router = APIRouter(prefix="/api", tags=["ask"])
logger = logging.getLogger(__name__)

BUSY_MESSAGE = "Ask is busy right now. Try again in a minute."
FAILED_MESSAGE = "Something went wrong while answering. Try again."
_BUSY_MARKERS = ("429", "RESOURCE_EXHAUSTED", "ResourceExhausted", "quota")

FORMATS = {
    "pdf": (pdf, "application/pdf", "pdf"),
    "docx": (docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "csv": (csv_bytes, "text/csv; charset=utf-8", "csv"),
    "xlsx": (xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
}
Exports = Depends(rate_limited(rate_limit.EXPORTS))
SpokenQuestions = Depends(rate_limited(rate_limit.SPOKEN_QUESTIONS))
VOICE_MAX_SECONDS = 60
VOICE_MAX_BYTES = 5 * 1024 * 1024  # a minute of speech is well under 1 MB in any format a browser records
VOICE_TOO_LONG = "Spoken questions can be up to a minute. Try a shorter one, or type your question."
VOICE_NOT_HEARD = "I couldn't make out that recording. Try again somewhere quieter, or type your question."
VOICE_FAILED = "Your recording couldn't be read just now. Try again, or type your question."
VOICE_NOT_AUDIO = "That recording couldn't be played. Try again, or type your question."


# Plain defs (not async): the pipeline blocks on Postgres and Gemini, so FastAPI
# runs it in its threadpool instead of stalling the event loop.
@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    result = answer_question(request.question, languages=True)
    # The export and the reading are of the English: it is the answer that was checked, and the sources are in it.
    answered = Answered(request.question, result["answer_english"], result["status"], list(result["sources"]),
                        list(result["figures"]), result["chart"], result["chart_note"])
    speakable = not result["translated"] and read_aloud.may_speak_answer(request.question, result["answer_english"])
    return AskResponse.model_validate({**result, "export": export_view(answered, utc_now()), "speakable": speakable})


def error_message(error: Exception) -> str:
    """Never internals."""
    text = f"{type(error).__name__} {error}"
    return BUSY_MESSAGE if any(marker in text for marker in _BUSY_MARKERS) else FAILED_MESSAGE


def _line(event: dict[str, object]) -> str:
    return AskStreamEvent.model_validate(event).model_dump_json() + "\n"


def _signed(question: str, event: dict[str, Any], seen: dict[str, Any]) -> dict[str, Any]:
    """The done event carries the export view, built from the sources and figures sent earlier."""
    if event["type"] == "sources":
        seen.update(sources=event["sources"], figures=event["figures"])
    if event["type"] != "done":
        return event
    cited = set(event["cited"])
    marked = {name: [{**item, "cited": item["label"] in cited} for item in seen.get(name, [])] for name in ("sources", "figures")}
    in_english = event.get("answer_english") or event["answer"]
    answered = Answered(question, in_english, event["status"], marked["sources"], marked["figures"], event["chart"], event["chart_note"])
    speakable = not event.get("translated") and read_aloud.may_speak_answer(question, in_english)
    return {**event, "export": export_view(answered, utc_now()), "speakable": speakable}


def ndjson_events(question: str) -> Iterator[str]:
    """A failure mid-answer ends the stream with an error event, not a broken stream."""
    seen: dict[str, Any] = {}
    try:
        for event in stream_answer(question, languages=True):
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


def _recording(upload: UploadFile) -> bytes:
    data = upload.file.read(VOICE_MAX_BYTES + 1)
    if len(data) > VOICE_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, VOICE_TOO_LONG)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, VOICE_NOT_HEARD)
    return data


@router.post("/ask/voice", response_model=AskHeard, dependencies=[SpokenQuestions])
def ask_voice(audio: Annotated[UploadFile, File(description="The spoken question, as the browser recorded it")]) -> AskHeard:
    """A spoken question in words, to be checked before it is asked. Nothing is asked here."""
    try:
        heard = listen(_recording(audio), audio.content_type or "", VOICE_MAX_SECONDS)
    except AudioRejected:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, VOICE_NOT_AUDIO) from None
    except TranscriptionFailed:
        logger.warning("A spoken question couldn't be transcribed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, VOICE_FAILED) from None
    if isinstance(heard, Unusable):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, VOICE_TOO_LONG if heard is Unusable.TOO_LONG else VOICE_NOT_HEARD)
    question = heard.english[:MAX_QUESTION_LENGTH]
    return AskHeard(question=question, language=heard.language, understood=understood(question, heard.language))
