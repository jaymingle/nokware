from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import ask, documents, jobs, me, options, queues
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.portal_queries import DocumentNotFound
from app.services.workflow import WorkflowError

quiet_sdk_deprecation_warnings()
settings = get_settings()

app = FastAPI(title="Nokware Backend", version="0.1.0")

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
