"""POST /api/ask: answer a question from the Ledger with cited sources.

No auth yet: this route exists to prove the retrieval-and-citation premise.
"""

from fastapi import APIRouter

from app.schemas.ask import AskRequest, AskResponse
from app.services.rag import answer_question

router = APIRouter(prefix="/api", tags=["ask"])


# A plain def (not async): answer_question blocks on Postgres and Gemini, so
# FastAPI runs it in its threadpool instead of stalling the event loop.
@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    return AskResponse.model_validate(answer_question(request.question))
