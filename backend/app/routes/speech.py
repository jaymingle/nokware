"""Read aloud: an Ask answer, or a report's confirmation and status, spoken as audio. No sign-in.

    POST /api/speech/answer   an Ask answer, sent back as its signed export view
    POST /api/speech/report   a report's status, by its reference (in the body, never the address)

Both answer with one part of the reading (MP3), "part" counting from 0, and say in X-Speech-Parts how many parts
there are: the page plays each while it fetches the next. Only what the server produced is spoken, never anything
about someone's safety (read_aloud.py).
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.dependencies import rate_limited
from app.schemas.ask import SpeechAnswerRequest, SpeechReportRequest
from app.services import ask_export, rate_limit, read_aloud, report_followups, report_store
from app.services.ledger_documents import utc_now

router = APIRouter(prefix="/api/speech", tags=["speech"])
Speech = Depends(rate_limited(rate_limit.SPEECH))


def _audio(script: str, part: int) -> Response:
    pieces = read_aloud.parts(script)
    if part >= len(pieces):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's nothing more to read.")
    spoken = read_aloud.audio(pieces[part], utc_now())
    headers = {"Cache-Control": "no-store", "X-Speech-Parts": str(len(pieces))}
    return Response(spoken.data, media_type=spoken.content_type, headers=headers)


@router.post("/answer", dependencies=[Speech], response_class=Response,
             responses={200: {"content": {"audio/mpeg": {}}, "description": "The answer, spoken"}})
def answer(request: SpeechAnswerRequest) -> Response:
    view = request.view
    if not ask_export.verified(view):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This answer can't be read aloud: ask the question again.")
    return _audio(read_aloud.answer_script(view.question, view.answer, view.status), request.part)


@router.post("/report", dependencies=[Speech], response_class=Response,
             responses={200: {"content": {"audio/mpeg": {}}, "description": "The report's status, spoken"}})
def report(request: SpeechReportRequest) -> Response:
    case = report_followups.find(request.reference)  # CaseNotFound: 404, as the status page says
    public = report_followups.public_status(case, report_store.assignments_for(case["$id"]), utc_now())
    return _audio(read_aloud.status_script(public, receipt=request.kind == "receipt"), request.part)
