import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import ask, documents, jobs, me, options, queues
from app.services import scheduler
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.portal_actions import run_deadline_job
from app.services.portal_queries import DocumentNotFound
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
    # Documents publish when their clock runs out, without cron: the deadline
    # job runs in this process every DEADLINE_JOB_INTERVAL_SECONDS.
    task = scheduler.start(settings.deadline_job_interval_seconds, run_deadline_job, "Deadline job")
    yield
    await scheduler.stop(task)


app = FastAPI(title="Nokware Backend", version="0.1.0", lifespan=lifespan)

# Auth travels in the Authorization header, never in cookies, so credentials
# stay off and only the headers the frontend sends are allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(WorkflowError)
def workflow_error(_: Request, exc: WorkflowError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)


@app.exception_handler(DocumentNotFound)
def document_not_found(_: Request, __: DocumentNotFound) -> JSONResponse:
    return JSONResponse({"detail": "No such document."}, status_code=404)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(ask.router)
app.include_router(me.router)
app.include_router(options.router)
app.include_router(queues.router)  # before documents: /documents/library must not match /documents/{id}
app.include_router(documents.router)
app.include_router(jobs.router)
