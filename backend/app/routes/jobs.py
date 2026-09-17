"""The deadline job on demand; the API also runs it itself on an interval. Safe to call at any frequency."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from app.dependencies import authorize_job
from app.schemas.documents import JobResult
from app.services import portal_actions

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/publish-expired", response_model=JobResult)
def publish_expired(_: Annotated[str, Depends(authorize_job)], tasks: BackgroundTasks) -> JobResult:
    published, queued = portal_actions.deadline_job()
    for document_id in queued:
        tasks.add_task(portal_actions.ingest_quietly, document_id)
    return JobResult(published=published, ingestion_queued=queued)
