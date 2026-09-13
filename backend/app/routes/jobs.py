"""POST /api/jobs/publish-expired: the deadline job.

Publishes held documents and escalated disputes whose 72-hour clock has run
out, and re-queues ingestion for published documents that failed or stalled.
The API already runs this job itself every DEADLINE_JOB_INTERVAL_SECONDS; the
route runs it on demand. Safe to call at any frequency. Callable by an MCE
session, or by a scheduler sending the X-Job-Token header (when JOB_TOKEN is set).
"""

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
