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
the credits left without spending any. WhatsApp goes through Twilio when
`WHATSAPP_PROVIDER=twilio` (below).

Emergency numbers (`app/contacts.py`, `channel_contacts.py`): Ghana's hotlines
often don't connect, so a report where someone may be in danger shows every
number we have for each service involved, in the order to try them: 112, then
the services its topic needs (fire, NADMO, the Police), and the ambulance for
anything where someone could be hurt. Personal safety adds the Police
reporting lines (marked, as everywhere, as reported via X and not
independently verified), the Helpline of Hope and Social Welfare (the
citizen's sub-metro desk, or every desk, and the head office). The web and
WhatsApp show the full list; an SMS or a USSD screen, which can't hold it,
gives two numbers per service and points to `/contacts/emergency`, a page of
emergency numbers only (no "Who represents you": safety reporters are never
pointed to an Assembly Member, an elected politician who in a small area may
know the abuser). A personal-safety SMS never carries numbers: it says only the
reference. A road accident is a public-safety report to the Police with Police
and ambulance numbers. A medical emergency (someone ill or hurt, no one else
involved) isn't the Assembly's to act on: WhatsApp and USSD (menu 4) say so
plainly, file nothing, and give the ambulance numbers.

A precise location (`report_locations.py`) is the one exception to the
coarse-location rule, and only on the citizen's explicit opt-in. After a
personal-safety report is filed on WhatsApp, the receipt names who has it and
offers, for an hour, CALL (the responders may phone; apart from updates),
PLACE (say exactly where they are, so help can come), REMOVE and YES
(updates). A location, a pin or a typed address, goes straight into the
citizen's contact record, encrypted, never through Redis; the message that
carried it is deleted from Twilio's log; and it is deleted with the numbers 30
days after the case closes, or at once on REMOVE, which is confirmed only after
a fresh read shows it gone. Only a Police or Social Welfare account actively on
that case can open it (`GET /api/cases/{id}/location`), never the MCE or another
department, even after a reassignment. The case page says a location exists;
each opening is a deliberate act recorded in the audit trail (the service and
the time, never the place), and the citizen's status page says "Your location
was viewed by Ghana Police Service on ...". USSD offers CALL but not a location:
an address can't practically be typed on a keypad. Run
`scripts/add_exact_location.py --yes` before an API with this code takes one.

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

The messaging channels share one layer, so WhatsApp and USSD file and answer
through the same `report_intake.submit()` and `rag.answer_question()` as the web:

- `channel_intent.py` reads a message: a short one holding a case reference
  asks for its status and a greeting asks for help, with no model call; the
  quick model sorts the rest into question, report, status ("what's happening
  with my report K7QM-4TXP?", answered only when it names a reference) or
  unclear, and a failure means "unclear", so nothing is filed or answered on a
  guess.
- `rag.answer_question(question, length)` answers at the channel's length (the
  web in full, a chat in about 1,000 characters, an SMS in 240); only a length
  line in the prompt changes, so sources, live figures, "fewer than 5" and the
  safety refusal hold everywhere. `channel_answers.py` lays the answer out:
  numbered sources for WhatsApp, and for SMS one plain GSM-7 message of two
  pages at most with its first source.
- `channel_status.py` gives a case's status from the same `public_status()` as
  the web: a personal-safety case says only its stage.
- `redis_store.py`, `channel_sessions.py` and `channel_limits.py` keep
  short-lived state in Redis (`REDIS_URL`): USSD menus and WhatsApp drafts
  that expire when a conversation goes quiet, and per-number limits in fixed
  windows. A phone number never appears in Redis: keys hold a keyed hash of
  it. The day's SMS page count lives there too, so a restart can't reset it,
  and if Redis can't be reached no SMS is sent rather than sent uncounted.

USSD (`ussd.py`, `POST /api/channels/ussd/{token}`) is a keypad menu: 1 Ask
a question, 2 Report an issue, 3 Check a case. Each screen fits 160 plain
characters, and the menu's place is kept in Redis under the session ID for 3
minutes. An answer takes longer than a screen can wait, so the session ends
with "your answer is on its way by SMS" and the answer follows as one SMS of
two pages at most (5 a day per number). A report is described by keypad and
read (classified) at once, allowed 4 seconds before the rules decide alone. An
emergency then shows two numbers per service to try before anything else. An
everyday or public-safety report is placed by sub-metro and electoral area
from numbered lists; a personal-safety report is asked only for its sub-metro,
which it may skip. Then it is confirmed (with or without SMS updates) and
filed while the citizen waits for up to 8 seconds; if filing takes longer the
reference follows by SMS. Reports have no photos. A personal-safety report
shows its reference and where more numbers are, and asks about updates once,
which stay off unless the citizen says yes; any SMS about it says only the
reference. `scripts/ussd_simulator.py` plays a
phone against the API (Arkesel's request format, from its sample application),
so the menu can be tried locally.

USSD is proven against Arkesel's real gateway, not only the simulator: the
"Test My Service" tool in Arkesel's dashboard dials the endpoint exactly as the
live gateway does (free, no shortcode needed). On 14 September 2026 a full
report went through it (menu, description, Okaikoi South, Kaneshie, "File, and
SMS me updates", reference S288-VG6C filed with the Works Department): the
request format matched, the session held across 7 turns, and every screen fit.

WhatsApp (`whatsapp.py`, `whatsapp_conversation.py`) runs through Twilio.
Every webhook is checked with Twilio's own `RequestValidator` against
`PUBLIC_API_URL` (Twilio signs the address it called), answered at once, and
handled afterwards, since an answer can take 13 seconds; a repeated delivery is
ignored. A question gets a chat-length answer with numbered sources. A report
is read (classified) as soon as it is described, and becomes a draft for 15
quiet minutes. An emergency's first reply is every number to try, grouped by
service, before any question. An everyday or public-safety report needs an
electoral area (named in the message or asked for); a personal-safety report
is asked only for its sub-metro, which it may skip, and an area it names is
kept only as its sub-metro. A draft gathers photos and is filed only when the
citizen replies 1, so a question the router misread is never filed. Photos are
fetched once, cleaned and held only with the draft, and deleted from Twilio at
once. A case reference gets its status. A personal-safety report gets its
reference and updates only after YES. "Thanks" gets no reply (each costs money),
and at most 60 messages an hour per number are handled. A voice note is heard
and handled as if typed (below). `scripts/whatsapp_simulator.py` sends signed
webhooks locally, a voice note (`--voice FILE`, served from this machine as
Twilio would serve it) and a pin (`--pin`) included; with
`WHATSAPP_PROVIDER=log` replies only reach the API's log.

Voice notes (`whatsapp_voice.py`, `voice_transcribe.py`, `voice_speech.py`,
`voice_audio.py`). A voice note is fetched from Twilio once and deleted there at
once; the recording is never stored. Up to 3 minutes, 10 an hour per number.
Gemini 2.5 Flash listens to it directly, at temperature 0, told the AMA's
electoral areas and sub-metros (so "Kaneshie" isn't heard as "Canashy"), its
common terms (market stall, levy, property rate, business operating permit,
fee-fixing, rates, tolls, permit: a live test heard "market stall" as "market
store" before they were added) and how a reference is spelled, and returns what was said, in the language spoken and
in English, and whether it was clear. Any language is accepted: the English is
what Nokware acts on, exactly as if typed, through every step of the chat, and
a lone spoken choice ("one", "yes", "remove") or a spelled-out reference reads
as its typed form, so someone who can't type can use every menu. The words are
shown back ("I understood: …", marked "translated by machine" when they were)
with a question's answer and in the confirm before a report is filed, so a bad
transcription is caught by the person who said it; the audit trail records that
a description is a confirmed machine transcription. A transcript with more
words than the note's length could hold is taken as unheard: on a half-second
note Gemini invented a whole sentence. Only a question's answer is also spoken:
after the text answer (which carries the sources), a voice note of about 50
seconds of its gist, in English, ending "The sources are in the message above."
It is never spoken when Gemini or the report rules' danger words say the note
is about harm to a person, nor for a report, a status, a safety or a medical
reply: a voice note about abuse could play aloud near the abuser. Speech is
Gemini's (`GEMINI_TTS_MODEL`, a preview model, and `GEMINI_TTS_VOICE`), encoded
with PyAV (FFmpeg bundled in its wheel, so nothing to install on the server) as
OGG/Opus, the only OGG Twilio takes, which WhatsApp plays as a voice note; MP3
is the fallback. Twilio fetches it from `GET /api/channels/whatsapp/audio/{name}`:
a random link, held in Redis for 10 minutes, deleted when Twilio reports on the
message and kept out of the access log. Twilio keeps its own copy in its media
store, which would tie the answer, and so the question, to the citizen's number:
it is deleted when Twilio reports the message delivered (or read), failed or
undelivered, never on sent or queued; one Twilio never reports on is deleted a
day after it was sent by the hourly purge job (`CONTACT_PURGE_INTERVAL_SECONDS`). A spoken reply is a second WhatsApp
message (WhatsApp drops text sent with audio), so there are 10 a day per number
and `VOICE_DAILY_LIMIT` (default 20) across everyone; past either, or on any
failure, the text answer stands alone.

WhatsApp allows free-form messages only within 24 hours of the citizen's last
message. Each message they send opens that window in Redis; a notification
outside it goes by SMS to the same number when it is Ghanaian and the citizen
isn't getting SMS already, and so does one Twilio reports undelivered for that
reason (error 63016, on the signed status callback).

Known limitations:

- Arkesel does not sign USSD callbacks yet (its signing guide says USSD waits
  on gateway work). Until it does, the USSD callback is protected only by the
  secret token in its URL (`ARKESEL_USSD_TOKEN`), which anyone who learns the
  URL (from a log or a proxy, say) could use to post fake sessions. The API
  redacts it from its own access log (`RedactChannelSecrets` in `main.py`), but a
  proxy in front of it, or ngrok's inspector in development, still records
  it. When Arkesel signs USSD, it moves to the same verification as SMS.
- While the sender ID is unregistered (the account sends as "Jay" meanwhile),
  Arkesel holds each real SMS for approval: in testing, about 15 minutes
  before delivery. Notifications and USSD answers therefore don't arrive
  promptly until the sender ID is registered; registration (a letter of
  authorization, approved over some days) is the fix.
- WhatsApp updates outside the 24-hour window need message templates approved
  by WhatsApp, which the Twilio sandbox can't have. Until a WhatsApp sender with
  approved templates exists (a production step), those updates go by SMS to
  Ghanaian numbers and are not delivered to others.
- Twilio keeps its own log of message bodies. The API deletes incoming photos
  and voice notes, and the spoken replies it sent, from Twilio's media store,
  but what a citizen typed, and the text replies, stay in Twilio's message log
  until deleted there.
- Voice in languages other than English is untested. Twi, Ga and Ewe haven't
  been tried with real speakers. In testing, a clear French note was heard as
  Twi-sounding words and marked unclear (so the citizen was asked to try again
  or type): the prompt's Ghanaian context pulls Gemini towards Twi. Spoken
  replies are English only. "I understood: …" is the safeguard, not a
  guarantee.
- Very short voice notes are unreliable: a half-second "one" was heard as
  "Hello". A wrong short word only re-asks the question, and invented sentences
  are rejected, but typing a menu choice is surer.
- A voice note is sent to Google's Gemini API to be transcribed, as typed text
  already is to be read, classified and answered. The recording isn't kept by
  Nokware.
- Gemini's speech model is a preview (`gemini-2.5-flash-preview-tts`) and may
  change or be withdrawn; `GEMINI_TTS_MODEL` swaps it without a code change, and
  if speech fails the text answer is still sent.

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
