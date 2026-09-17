import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from sqlalchemy.exc import OperationalError as SearchIndexUnreachable

from app import stats_mcp
from app.config import get_settings
from app.routes import (
    accountability,
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
    phone,
    queues,
    reports,
    representatives,
    speech,
)
from app.routes import (
    petitions as petition_routes,
)
from app.services import bms_deliveries, notifications, petition_clock, petitions, scheduler, search_index, whatsapp_voice
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.issue_voices import InvalidVoice, IssueNotFound, purge_expired_voice_names
from app.services.ledger_documents import utc_now
from app.services.petition_rules import PetitionError
from app.services.phone_proof import ProofError
from app.services.portal_actions import run_deadline_job
from app.services.portal_queries import DocumentNotFound
from app.services.read_aloud import NotReadAloud, ReadAloudUnavailable
from app.services.redis_store import RedisUnavailable
from app.services.report_contacts import InvalidNumber
from app.services.report_followups import CaseNotFound, purge_expired_contacts
from app.services.report_photos import PhotoRejected
from app.services.report_rules import InvalidReport
from app.services.workflow import WorkflowError

quiet_sdk_deprecation_warnings()
settings = get_settings()


def show_app_logs() -> None:
    """Uvicorn configures only its own loggers, so without this the app's messages below WARNING are dropped."""
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)


show_app_logs()


class RedactChannelSecrets(logging.Filter):
    """Keep secrets in channel addresses out of access logs: the USSD callback's (Arkesel doesn't sign USSD yet)
    and a spoken reply's random link."""

    PATH = re.compile(r"(/api/channels/(?:ussd|whatsapp/audio)/)[^/?\s]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self.PATH.sub(r"\1[secret]", a) if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(RedactChannelSecrets())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    notifications.check_providers()
    # Postgres comes through a tunnel on a local port that something else can take: say so now, plainly, rather
    # than 30 seconds into a resident's first question. The API starts either way.
    await asyncio.to_thread(search_index.startup_check)
    # Documents publish when their clock runs out, without cron.
    task = scheduler.start(settings.deadline_job_interval_seconds, run_deadline_job, "Deadline job")
    # Petitions the MCE leaves undecided for 72 hours publish, and open ones close after 90 days, on the same interval.
    clock = scheduler.start(settings.deadline_job_interval_seconds, run_petition_clock, "Petition clock")
    # Citizens' numbers and names given with voices go 30 days after their case or petition closes; spoken replies
    # Twilio never reported on go a day after they were sent.
    purge = scheduler.start(settings.contact_purge_interval_seconds, run_contact_purge, "Contact purge")
    # BMS sends no delivery reports, so they are asked for.
    polling = settings.bms_delivery_poll_seconds if settings.sms_provider == "bms" else 0
    deliveries = scheduler.start(polling, run_bms_delivery_poll, "BMS delivery check")
    # The MCP server at /mcp answers only while its session manager runs, and its own app's lifespan never does here.
    async with stats_mcp.SERVER.session_manager.run():
        yield
    await scheduler.stop(task)
    await scheduler.stop(clock)
    await scheduler.stop(purge)
    await scheduler.stop(deliveries)


def run_petition_clock() -> None:
    petition_clock.run_clock(utc_now())


def run_bms_delivery_poll() -> None:
    bms_deliveries.poll(utc_now())


def run_contact_purge() -> None:
    now = utc_now()
    purge_expired_contacts(now)
    purge_expired_voice_names(now)
    petitions.purge_creator_numbers(now)
    whatsapp_voice.sweep(now)


app = FastAPI(title="Nokware Backend", version="0.1.0", lifespan=lifespan)

# Auth travels in the Authorization header, never in cookies, so credentials
# stay off and only the headers the frontend sends are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Receipt-Token", "X-Phone-Proof"],
    expose_headers=["Retry-After", "Content-Disposition", "X-Speech-Parts"],  # an export's file name; a reading's parts
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


@app.exception_handler(PetitionError)
@app.exception_handler(ProofError)
@app.exception_handler(NotReadAloud)
@app.exception_handler(ReadAloudUnavailable)
def petition_error(_: Request, exc: PetitionError | ProofError | NotReadAloud | ReadAloudUnavailable) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


@app.exception_handler(petitions.PetitionNotFound)
def petition_not_found(_: Request, __: petitions.PetitionNotFound) -> JSONResponse:
    return JSONResponse({"detail": "No petition has that number."}, status_code=404)


@app.exception_handler(RedisUnavailable)
def redis_unavailable(_: Request, __: RedisUnavailable) -> JSONResponse:
    return JSONResponse({"detail": "This isn't available right now. Try again shortly."}, status_code=503)


@app.exception_handler(PoolTimeout)
@app.exception_handler(psycopg.OperationalError)
@app.exception_handler(SearchIndexUnreachable)  # the same failure, through the vector store's SQLAlchemy engine
def ledger_search_unavailable(_: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("app").error("The Ledger's search index can't be reached: %s", type(exc).__name__)
    return JSONResponse({"detail": "The Ledger can't be searched right now. Try again shortly."}, status_code=503)


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
app.include_router(accountability.router)
app.include_router(contacts.router)
app.include_router(representatives.router)
app.include_router(issues.router)
app.include_router(petition_routes.router)
app.include_router(phone.router)
app.include_router(speech.router)
app.include_router(channels.router)
app.add_route(stats_mcp.PATH, stats_mcp.APP)  # live report figures for AI clients: public Ask's tools and rules
