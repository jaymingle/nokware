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
| `GET /api/reports/options` (wards by sub-metro, personal-safety types, limits) | public |
| `POST /api/reports` (multipart: `description`, `ward` or `sub_metro`, `safety_topic`, `phone`, `whatsapp`, `notify`, `callback_consent`, up to 10 `photos`) | public, 5 per 10 minutes per client |
| `GET /api/reports/{reference}` (by reference or case ID; personal safety shows only its stage) | public, 30 a minute |
| `POST /api/reports/{reference}/escalate` (`note`; once, within 14 days of resolution) | public |
| `POST /api/reports/{reference}/preferences` (`X-Receipt-Token`; after a safety reclassification, once, within the hour) | public |
| `GET /api/representatives` (each sub-metro's chairperson, office and electoral areas; `?area=` finds one area by any spelling) | public |
| `GET /api/contacts` (who to call, grouped by service; each number with its tier and source) | public |
| `GET /api/issues` (open civic issues: topic, area, department, status and voice count; `?sub_metro`, `?topic`) | public |
| `POST /api/issues/{public_id}/voices` (`device_token`, optional `name`; one voice per browser per issue) | public, 20 an hour per client |
| `GET /api/dashboard` (twelve months of report figures, no personal safety; Ledger counts and latest documents; cached a minute) | public |
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
| `GET /api/cases/queue` (citizen reports routed to the caller, most severe and oldest first) | department, agency |
| `GET /api/cases/oversight` (every case and headline counts; personal safety in outline) | MCE |
| `GET /api/cases/{id}` (as the caller may see it; 404 for anyone with no part in it) | department, agency, MCE |
| `POST /api/cases/{id}/acknowledge`, `/resolve` (`note`) | the case's recipients |
| `POST /api/cases/{id}/reassign` (`from_recipient`, `to_recipient`, `reason`), `/reopen`, `/confirm-resolution` (`note`) | MCE |

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
- `app/wards.py`: AMA's electoral areas in 3 sub-metros, with each
  sub-metro's chairperson and office, as given from ama.gov.gh. The 2023
  Monitoring and Evaluation Report's spellings are kept as alternates, and
  `find_ward` matches any of them; Mukose comes from that report alone.

Filing (`app/services/report_intake.py`) checks everything before writing:
photos are re-encoded from their pixels alone (`report_photos.py`: no EXIF,
so no GPS), numbers are validated and stored apart (`report_contacts.py`),
and the model's verdict (`report_classifier.py`, 15-second limit) goes through
the filing rules. Messages (`notifications.py`) go only on submission,
resolution and escalation, content-neutral for personal safety; each is
written to the outbox, then sent. Numbers are deleted by an hourly job 30 days
after their case closes.

SMS goes through Arkesel (`sms.py`) when `SMS_PROVIDER=arkesel`; `log`, the
default, records each message as not sent. Every message fits one SMS page
(one credit): text is made plain GSM-7 (`sms_text.py`), since one curly
apostrophe would send it as Unicode at 70 characters a page, and office names
give way to "2 offices" when they would not fit. `ARKESEL_SANDBOX=true` (the
default) goes through Arkesel without delivering or spending credits, and the
case history says so; outside it, `SMS_DAILY_LIMIT` caps the pages sent in a
day (counted in the API process, so a restart resets it). A provider named but
missing its settings stops the API at startup. `scripts/sms_balance.py` shows
the credits left without spending any. WhatsApp (Twilio) is still `log`.

Callbacks from the providers (`app/routes/channels.py`) are verified before
they are trusted. Arkesel signs SMS and Voice callbacks, and
`arkesel_signatures.py` follows its signing guide exactly (the guide is
Arkesel's and comes from [Arkesel support](https://arkesel.com/contact/); it is
not in this repository). In short: the `X-Arkesel-Webhook-Signature` header
carries `v1=` and an HMAC-SHA256 hex digest, made with `ARKESEL_WEBHOOK_SECRET`,
of `{timestamp}.{canonical JSON}`: the `X-Arkesel-Webhook-Timestamp` header, a
period, then the callback's query parameters as JSON with keys sorted at every
level, list order kept, slashes unescaped and non-ASCII escaped as PHP's
`json_encode` does. During a secret rotation the header holds two
comma-separated `v1=` values, and either may match. The comparison is
constant-time, and a timestamp more than 5 minutes off is refused. Each SMS asks for a delivery report only when `PUBLIC_API_URL` and
the secret are both set; the report sets the outbox row's `deliveryStatus`
(`scripts/add_delivery_reports.py` adds the fields and the index it needs).
Arkesel's sandbox records a message as `SANDBOXED` and sends no report.

Known limitation: Arkesel does not sign USSD callbacks yet (its guide says
USSD signing waits on gateway work). Until it does, the USSD callback is
protected only by a secret token in its URL, which anyone who learns the URL
(from a log or a proxy, say) could use to post fake sessions. When Arkesel
signs USSD, it moves to the same verification.

Staff work cases through `app/services/case_actions.py` (under a per-case
lock, like Ledger documents). What each caller sees is decided in one place
(`case_workflow.case_view`): recipients see everything; the MCE sees a
personal-safety case only in outline (status, recipients, age, audit trail),
and its audit trail never carries what anyone wrote about the case.

The public dashboard (`app/services/report_dashboard.py`) counts only civic
and public-safety reports. Personal safety is left out of every figure,
totals included, so no total less the visible topics can give its number
away; nothing is broken down finer than a sub-metro, and a median needs five
resolved reports.

`scripts/report_lifecycle.py` files `[TEST]` reports against the live services
and checks what was stored; `scripts/case_lifecycle.py` works them through the
staff routes as seeded accounts; `scripts/delete_test_reports.py` lists them
(and removes them with `--yes`).

Police and GNFS receive safety reports as agency teams (`agency-police`,
`agency-gnfs`); they are not Assembly departments and have no part in the
Ledger. `scripts/create_citizen_reports.py` creates those teams and the report
collections (citizen phone numbers are encrypted at rest); add their liaison
accounts to `scripts/seed_users.toml` and re-run `scripts/seed_users.py`.

## What the public sees, and the privacy model

Three public surfaces read citizen reports: the dashboard, Ask's live figures
and the issue list. They share one set of rules (`app/services/stats.py`):

- **Personal safety is never counted**, not as a filter and not in any total,
  so no total less the visible topics can give its number away. Ask answers a
  request for such figures with "Nokware doesn't publish figures on reports
  about someone's safety."
- **A count from 1 to 4 reads "fewer than 5"**, on the dashboard and in Ask
  alike. Zero is shown.
- **Only aggregates, never content.** Ask's tool returns numbers only; the
  issue list shows a civic issue's topic, electoral area, department, status
  and voice count, never the citizen's words, photos or number, and never its
  reference or case ID (either opens a status page), only a separate public ID.

Ask's figures come from a counting tool (`app/services/ask_figures.py`) that a
quick planning call can invoke; each figure is cited as `[R1]` beside the
documents' `[S1]`, and the answer says it is live report data, not a document.

"Add your voice" (`app/services/issue_voices.py`) takes open civic-service
issues only. A voice is anonymous unless the resident gives a name; names are
encrypted at rest, reach the handling department only (the MCE and the public
see counts), and are deleted 30 days after the case closes. One voice per
browser per issue: only a hash of the browser's random token and the case is
stored. `scripts/create_case_voices.py` creates the structure (a dry run by
default; run it with `--yes` before deploying this code).

**Known limits, stated rather than hidden:**

- **Differencing.** Any system that answers counts allows it: comparing an
  electoral area's count with its sub-metro's, or a total with its parts, can
  narrow a "fewer than 5" cell. Leaving personal safety out entirely is the
  protection that matters; for civic and public-safety counts, this residual
  risk is accepted.
- **Voices are not verified.** Without accounts, one person can add voices from
  several browsers; the count is a signal of how many residents care, not a
  signature list, and the page says so. A per-connection rate limit caps abuse.

**Roadmap:** a department-written, one-line public title for an issue (for
example "Pothole on Kaneshie market road near the footbridge"), added when the
department starts work, so residents can tell similar issues apart without the
citizen's own words ever being published.

## Contact numbers

`app/data/contacts.json` holds the numbers a citizen is shown, by how well each
is sourced: national emergency lines (tier 1), numbers on an official site,
cited and checked against that page on a given date (tier 2), and numbers
reported only on social media or in the press, marked not independently
verified (tier 3). A number whose stated source didn't hold up stays in the
file's `held` list and is never shown. Offices are listed by desk: no civil
servant is named beside a number. `app/contacts.py` picks the numbers for a
report's route; a personal-safety report gets the Social Welfare desk for its
sub-metro, and its public status page shows no numbers at all.

## Departments

The departments are AMA's own list (ama.gov.gh/departments) under AMA's own
names, plus Press for assembly-wide publications: 19 teams, in
`app/teams.py`. Pages that list recipients to someone reporting a danger to a
person use a plainer name where AMA's is long ("Social Welfare", not "Social
Welfare & Community Development"); everywhere else uses the full name.

AMA's site doesn't say which department published each document, so the AMA
import files each by its Documents Centre folder, refined by
`scripts/ama_departments.py` (the budget and fee-fixing documents belong to
Budget & Rating, the road-safety reports to Urban Roads, international reports
to International Relations). `scripts/migrate_departments.py` moved an existing
install from the earlier 12-department list: a dry run by default, `--yes` to
apply, `--delete-old-teams` to remove the three superseded teams once nothing
refers to them. Each document change is logged to `scripts/logs/` so it can be
reversed.

The rules behind the Ledger routes live in `app/services/workflow.py`. Every change
is written to the `document_history` collection
(`scripts/create_document_history.py` creates it).

`scripts/portal_lifecycle.py` runs the whole lifecycle against the live
services as seeded accounts, using server-minted JWTs. It creates `[TEST]`
documents and lists them at the end.
