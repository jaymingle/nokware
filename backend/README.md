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

At startup the API checks that `POSTGRES_URL` reaches the Ledger's search index
(`app/services/search_index.py`): the database it names, holding
`document_chunks` with its 768-dimension embeddings. Postgres comes through a
tunnel on a local port, and another program can take that port; the log then
says so plainly ("Something answers on localhost:5433, but it isn't Nokware's
search index…") instead of Ask failing 30 seconds into a resident's first
question with "password authentication failed". The API starts either way:
reports, the portal and petitions don't need the index, and Ask and the Ledger
search answer 503 until it is fixed.

## API

The Ask routes and the published-file link are public. Every other route needs
an Appwrite JWT (`account.createJWT()` in the browser) as
`Authorization: Bearer <jwt>`; the server resolves the role from the user's team
membership.

| Route | Who |
|---|---|
| `POST /api/ask` (whole answer) | public |
| `POST /api/ask/stream` (newline-delimited JSON events: stage, sources, answer text, done) | public |
| `POST /api/ask/export` (`view`: an answer's signed export view, `format`: `pdf`, `docx` or `csv`; the file as an attachment) | public, 30 an hour per client |
| `POST /api/ask/voice` (multipart `audio`, up to a minute; returns the words to check, asks nothing) | public, 20 an hour per client |
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
| `GET /api/publishing-record` (the documents AMA is required to publish, against what the Ledger holds, by year; cached ten minutes) | public |
| `GET /api/responsiveness` (each Assembly department's handling of reports and contributors' documents, last twelve months; cached a minute) | public |
| `POST /api/phone/challenges`, `/challenges/status`, `/challenges/sms`, `/challenges/sms/confirm` (confirm a phone number; the secret in the body) | public, rate-limited per client |
| `GET /api/petitions/options`, `GET /api/petitions` (`?group=open\|awaiting\|responded\|closed`, `?topic`; with the MCE's moderation record), `GET /api/petitions/{number}`, `/ledger` | public |
| `POST /api/petitions/check`, `POST /api/petitions/ledger` (a draft's words checked; what the Ledger holds on its subject) | public, 30 an hour per client |
| `POST /api/petitions`, `GET /api/petitions/mine`, `POST /api/petitions/{number}/resubmit`, `/withdraw`, `/anonymous` | the creator (`X-Phone-Proof`) |
| `POST /api/petitions/{number}/signatures` (`show_name`, `name`), `GET /api/petitions/{number}/signature`, `POST .../signature/anonymous` | the signer (`X-Phone-Proof`) |
| `GET /api/petitions/{number}/names` (the names signers chose to show) | public |
| `GET /api/petitions/review`, `POST /api/petitions/{number}/decision` (`publish`, or `refuse` with a fixed `reason`), `GET /api/petitions/responses`, `POST /api/petitions/{number}/response` (`kind`: `will_act`, `referred` or `cannot_act`; `text`; `department`; `documents`) | MCE |
| `POST /api/speech/answer` (`view`: an Ask answer's signed export view), `POST /api/speech/report` (`reference`, `kind`); each with `part` (from 0): that part as MP3, and `X-Speech-Parts` saying how many | public, 120 an hour per client |
| `/mcp` (an MCP server over streamable HTTP, stateless: the `count_reports` and `personal_safety_figures` tools; see [Report figures for AI clients](#report-figures-for-ai-clients-mcp)) | public, no sign-in, 120 requests per 10 minutes per client |
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

**Speaking a question on Ask** (`POST /api/ask/voice`): a microphone beside the
question box. The browser records up to a minute (WebM/Opus in Chrome and
Firefox, MP4/AAC in Safari, re-encoded for Gemini) and sends it once; it goes
through the same pipeline as a WhatsApp voice note (`voice_transcribe.listen`),
and comes back as words, never an answer. The page shows "I understood: …"
(marked "translated by machine" when it wasn't English) with Ask this, Edit and
Discard: nothing is asked until the person chooses, so a mishearing is caught
before it becomes a question. The recording is held in memory only, never
stored, and its words are never logged. 20 an hour per client, since each is a
Gemini call. French from a natural voice was heard word for word in testing;
the robotic macOS French voice was misheard, and Twi is untested (see the voice
limits below).

**Read aloud** (`app/services/read_aloud.py`, `app/routes/speech.py`): a speaker
button on Ask answers, report confirmations and report status pages, the places
where the content is prose someone needs to understand and not being able to
read it locks them out. Not a whole-page reader: screen readers do that better.
It reuses WhatsApp voice's Gemini speech, as MP3 (every browser plays it). It
speaks only what the API produced, never text a browser sends: an Ask answer
comes back as its signed export view, and a report is looked up by its
reference (in the request body, never the address). So it can't be used as a
free text-to-speech service. Nothing about someone's safety is read aloud,
WhatsApp's rule: no personal-safety report, and no Ask answer whose question or
answer carries words of danger to a person (each answer says whether it is
`speakable`, so the page shows the button only where it works). An answer is
read up to about two and a half minutes, then "The rest of the answer is on the
screen." A reading is made in parts that end at sentences (`X-Speech-Parts`
says how many; the page asks for the next while one plays), because the speech
model takes about two thirds as long to speak as the audio lasts: the first part
is short, so the first words come in about seven seconds. The same words are
spoken once and kept in Redis for six hours; `READ_ALOUD_DAILY_LIMIT` (300) caps
fresh parts a day.

**Characters some PDFs lost, mended at ingestion.** Some of the Assembly's
PDFs store ligatures and bullets in a font's private characters: "flooding"
came out as a private character followed by "ooding" ("fi" as U+F001, "fl" as
U+F002), bullets as U+F0B7 and its neighbours, and one document's full stops
were lost outright (U+FFFD). On 15 September 2026 that was 740 of the Ledger's
7,537 chunks, across 42 documents, and it hurt accuracy, not only looks: Ask's
keyword search couldn't match "flooding" in them. Ingestion now mends the text
before it is chunked and embedded (`app/services/pdf_text.py`): a ligature
becomes its letters and a font bullet "•"; a lost character becomes a space,
never a guessed letter. Documents stored before the fix are re-indexed through
the normal ingestion path by `scripts/reindex_mended.py` (a dry run by default,
which lists them with the embedding cost). Run on 15 September 2026: all 42
documents in 6.5 minutes, for about $0.15 of embeddings, with no unmended chunk
left. Chunks matching "flood" went from 234 to 252, and the AMA newsletters,
which weren't found for "flooding" before, now are: an Ask question about the
newsletters' reports on flooding and desilting is answered from three of them.

**Known limitation: Ga names can come out wrong.** Some PDFs set Ga letters
such as ɔ and ɛ in fonts whose text layer maps them to other characters: one
newsletter's "Nii Tetteh M)waam) I" has ")" where a Ga letter should be. Unlike
the ligatures, the mapping isn't a fixed private character that can be
restored: ")" is also real punctuation, so replacing it would corrupt other
text, and which letter it stood for can't be known from the text alone. It is
not fixed. For a civic tool for Accra, mangling Ga names is a real failing,
not a cosmetic one; the fix needs the PDFs' fonts read glyph by glyph, or OCR
of those pages, and comparison against the printed page.

### Exports and charts

Every Ask answer can be downloaded as a PDF, a Word document or a CSV
(`ask_export.py`, `export_pdf.py`, `export_docx.py`, `export_csv.py`). Each
carries the question, when it was answered, the answer with its citations
numbered [1], [2] (live figures [F1]), and every cited source with its title,
department, year, provenance line (the web's words), original URL and
Nokware's copy. Every page is headed with Nokware's mark and "Generated by
Nokware from the Accra Metropolitan Assembly's published documents. This is not
an official AMA document.", and footed "Machine-written by Nokware's Ask from
the sources listed. Check them before relying on it." with the page number; the
PDF's and Word file's author reads "Nokware (not an official AMA document)". A
printout can't pass for an Assembly publication. The CSV is one file with a
`section` column; each live figure and each line of its breakdown is a row with
the count in `value`, and "fewer than 5" leaves `value` empty (saying so in
`shown_as`) so a spreadsheet can't add it up. Numbers quoted from documents stay
in the answer's text until the documents' tables can be read accurately. A cell
that would start a formula is prefixed with an apostrophe.

Nothing is stored: each answer comes with its export view, signed with a key
derived from the server's secret, and the export route renders only a view whose
signature holds, so the server can't be used to print Nokware-branded documents
with invented words. Text is set in the site's fonts, Fraunces and Public Sans,
static cuts in `app/fonts` (see its README); Public Sans has no cedi sign (₵) or
Ghanaian letters (ɛ, ɔ), so those characters are set in Noto Sans.

A question can ask for a chart ("show reports by sub-metro as a pie chart",
"graph the reports each month this year"), and `ask_charts.py` decides it from
the answer's cited live figures only. It draws the kind the question names,
unless that kind can't show the data honestly; then the nearest honest kind,
with one line saying why. Unnamed, it is a line over time (live figures can now
break down by month, from Nokware's first report), bars otherwise, horizontal for
long labels. "Fewer than 5" is a range from 1 to 4, never a value: hatched on a
bar, a dashed span on a line. So a pie or donut is never drawn with one in the
set (a slice needs a size), nor a stacked bar (an unknown segment shifts every
one above it); a pie of separate, possibly overlapping counts becomes bars; and
a line across unordered categories becomes bars. The web draws the chart
(`answer-chart.tsx`); the exports draw the same decisions with Pillow
(`export_chart.py`). A chart of document data is refused in fixed words, "The
tables in AMA's documents aren't yet read in a form that can be charted
accurately, so I'd rather give you the figures in text than a chart that might be
wrong.": pypdf flattens a table's columns, a chart inside a PDF comes through as
its axis ticks, and an answer rests on a few passages, not a whole table. Charts
of document data wait for the table extraction.

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

SMS goes through Arkesel (`sms.py`) when `SMS_PROVIDER=arkesel`, or through
BMS Africa (`sms_bms.py`, mNotify's API) when `SMS_PROVIDER=bms`; `log`, the
default, records each message as not sent. BMS is there because "Nokware" is
an approved sender ID on it, so its messages go at once rather than being held
for review; Arkesel stays in place, and USSD stays on Arkesel either way. BMS
has no sandbox: every message it accepts is sent and charged, within the same
daily page limits. Every message fits one SMS page
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
anything where someone could be hurt. Personal safety adds DOVVSU, the
Police's Domestic Violence and Victim Support Unit (its helpline as the Police
publish it on police.gov.gh, checked 15 September 2026), the Police reporting
lines (marked, as everywhere, as reported via X and not independently
verified), the Helpline of Hope and Social Welfare (the citizen's sub-metro
desk, or every desk, and the head office). A source may carry its own checked
date where it was checked apart from the rest. The web and WhatsApp show the
full list, and USSD the verified numbers that can be called from the phone in
hand; an SMS about a report, which
can't hold it, gives two numbers per service and points to
`/contacts/emergency`, a page of emergency numbers only (no "Who represents
you": safety reporters are never pointed to an Assembly Member, an elected
politician who in a small area may know the abuser). An SMS about a
personal-safety report never carries numbers: it says only the reference. The
numbers reach a safety reporter's phone by SMS only if they ask for them at the
end of a USSD report, told first that anyone with the phone could see them.
After a personal-safety report's numbers, every channel shows the same steps
for right now (`app/safety_steps.py`: leave for a neighbour, family or the
nearest police station if you can; ask there for DOVVSU; keep your phone; a
hospital or 193 if hurt; don't confront the person when it's someone else):
the web safety form and a private report's receipt, the first WhatsApp reply,
and two USSD screens. A road accident is a public-safety report to the Police
with Police and ambulance numbers. A medical emergency (someone ill or hurt, no
one else involved) isn't the Assembly's to act on: WhatsApp, USSD menu 4 and a
USSD report whose description reads as medical say so plainly, file nothing,
and give the ambulance numbers.

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

BMS sends no delivery reports at all: it has no SMS webhook, signed or not. So
`bms_deliveries.py` asks it instead: every `BMS_DELIVERY_POLL_SECONDS` (120),
for each BMS message sent between a minute and two days ago whose delivery
isn't settled, it reads the campaign's report and sets the outbox row's
`deliveryStatus` as a webhook would, so staff see DELIVERED or FAILED
whichever provider carried the message. This gives up Arkesel's HMAC
verification, but deliberately: with no webhook, nothing comes in, so there is
nothing to forge. The API makes outbound requests to BMS over HTTPS and trusts
the answers as it trusts any response from BMS. It is a different shape of risk
rather than a worse one. What it costs is time: a status arrives up to two
minutes after BMS knows it, where a webhook is immediate.

BMS takes its API key as a query parameter (`?key=`), never a header, so the
key is in every request's address. It never reaches a log, a stored error or
the outbox: errors name the failure and never echo the address (an unreachable
gateway is reported by its error type alone, and BMS's own words are stripped
of the key and of any phone number), and a filter redacts `key=` from httpx's
request log line, the one place a library writes the address.

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
read (classified) at once, allowed 4 seconds before the rules decide alone.
Help comes first, filing second: an emergency then shows every number to call
for it, under "In danger now? Call 112", before any other question. The
services that come to you are listed first (the Police, DOVVSU, Fire, NADMO,
the ambulance, which every emergency where someone could be hurt includes),
then the Helpline of Hope and Social Welfare; a fire or a flood fits one
screen, personal safety two. The Police reporting lines, reported on X and not
independently verified, stay on the web and WhatsApp: a keypad session can
time out, and their screen is better spent on DOVVSU's verified line. A
personal-safety report then shows the steps for right now on two screens. An
everyday or public-safety report is placed by sub-metro and
electoral area from numbered lists; a personal-safety report is asked only for
its sub-metro, which it may skip, and its Social Welfare desk's number is shown
as soon as the sub-metro is chosen. Then it is confirmed (with or without SMS
updates) and filed while the citizen waits for up to 8 seconds; if filing takes
longer the reference follows by SMS. Reports have no photos. A personal-safety
report shows its reference and where more numbers are, and asks about updates
once, which stay off unless the citizen says yes; any SMS about the report says
only the reference. Last it asks "Send these numbers by SMS? Anyone with your
phone could see them." Yes sends one SMS of two pages at most (the citizen's
desk included, nothing saying what happened; three a day per phone); no sends
nothing. The session ends by saying the phone's call list may show the dial.
Medical emergencies aren't filed; they get the ambulance numbers at once,
from menu 4 or when a description under "Report an issue" reads as medical
(the quick model, as on WhatsApp, run beside the reading within the same 4
seconds; not knowing in time means not medical). Because the model can misread,
that screen offers "1 File it as a report anyway". `scripts/ussd_simulator.py` plays a
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
note Gemini invented a whole sentence. So is one that repeats Gemini's own
instructions, which it did once on a clip it couldn't make out (words per second
only catches that on a recording under about a minute). Only a question's answer is also spoken:
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
- While the sender ID is unregistered on Arkesel (the account sends as "Jay"
  meanwhile), Arkesel holds each real SMS for approval: in testing, about 15
  minutes before delivery. With `SMS_PROVIDER=bms` SMS goes as the approved
  "Nokware" and isn't held; USSD answers, which only Arkesel carries, still
  wait on the registration (a letter of authorization, approved over some
  days).
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
  or type): the prompt's Ghanaian context pulls Gemini towards Twi. Later, two
  French questions in a natural voice (Gemini's own speech) were heard word for
  word with a correct English translation, while macOS's robotic French voice was
  misheard or unheard. Real French speakers haven't been tried. Spoken
  replies are English only. "I understood: …" is the safeguard, not a
  guarantee.
- Very short voice notes are unreliable: a half-second "one" was heard as
  "Hello". A wrong short word only re-asks the question, and invented sentences
  are rejected, but typing a menu choice is surer.
- A voice note is sent to Google's Gemini API to be transcribed, as typed text
  already is to be read, classified and answered. The recording isn't kept by
  Nokware.
- Gemini's speech model is a preview (`gemini-3.1-flash-tts-preview`) and may
  change or be withdrawn; `GEMINI_TTS_MODEL` swaps it without a code change, and
  if speech fails the text answer is still sent. It replaced
  `gemini-2.5-flash-preview-tts`, which in September 2026 took longer than the
  audio lasted and often stalled for 30 seconds and dropped the connection on a
  few hundred characters; 3.1 spoke the same text in about two thirds of its
  length without a failure.

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

Four public surfaces read citizen reports: the dashboard, Ask's live figures,
the MCP server and the issue list. They share one set of rules
(`app/services/stats.py`):

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

### Report figures for AI clients (MCP)

`/mcp` (`app/stats_mcp.py`) is an MCP server that lets an outside AI client
(Claude, ChatGPT, a newsroom's own agent) query the same live figures Ask uses.
It has Ask's two tools and nothing else: `count_reports` (Ask's `CountReports`:
a topic, category, status, electoral area, sub-metro, department and period,
optionally broken down by topic, sub-metro or month) and
`personal_safety_figures`, which gives the fixed refusal. The counting is
`stats.py`'s, so every rule above holds: personal safety is never counted and
is not a topic the tool accepts, and 1 to 4 reads "fewer than 5". Each result
says what was counted, when (at most a minute ago), and that these are
reports residents filed with Nokware, not the Assembly's own records.

It is read-only, needs no sign-in, and is rate-limited per client address.
It runs inside the API process (stateless streamable HTTP with plain JSON
responses, so no session state and no sticky routing), accepts only the
API's own host (`PUBLIC_API_URL`) and localhost as the `Host` header, and
refuses browser origins: it is for MCP clients, not web pages. To connect a
client, give it `https://<API host>/mcp`.

**A deliberate decision: the MCE gets no more through MCP than the public
does.** It would have been easy to add a signed-in path where the MCE sees the
personal-safety counts that public Ask refuses. We decided not to, for three
reasons:

- **Differencing.** A query tool is not a fixed figure. Anyone who can ask for
  counts freely can subtract one answer from another (a sub-metro total less
  its other topics, this month less last month) and recover a cell that "fewer
  than 5" hides. For personal safety, a count by electoral area and month can
  point to one household. Leaving personal safety out entirely is the
  protection that matters, and a signed-in path would put it back.
- **Results leave Nokware.** An MCP result lands in an outside AI client's
  context, transcripts and logs, run by another company under its own
  retention rules. Nokware decides how long what it holds is kept; it has no
  say over how long a figure lives in someone else's chat history.
- **The MCE already has what the job needs.** The portal shows the MCE the
  open personal-safety count metro-wide (as "fewer than 5" below five) and
  every personal-safety case in outline: its status, recipients, age and
  history, without the resident's words or photos. The MCE can see whether
  safety cases are being handled without being able to query them.

If the Assembly needs more, the way to give it is another fixed, suppressed
figure in the portal (open safety cases by sub-metro, say), not a query tool.
Sign-in would only matter on `/mcp` if it widened what comes back, so there
is none.

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

## Accountability

Two public pages publish evidence about the Assembly itself, not only its
documents.

The publishing record (`app/services/publishing_record.py`,
`/accountability/documents`) sets what the Assembly is required to publish
against what the Ledger holds, year by year, from 2021. The list, in four groups
(vision and plans; budget and tariffs; financial and audit; oversight and RTI),
is in `app/data/statutory_documents.json`: each document's cadence (annual,
quarterly, or the 4-year development-plan period), title patterns for the
document itself and for documents only related to it, and when it counts as
expected. Each period is held, related documents only (a monitoring and
evaluation report is not an Annual Progress Report), not found, or not yet
expected. A gap says exactly what was checked, "Not found in ama.gov.gh's
Documents Centre (checked 12 September 2026) and not in The Ledger", never that
the document doesn't exist, links to `/rti` with the request worded, and sits
beside what the Ledger does hold that year from the same departments or
categories. The Auditor-General's and Public Accounts Committee reports name who
issues them, and a PAC report, on no fixed schedule, is never marked missing.
The "expected" dates are our own conservative assumptions, not statutory
deadlines: confirm the dates under the Local Governance Act, 2016 (Act 936)
before the record is used for real. `scripts/publishing_record_matches.py`
prints every match the rules make, for a person to confirm; a wrong one is
corrected under `confirmed` in the data file (the document's ID to a
requirement and year, or to null to set it aside). Update
`documents_centre_checked` whenever the Documents Centre is imported again.
Test documents are left out.

Departmental responsiveness (`app/services/department_responsiveness.py`,
`/accountability/departments`), over the last twelve months: for each Assembly
department, reports received, resolved and still open; still waiting to be
started after 7 days (reports don't expire, so this is the measure chosen, not a
statutory deadline); the median days until work started and to resolve; the
resolutions residents said weren't fixed, and whether the MCE confirmed them or
sent them back. For contributors' documents: accepted, disputed, or left to
publish automatically when the 72-hour review clock ran out, and the median
review time; and for the MCE, escalated disputes ruled on against those left to
run out. The public rules hold: personal safety is left out entirely, a count
from 1 to 4 reads "fewer than 5", a median needs five cases, and where two counts
add up to one that is shown (resolved and still open make up received), hiding
one hides the other. Departments are listed by name, never ranked. The Police and
GNFS are national agencies, not Assembly departments, and are left off.

**Roadmap:** a department-written, one-line public title for an issue (for
example "Pothole on Kaneshie market road near the footbridge"), added when the
department starts work, so residents can tell similar issues apart without the
citizen's own words ever being published.

## Petitions

A resident can ask the Assembly to act, publicly, and gather support for it.
The rules are in `app/services/petition_rules.py`; storage, the MCE's decision
and the clocks in `app/services/petitions.py`.

- **Drafting.** The ask ("what we're asking the Assembly to do"), why, a topic
  (everyday topics and public-safety ones an Assembly department handles; never
  personal safety, nor what only the Police or the Fire Service handle), the
  whole Assembly or one electoral area, and optionally an open issue and up to
  three Ledger documents to cite. Words of danger to a person stop it (it goes
  through Report, privately) and so does personal data found by pattern (a phone
  number, an email address, a Ghana Card number); both are checked again on the
  server. Gemini's reading that it names a private person only warns: a model can
  be wrong about who is a public official, so the creator decides and the MCE
  can refuse it (`app/services/petition_screen.py`).
- **A confirmed phone.** Starting a petition needs a Ghanaian mobile number,
  confirmed from the page (`app/services/phone_proof.py`): by WhatsApp (the page
  opens a chat with "Nokware code 482173" typed; Twilio says who sent it) or
  USSD (option 5, then the code; the network says who dialled), or by an SMS
  code (`SMS_VERIFICATION_CODES=true`) with `SMS_PROVIDER=bms`, where "Nokware"
  is an approved sender. Codes need an approved sender: an unregistered
  one's messages are held for about 15 minutes, so on Arkesel they stay off
  until its sender ID is registered. They have a daily cap of their own. The page then holds a sealed proof
  (AES-GCM) for 12 hours; no number is ever in Redis. Each WhatsApp confirmation
  costs one reply message.
- **The MCE's review, which can't be a veto.** The MCE is usually the petition's
  target. They have 72 hours to publish it or refuse it, and may refuse it only
  for a fixed reason (names a private individual, about personal safety,
  duplicates an open petition, not the Assembly's responsibility, hate speech or
  incitement, personal data), with an optional note to the creator. If they
  decide nothing in 72 hours it **publishes automatically**. The creator can
  edit and send a refused petition back twice. The public list shows how many
  are waiting, how many the MCE published and how many published themselves,
  and every refusal by reason. These counts are exact, not "fewer than 5": they
  count the MCE's decisions, not people.
- **Open for 90 days**, at `/petitions/{number}` (a six-digit number, so it can
  be typed on a keypad or read aloud), with what The Ledger already holds on its
  subject beside it: someone petitioning about drainage sees the Assembly's own
  flood plans and budget lines, to strengthen the case or to find the commitment
  already exists and wasn't kept. The match is by search, and the page says it
  means a document touches the subject, not that it commits to what's asked.
- **Signing** (`app/services/petition_signatures.py`): one signature per
  confirmed Ghanaian number per petition, on the petition's page (with a number
  confirmed by WhatsApp, USSD or, once switched on, SMS; a tab that has
  confirmed a number signs further petitions without another message) or by
  USSD alone (option 6, then the petition's six-digit number). A signature
  holds no phone number, only a keyed hash of number and petition together,
  under a unique index: a number can't sign twice, and no one can list what a
  number has signed. The count is recounted under the petition's lock after
  every signature.
- **Thresholds** (`PETITION_THRESHOLD_AREA=150`, `PETITION_THRESHOLD_METRO=500`)
  are fixed on a petition when it opens. The signature that reaches it sends the
  petition to the MCE, who has 30 days to respond publicly, counted down on the
  page. It keeps taking signatures until its 90 days are up, and can no longer
  be withdrawn.
- **The MCE's response** (`app/services/petition_responses.py`): one of three,
  the Assembly will act, it's referred to a department (named), or the Assembly
  can't act and why, always with a written statement and optionally up to three
  Ledger documents. It is published on the page as given and can't be changed;
  the trail keeps the MCE's name, the page says "the MCE". Once answered, the
  petition takes no more signatures. If 30 days pass first, the petition clock
  (`app/services/petition_clock.py`) records it once and the page says plainly
  "No response 30 days after the petition reached its threshold." A late
  response is still taken, and the page says how many days late it came.
- **Updates to the creator** (`app/services/petition_updates.py`), at seven
  moments: refused (with the reason), published by the MCE, published
  automatically, reached its threshold, responded, no response after 30 days
  (the moment the outcome becomes a fact about the Assembly rather than a
  pending matter), and closed short of its threshold. Neutral wording, like
  report messages: what happened, the number, the link. Each fits one SMS page
  in plain GSM-7. On the channel the creator confirmed with: WhatsApp while its
  24-hour window is open, otherwise SMS to the same number; USSD and SMS
  confirmations get SMS. Each is a credit or a WhatsApp message, so a petition
  costs at most four messages in a normal life (published, threshold, then
  response or no response). Each leaves a private line in the trail.
- **Names are the person's choice.** Anonymous by default; a name is shown
  publicly only if its owner chooses, told first that anyone can see it,
  including the department the petition concerns, and it can be taken off
  later. In a city where retaliation is a real concern, forcing a public list
  would suppress signing on exactly the petitions that need it most, so the
  choice is the signer's, not the platform's. Anonymous support still counts.
- **The creator's number** is kept only as a keyed hash (so they can find their
  petition again by confirming their number) and, encrypted, for updates about
  it; the number is deleted 30 days after the petition closes, is withdrawn, or
  is refused and not sent back.

`scripts/create_petitions.py` creates the collections (a dry run by default;
run it with `--yes` before deploying this code).

**Known limit, stated rather than hidden:** the count is of confirmed numbers,
not of people. Someone with several SIM cards can sign once with each. A daily
cap per number (30 petitions) and a per-connection limit slow a flood, but
don't stop a determined one; the page counts "signatures from confirmed
Ghanaian numbers", and that is what it is.

**On the accountability pages** (`app/services/petition_figures.py`), over the
last twelve months: petitions sent, published by the MCE, published
automatically, refused (by reason); and of those that reached their threshold,
how many the MCE answered within 30 days, answered late, hadn't answered after
30 days, or still has time for. Exact counts: they count the MCE's decisions on
public petitions, not residents.

**Stages.** P1: drafting, the confirmed phone, the MCE's review with the 72-hour
clock, the public pages. P2: signing, one per confirmed number per petition,
and the threshold sending it to the MCE. P3 (this), as planned: the MCE's public
response within 30 days, counted down, with "No response 30 days after the
petition reached its threshold" stated plainly when it runs out; updates to the
creator; petition figures on the accountability pages.

**Roadmap:** messages to signers when the MCE responds. Only the creator gets
updates for now: WhatsApp can't reach someone outside the 24-hour window without
approved message templates, and an SMS to every signer could cost hundreds of
credits. The public page carries the response.

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
