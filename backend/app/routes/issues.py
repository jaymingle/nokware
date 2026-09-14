"""Add your voice: open civic issues, and residents saying one affects them too. No sign-in.

    GET  /api/issues                        open civic issues, most supported first (?sub_metro, ?topic)
    POST /api/issues/{public_id}/voices     add a voice, anonymous unless a name is given
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.dependencies import rate_limited
from app.schemas.issues import Issue, IssuePage, VoiceRequest, VoiceResult
from app.services import issue_voices, rate_limit
from app.services.case_workflow import CaseStatus
from app.services.ledger_documents import utc_now
from app.services.report_taxonomy import TOPICS_BY_ID
from app.teams import RECIPIENT_NAMES
from app.wards import sub_metros, wards

router = APIRouter(prefix="/api/issues", tags=["issues"])
Voices = Depends(rate_limited(rate_limit.VOICES))
PAGE_MAX = 50
STAGES = {CaseStatus.SUBMITTED: "received", CaseStatus.ASSIGNED: "received", CaseStatus.IN_PROGRESS: "in_progress",
          CaseStatus.ESCALATED: "escalated"}


def _issue(case: dict[str, Any]) -> Issue:
    ward, sub_metro = wards().get(case.get("wardLocation") or ""), sub_metros().get(case.get("subMetro") or "")
    return Issue(
        public_id=case["publicId"],
        topic=TOPICS_BY_ID[case["topic"]].label,
        ward=ward.name if ward else None,
        sub_metro=sub_metro.name if sub_metro else None,
        departments=[RECIPIENT_NAMES.get(r, r) for r in case.get("recipients") or []],
        stage=STAGES[CaseStatus(case["status"])],
        filed_at=case["createdAt"],
        voices=case.get("voiceCount") or 0,
    )


@router.get("", response_model=IssuePage)
def issues(
    sub_metro: str | None = None,
    topic: str | None = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IssuePage:
    found, total = issue_voices.list_issues(sub_metro, topic, limit, offset)
    return IssuePage(issues=[_issue(case) for case in found if issue_voices.is_public_issue(case)], total=total)


@router.post("/{public_id}/voices", response_model=VoiceResult, dependencies=[Voices])
def add_voice(public_id: str, request: VoiceRequest) -> VoiceResult:
    voices, added = issue_voices.add_voice(public_id, request.device_token, request.name, utc_now())
    return VoiceResult(voices=voices, added=added)
