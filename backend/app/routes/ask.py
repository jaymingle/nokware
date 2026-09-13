"""Ask: answer a question from the Ledger with cited sources. Public, no sign-in.

POST /api/ask returns the whole answer at once. POST /api/ask/stream sends the
same answer as newline-delimited JSON events (see AskStreamEvent), so the page
can show progress during the 6-13 seconds an answer takes.
"""

import logging
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.ask import AskRequest, AskResponse, AskStreamEvent
from app.services.rag import answer_question, stream_answer

router = APIRouter(prefix="/api", tags=["ask"])
logger = logging.getLogger(__name__)

BUSY_MESSAGE = "Ask is busy right now. Try again in a minute."
FAILED_MESSAGE = "Something went wrong while answering. Try again."
_BUSY_MARKERS = ("429", "RESOURCE_EXHAUSTED", "ResourceExhausted", "quota")


# Plain defs (not async): the pipeline blocks on Postgres and Gemini, so FastAPI
# runs it in its threadpool instead of stalling the event loop.
@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    return AskResponse.model_validate(answer_question(request.question))


def error_message(error: Exception) -> str:
    """What to tell the reader: busy (rate limited) or a plain failure; never internals."""
    text = f"{type(error).__name__} {error}"
    return BUSY_MESSAGE if any(marker in text for marker in _BUSY_MARKERS) else FAILED_MESSAGE


def _line(event: dict[str, object]) -> str:
    return AskStreamEvent.model_validate(event).model_dump_json() + "\n"


def ndjson_events(question: str) -> Iterator[str]:
    """The stream's lines. A failure mid-answer ends it with an error event, not a broken stream."""
    try:
        for event in stream_answer(question):
            yield _line(event)
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
