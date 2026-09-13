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

The Ask routes and the published-file link are public. Every other route needs
an Appwrite JWT (`account.createJWT()` in the browser) as
`Authorization: Bearer <jwt>`; the server resolves the role from the user's team
membership.

| Route | Who |
|---|---|
| `POST /api/ask` (whole answer) | public |
| `POST /api/ask/stream` (newline-delimited JSON events: stage, sources, answer text, done) | public |
| `GET /api/ledger/{id}/file` (redirects to a 10-minute PDF link; published documents only, 404 otherwise) | public |
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

Every Ask source says where its document came from (`provenance`): imported
from ama.gov.gh, submitted by a department through the portal, or from a
verified contributor. It comes from each record's `origin` attribute, which
`scripts/add_document_origin.py` added and backfilled; the AMA import and the
portal set it on every new document.

## Citizen reports

Residents report problems (civic service, public safety) or danger to a person
(personal safety). The rules live in pure, unit-tested modules:

- `app/services/report_taxonomy.py`: the fixed list of topics and who each is
  routed to. The classifier picks a topic, never a recipient. The routing is a
  first draft for the Assembly to review.
- `app/services/report_rules.py`: filing. Every doubt resolves toward
  privacy: a report is personal safety if the citizen says so, the model says
  so, or the model fails and the words suggest danger to a person. Personal
  safety is always severity 5 and keeps no ward, only a sub-metro at most.
- `app/services/case_workflow.py`: the lifecycle (one assignment per
  recipient; one escalation to the MCE within 14 days of resolution), what each
  role may see (the MCE sees personal-safety cases only in outline), and when a
  citizen's numbers are deleted (30 days after the case closes).
- `app/wards.py`: AMA's 20 electoral areas in 3 sub-metros, from its 2023
  Monitoring and Evaluation Report.

Police and GNFS receive safety reports as agency teams (`agency-police`,
`agency-gnfs`); they are not Assembly departments and have no part in the
Ledger. `scripts/create_citizen_reports.py` creates those teams and the report
collections (citizen phone numbers are encrypted at rest); add their liaison
accounts to `scripts/seed_users.toml` and re-run `scripts/seed_users.py`.

The rules behind the Ledger routes live in `app/services/workflow.py`. Every change
is written to the `document_history` collection
(`scripts/create_document_history.py` creates it).

`scripts/portal_lifecycle.py` runs the whole lifecycle against the live
services as seeded accounts, using server-minted JWTs. It creates `[TEST]`
documents and lists them at the end.
