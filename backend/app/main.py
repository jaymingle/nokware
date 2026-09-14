import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import (
    ask,
    cases,
    channels,
    contacts,
    dashboard,
    documents,
    issues,
    jobs,
    ledger,
    me,
    options,
    queues,
    reports,
    representatives,
)
from app.services import notifications, scheduler
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.issue_voices import InvalidVoice, IssueNotFound, purge_expired_voice_names
from app.services.ledger_documents import utc_now
from app.services.portal_actions import run_deadline_job
from app.services.portal_queries import DocumentNotFound
from app.services.report_contacts import InvalidNumber
from app.services.report_followups import CaseNotFound, purge_expired_contacts
from app.services.report_photos import PhotoRejected
from app.services.report_rules import InvalidReport
from app.services.workflow import WorkflowError

quiet_sdk_deprecation_warnings()
settings = get_settings()


def show_app_logs() -> None:
    """Send the app's own INFO logs (e.g. what the deadline job published) to the console.

    Uvicorn configures only its own loggers, so without this the app's messages
    below WARNING are dropped.
    """
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)


show_app_logs()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # A messaging provider that is named but missing its settings stops the API here.
    notifications.check_providers()
    # Documents publish when their clock runs out, without cron: the deadline
    # job runs in this process every DEADLINE_JOB_INTERVAL_SECONDS.
    task = scheduler.start(settings.deadline_job_interval_seconds, run_deadline_job, "Deadline job")
    # Citizens' numbers, and names given with voices, are deleted 30 days after their case closes.
    purge = scheduler.start(settings.contact_purge_interval_seconds, run_contact_purge, "Contact purge")
    yield
    await scheduler.stop(task)
    await scheduler.stop(purge)


def run_contact_purge() -> None:
    now = utc_now()
    purge_expired_contacts(now)
    purge_expired_voice_names(now)


app = FastAPI(title="Nokware Backend", version="0.1.0", lifespan=lifespan)

# Auth travels in the Authorization header, never in cookies, so credentials
# stay off and only the headers the frontend sends are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Receipt-Token"],
    expose_headers=["Retry-After"],
)


@app.exception_handler(WorkflowError)
def workflow_error(_: Request, exc: WorkflowError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


@app.exception_handler(InvalidReport)
@app.exception_handler(InvalidNumber)
@app.exception_handler(PhotoRejected)
@app.exception_handler(InvalidVoice)
def invalid_report(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(CaseNotFound)
def case_not_found(_: Request, __: CaseNotFound) -> JSONResponse:
    return JSONResponse({"detail": "No report has that reference. Check it and try again."}, status_code=404)


@app.exception_handler(IssueNotFound)
def issue_not_found(_: Request, __: IssueNotFound) -> JSONResponse:
    return JSONResponse({"detail": "No open issue has that ID."}, status_code=404)


@app.exception_handler(DocumentNotFound)
def document_not_found(_: Request, __: DocumentNotFound) -> JSONResponse:
    return JSONResponse({"detail": "No such document."}, status_code=404)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ask.router)
app.include_router(ledger.router)
app.include_router(me.router)
app.include_router(options.router)
app.include_router(queues.router)  # before documents: /documents/library must not match /documents/{id}
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(cases.router)
app.include_router(dashboard.router)
app.include_router(contacts.router)
app.include_router(representatives.router)
app.include_router(issues.router)
app.include_router(channels.router)
