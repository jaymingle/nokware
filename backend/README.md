# Nokware Backend

Python 3.11 · FastAPI · LangChain · Google Gemini (`gemini-2.5-flash`,
`gemini-embedding-2` at 768 dims) · Appwrite SDK · MinIO · Postgres/pgvector.

## Install

With [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Or with pip in a virtualenv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Environment

Copy the example file and fill in real values (pull secrets from Vaultwarden —
do **not** commit `.env`):

```bash
cp .env.example .env
```

Required vars: `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY`,
`POSTGRES_URL`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`,
`MINIO_LEDGER_BUCKET`, `MINIO_PHOTOS_BUCKET`, `GEMINI_API_KEY`.

Optional: `CORS_ORIGINS` (comma-separated browser origins; localhost on any
port is allowed by default), `DEADLINE_JOB_INTERVAL_SECONDS` (default 120; `0`
turns the built-in deadline job off) and `JOB_TOKEN` (lets an outside scheduler
call the job route; without it only a signed-in MCE can).

## Run

```bash
uvicorn app.main:app --reload
```

Run a single worker: portal changes are serialised per document within one
process (see `app/services/portal_actions.py`), and the deadline job runs inside
it. Every `DEADLINE_JOB_INTERVAL_SECONDS` the API publishes documents whose
72-hour clock has run out and retries stalled ingestion, so no cron is needed.

Health check: `GET http://localhost:8000/health` → `{"status": "ok"}`.

## API

`POST /api/ask` is public. Every other route needs an Appwrite JWT
(`account.createJWT()` in the browser) as `Authorization: Bearer <jwt>`; the
server resolves the role from the user's team membership.

| Route | Who |
|---|---|
| `GET /api/me` | anyone signed in |
| `GET /api/departments`, `GET /api/categories` | anyone signed in |
| `POST /api/documents` (multipart: `file`, `title`, `category`, `document_year`, `department`, `source_url`) | department (published), contributor (held 72h) |
| `GET /api/review-queue`, `GET /api/documents/library` | department |
| `GET /api/documents/mine` | contributor |
| `GET /api/escalations` | MCE |
| `GET /api/documents/{id}`, `GET /api/documents/{id}/file` | anyone who may see it |
| `POST /api/documents/{id}/accept`, `/dispute` | department |
| `POST /api/documents/{id}/accept-dispute`, `/escalate`, `/resubmit` (multipart) | contributor |
| `POST /api/documents/{id}/uphold`, `/overrule` | MCE |
| `POST /api/jobs/publish-expired` | MCE, or `X-Job-Token` |

The rules behind these routes live in `app/services/workflow.py`. Every change
is written to the `document_history` collection
(`scripts/create_document_history.py` creates it).

`scripts/portal_lifecycle.py` runs the whole lifecycle against the live
services as seeded accounts, using server-minted JWTs. It creates `[TEST]`
documents and lists them at the end.
