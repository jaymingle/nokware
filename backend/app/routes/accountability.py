"""Accountability: what the Assembly publishes, and how its departments respond. Public, no sign-in.

    GET /api/publishing-record   the documents it is required to publish, against what the Ledger holds, by year,
                                 with the figures its documents once reported and haven't since
    GET /api/responsiveness      each department's handling of reports and contributors' documents, last 12 months
"""

from fastapi import APIRouter

from dataclasses import asdict

from app.schemas.accountability import PublishingRecord, Responsiveness
from app.services import department_responsiveness, publishing_record, reporting_gaps
from app.services.ledger_documents import utc_now

router = APIRouter(prefix="/api", tags=["accountability"])


@router.get("/publishing-record", response_model=PublishingRecord)
def record() -> PublishingRecord:
    now = utc_now()
    found = publishing_record.publishing_record(now)
    gaps = [asdict(gap) for gap in reporting_gaps.gaps(now)]
    return PublishingRecord.model_validate({**found, "gaps": gaps, "gaps_about": reporting_gaps.about()})


@router.get("/responsiveness", response_model=Responsiveness)
def responsiveness() -> Responsiveness:
    return Responsiveness.model_validate(department_responsiveness.responsiveness(utc_now()))
