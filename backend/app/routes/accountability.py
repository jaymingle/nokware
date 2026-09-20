"""Accountability: what the Assembly publishes, and how its departments respond. Public, no sign-in."""

from dataclasses import asdict

from fastapi import APIRouter

from app.schemas.accountability import PublishingRecord, Responsiveness
from app.services import department_responsiveness, publishing_record, reporting_gaps, unpublished_data
from app.services.ledger_documents import utc_now

router = APIRouter(prefix="/api", tags=["accountability"])


@router.get("/publishing-record", response_model=PublishingRecord)
def record() -> PublishingRecord:
    now = utc_now()
    found = publishing_record.publishing_record(now)
    gaps = [asdict(gap) for gap in reporting_gaps.gaps(now)]
    return PublishingRecord.model_validate({
        **found,
        "gaps": gaps,
        "gaps_about": reporting_gaps.about(),
        "unpublished": [asdict(finding) for finding in unpublished_data.findings()],
        "unpublished_about": unpublished_data.about(),
    })


@router.get("/responsiveness", response_model=Responsiveness)
def responsiveness() -> Responsiveness:
    return Responsiveness.model_validate(department_responsiveness.responsiveness(utc_now()))
