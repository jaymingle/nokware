# Deploying Nokware

Everything needed to put Nokware on the VPS from scratch, with Coolify. Two
services, built from this repository: the API (`backend/`) and the public site
and portal (`frontend/`). Appwrite and MinIO already run on the VPS and stay as
they are. Postgres (with pgvector) and Redis also run on the VPS; the API
reaches them directly, with no SSH tunnel.

Nothing here is secret. Secret values live in Coolify's environment settings
(and the team's password manager), never in this repository.

| | Address |
|---|---|
| Public site and portal | `https://nokware.tstitagency.com` |
| API | `https://api.nokware.tstitagency.com` (see *Decisions* if a different name is chosen) |
| Appwrite | `https://appwrite.tstitagency.com/v1` (unchanged) |
| MinIO | `s3.tstitagency.com` (unchanged) |

## Decisions to settle before starting

1. **The API's address.** `api.nokware.tstitagency.com` is assumed throughout.
   If `nokware-api.tstitagency.com` is chosen instead, replace it everywhere
   below: the DNS record, `PUBLIC_API_URL`, `NEXT_PUBLIC_API_URL`, and the
   Twilio and Arkesel callback addresses.
2. **How Postgres and Redis run on the VPS.** Either as Coolify-managed
   resources (the API joins their Docker network and uses their internal
   hostnames), or on the host itself (the API reaches them through the Docker
   host gateway, and Postgres's `pg_hba.conf` must admit the Docker network).
   The first is simpler; the connection strings below use `<postgres-host>` and
   `<redis-host>` for whichever it is.
3. **Redis database number.** Production shares the VPS's Redis with another
   product. Nokware's keys all start `nokware:`, but it should still have a
   database number of its own (for example `/2`). Pick one that is free.
4. **Live SMS from the first day: decided, yes.** SMS goes through BMS with
   verification codes on, so report notifications, petition updates and codes
   are real and charged from deployment, within the daily caps. Real messages
   arriving is the point; a demo where the SMS never comes is worse than one
   that costs a few credits.

## What the repository already provides

- `backend/Dockerfile`: Python 3.11, dependencies installed within
  `backend/constraints.txt` (the exact versions the tests pass on). The build
  fails if PyAV's FFmpeg can't encode Opus and MP3 (voice needs both). Runs as
  a non-root user, one uvicorn worker, with proxy headers, and a `/health`
  healthcheck.
- `frontend/Dockerfile`: Node 22, `next build` with `output: "standalone"`,
  the three `NEXT_PUBLIC_*` values as build arguments, non-root, port 3000.
  `frontend/package-lock.json` was regenerated in a Linux Node container, so it
  lists the optional packages only Linux installs and `npm ci` accepts it in the
  image (a lockfile made on macOS alone leaves them out, and the build fails).
- `backend/.dockerignore` and `frontend/.dockerignore`: no `.env` files, caches
  or tests go into an image.
- The design-tokens page (`/dev/tokens`) already answers 404 in a production
  build.

## Constraints that must hold

- **The API runs as one instance, with one worker.** The Ledger's deadline job
  (72-hour clocks), the petition clock (72-hour review, 90-day close, 30-day
  response) and the purge of expired phone numbers run inside the API process,
  and the locks that stop two changes to one record interleaving live in that
  process too. Two instances would run every job twice. In Coolify, never
  scale the API above one replica. A rolling deploy briefly runs the old and
  new containers together; the jobs re-read each record under its lock before
  acting, so the worst case is a duplicate line in a trail during those
  seconds.
- **The API's port is reached only through Coolify's proxy.** The container
  trusts the proxy's `X-Forwarded-For` so that rate limits (per client address)
  see each resident rather than the proxy. Don't publish port 8000 directly.
- **SMS goes through BMS (`SMS_PROVIDER=bms`), and it is live.** "Nokware" is
  an approved sender ID on BMS, so messages aren't held for review, which is
  what lets SMS verification codes go live (`SMS_VERIFICATION_CODES=true`). BMS
  has no sandbox: every report notification, petition update and code is
  delivered and charged. `SMS_DAILY_LIMIT` (50 pages) and `SMS_CODE_DAILY_LIMIT`
  (30) bound a day's spend. To deploy without live SMS instead, set
  `SMS_PROVIDER=arkesel` with `ARKESEL_SANDBOX=true` and
  `SMS_VERIFICATION_CODES=false`.
- **`ARKESEL_SANDBOX=true`.** Arkesel still carries USSD; its SMS provider
  stays configured as the fallback, in its sandbox.

## 1. DNS

At whoever hosts `tstitagency.com`:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `nokware` | the VPS's public IPv4 address | 300 |
| A | `api.nokware` | the VPS's public IPv4 address | 300 |

(Add matching AAAA records only if the VPS has IPv6 and Coolify's proxy
listens on it.) Wait until both names resolve to the VPS
(`dig +short nokware.tstitagency.com`) before deploying: Coolify's proxy asks
Let's Encrypt for each certificate on first request, and that fails while DNS
points elsewhere.

Appwrite at `appwrite.tstitagency.com` is on the same site as
`nokware.tstitagency.com`, so the browser's Appwrite session is a first-party
cookie and sign-in doesn't depend on third-party cookies.

## 2. Appwrite: add the web platform

Without this, Appwrite refuses sign-in from the new address (a CORS error in
the browser).

Appwrite console → the Nokware project → **Overview → Platforms → Add
platform → Web** → name `Nokware`, hostname `nokware.tstitagency.com`. Keep the
existing `localhost` platform for development.

## 3. New secrets to generate

Generate each once, store it in the password manager, and paste it into
Coolify (step 5):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # PHONE_KEY_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # ARKESEL_USSD_TOKEN (new)
```

- **`PHONE_KEY_SECRET`**: the secret behind the stored keyed hash of a
  confirmed phone number: who started a petition, and one signature per number
  per petition. Unset, it is derived from the Appwrite API key, so rotating
  that key would reset who has signed. Set it **before the first real petition
  or signature**, and never change it afterwards (changing it would let every
  number sign again, and creators would lose their petitions). There are no
  petitions or signatures now, so setting it at deployment changes nothing.
- **`ARKESEL_USSD_TOKEN`**: rotate it. Arkesel doesn't sign USSD callbacks, so
  the secret in the callback address is their only protection, and the current
  one has been in a public ngrok address during development. The new one goes
  into Coolify and into Arkesel's callback address (step 8) at the same time.
- **`JOB_TOKEN`** (optional): lets an outside scheduler call
  `POST /api/jobs/publish-expired`. The API runs the job itself, so leave it
  empty unless one is added.

## 4. Postgres and Redis

- **Postgres**: the same database the development tunnel reached
  (`nokware_rag`, user `nokware_user`, pgvector, table `document_chunks`). No
  data moves. The API needs a network path to it from its container (see
  *Decisions* 2).
- **Redis**: the VPS's Redis, on Nokware's own database number. It holds only
  short-lived state (USSD menus, WhatsApp drafts, phone-confirmation codes,
  per-number limits, the day's SMS count, read-aloud audio for six hours);
  everything in it expires.

## 5. Coolify: the API

New resource → **Application** → from the GitHub repository
`jaymingle/nokware`, branch `main` (connect Coolify's GitHub App, or a deploy
key, since the repository is private).

| Setting | Value |
|---|---|
| Build pack | Dockerfile |
| Base directory | `/backend` |
| Dockerfile location | `/backend/Dockerfile` |
| Port exposed | `8000` |
| Domains | `https://api.nokware.tstitagency.com` |
| Replicas | 1 (never more; see *Constraints*) |
| Health check | the Dockerfile's (`GET /health`) |

**Environment variables.** Every setting the API reads, with what changes
from development:

| Variable | Development | Production |
|---|---|---|
| `APPWRITE_ENDPOINT` | `https://appwrite.tstitagency.com/v1` | unchanged |
| `APPWRITE_PROJECT_ID` | the project's ID | unchanged |
| `APPWRITE_API_KEY` | secret | unchanged |
| `POSTGRES_URL` | `postgresql+psycopg://nokware_user:…@localhost:5434/nokware_rag` (tunnel) | `postgresql+psycopg://nokware_user:…@<postgres-host>:5432/nokware_rag` |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | `s3.tstitagency.com`, secrets | unchanged |
| `MINIO_LEDGER_BUCKET`, `MINIO_PHOTOS_BUCKET` | `nokware-ledger-files`, `nokware-report-photos` | unchanged |
| `GEMINI_API_KEY` | secret | unchanged |
| `CORS_ORIGINS` | empty | `https://nokware.tstitagency.com` |
| `CORS_ORIGIN_REGEX` | unset (default admits localhost on any port) | set to **empty**, so only the site above is admitted |
| `PUBLIC_API_URL` | the ngrok address | `https://api.nokware.tstitagency.com` |
| `PUBLIC_SITE_URL` | `http://localhost:3000` | `https://nokware.tstitagency.com` |
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://:<password>@<redis-host>:6379/<Nokware's number>` |
| `SMS_PROVIDER` | `arkesel` | **`bms`** (see *Constraints*: live and charged) |
| `WHATSAPP_PROVIDER` | `twilio` | unchanged |
| `ARKESEL_API_KEY`, `ARKESEL_SENDER_ID`, `ARKESEL_WEBHOOK_SECRET` | secrets | unchanged |
| `ARKESEL_SANDBOX` | `true` | `true` (see *Constraints*) |
| `BMS_API_KEY`, `BMS_SENDER_ID` | secret, `Nokware` | the same (the sender ID is approved on BMS) |
| `BMS_DELIVERY_POLL_SECONDS` | `120` | `120`: BMS sends no delivery reports, so the API asks it |
| `SMS_DAILY_LIMIT` | `50` | unchanged unless decided otherwise |
| `ARKESEL_USSD_TOKEN` | the development token | **the new token from step 3** |
| `USSD_SERVICE_CODE` | empty | empty until Arkesel confirms the dial code (e.g. `*920*123#`); then petition pages offer USSD |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | secrets | unchanged |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` (the sandbox) | unchanged until an approved WhatsApp sender replaces it |
| `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE`, `VOICE_DAILY_LIMIT` | `gemini-3.1-flash-tts-preview`, `Charon`, `20` | unchanged (leave `GEMINI_TTS_MODEL` unset or set it to the 3.1 model: 2.5 stalls on read-aloud's longer text) |
| `READ_ALOUD_DAILY_LIMIT` | `300` | unchanged: fresh read-aloud parts (about 25 seconds each) made in a day across everyone (repeats come from a six-hour cache) |
| `PETITION_THRESHOLD_AREA`, `PETITION_THRESHOLD_METRO` | `150`, `500` | unchanged |
| `SMS_VERIFICATION_CODES`, `SMS_CODE_DAILY_LIMIT` | `false`, `30` | **`true`**, `30` (with BMS; see *Constraints*) |
| `PHONE_KEY_SECRET` | unset | **the new secret from step 3** |
| `JOB_TOKEN` | unset | unset (optional; see step 3) |
| `DEADLINE_JOB_INTERVAL_SECONDS`, `CONTACT_PURGE_INTERVAL_SECONDS` | `120`, `3600` | unchanged |
| `MISSED_MESSAGE_SWEEP_INTERVAL_SECONDS` | `900` | unchanged: how often the API sends a "received" message that never reached the outbox (at most 20 a run, nothing older than 7 days) |

`PUBLIC_API_URL` must be exactly the address Twilio and Arkesel call: the API
checks Twilio's signature against it, and asks for delivery reports at it.
`PUBLIC_SITE_URL` is the address residents' messages link to; messages write
it without `https://` where one SMS page is tight.

**First start.** The startup log must contain, in this order:

1. `The Ledger's search index is reachable: nokware_rag at <postgres-host>:5432.`
   If it says instead that something else answers on the port, or that nothing
   does, `POSTGRES_URL` or the network path is wrong: Ask and the Ledger search
   answer 503 until it's fixed (reports, the portal and petitions still work).
2. `Deadline job runs every 120s`, `Petition clock runs every 120s`,
   `Contact purge runs every 3600s`, `BMS delivery check runs every 120s`.
3. `Application startup complete.`

Then `curl https://api.nokware.tstitagency.com/health` answers
`{"status": "ok"}`.

The MCP server (report figures for AI clients) is part of the API at
`https://api.nokware.tstitagency.com/mcp`: nothing to add in Coolify. It
accepts only the host in `PUBLIC_API_URL` (and localhost), so a wrong value
there shows as `421 Misdirected Request` on `/mcp`. Check it answers:

```bash
curl -s -X POST https://api.nokware.tstitagency.com/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The reply lists `count_reports` and `personal_safety_figures`.

## 6. Coolify: the site and portal

New resource → **Application** → the same repository and branch.

| Setting | Value |
|---|---|
| Build pack | Dockerfile |
| Base directory | `/frontend` |
| Dockerfile location | `/frontend/Dockerfile` |
| Port exposed | `3000` |
| Domains | `https://nokware.tstitagency.com` |

**Build arguments** (in Coolify, mark each as a build variable: Next bakes them
into the browser bundle, so changing one needs a rebuild, not a restart):

| Variable | Development | Production |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `https://api.nokware.tstitagency.com` |
| `NEXT_PUBLIC_APPWRITE_ENDPOINT` | `https://appwrite.tstitagency.com/v1` | unchanged |
| `NEXT_PUBLIC_APPWRITE_PROJECT_ID` | the project's ID | unchanged |

The site has no server-side secrets.

## 7. Twilio (WhatsApp)

Twilio console → **Messaging → Try it out → Send a WhatsApp message → Sandbox
settings**:

| Field | Value |
|---|---|
| When a message comes in | `https://api.nokware.tstitagency.com/api/channels/whatsapp`, method **POST** |
| Status callback URL | leave empty: the API asks for status callbacks on each message it sends, at `PUBLIC_API_URL` |

Once this points at the VPS, the development API no longer receives WhatsApp
messages; test locally with `backend/scripts/whatsapp_simulator.py`.

The sandbox reaches only phones that have joined it (by sending its join
code). A public launch needs an approved WhatsApp sender (a WhatsApp Business
profile through Twilio); when it is approved, set `TWILIO_WHATSAPP_FROM` to its
number and set the same "when a message comes in" address on that sender.

## 8. Arkesel (SMS and USSD)

- **USSD**: in Arkesel's dashboard, the USSD service's callback URL becomes
  `https://api.nokware.tstitagency.com/api/channels/ussd/<new ARKESEL_USSD_TOKEN>`.
  Update Coolify and Arkesel together: between the two, dials fail. The token
  never appears in the API's access logs (it is redacted).
- **SMS delivery reports**: the API asks for them on each message at
  `https://api.nokware.tstitagency.com/api/channels/sms/delivery` and verifies
  them with `ARKESEL_WEBHOOK_SECRET`. If the dashboard also keeps a webhook
  address, set it to that; the secret is unchanged.
- **Sender ID**: registration is in progress. It matters for USSD answers and
  for SMS if the API ever goes back to Arkesel; with `SMS_PROVIDER=bms`, SMS
  already goes as the approved "Nokware" on BMS.
- **BMS** needs nothing configured on its side: no webhook exists, and the API
  polls for delivery. The startup log says `BMS delivery check runs every
  120s`. `scripts/sms_balance.py` shows the credit left (it sends nothing).

## 9. Order of operations

1. Settle the open *Decisions* (the fourth, live SMS, is settled).
2. Add the DNS records; wait until both names resolve to the VPS.
3. Add the Appwrite web platform.
4. Generate `PHONE_KEY_SECRET` and the new `ARKESEL_USSD_TOKEN`; store both.
5. Create the API in Coolify with every variable above; deploy. Check the
   startup log (search index reachable, four jobs running, the fourth being the BMS
   delivery check) and `/health`.
6. Create the site in Coolify with its build arguments; deploy. Check:
   - the home page, Ask (a question that cites documents), and a document's PDF;
   - filing a report, and its status page (with BMS the SMS is real and
     charged: file with your own number, once, and check the outbox row
     reaches `deliveryStatus` DELIVERED within a few minutes);
   - staff sign-in (a department and the MCE), and the portal queues;
   - the petitions pages, and the accountability pages.
7. Switch Twilio's sandbox webhook (step 7) and Arkesel's USSD callback with
   the new token (step 8), Coolify's token first.
8. Test each channel once with the simulators pointed at the API
   (`--url https://api.nokware.tstitagency.com`): one WhatsApp question, one
   USSD session. With the sandbox and simulators nothing is charged. A real
   WhatsApp message to the sandbox number costs one inbound and one reply:
   only with a yes, per message.
9. Watch the logs for the first 72-hour, 90-day and 30-day clock runs and the
   hourly purge.

## Rolling back

Point Twilio's webhook and Arkesel's USSD callback back at the development
address (an ngrok tunnel to a local API with the old token), and stop the two
Coolify applications. The data is untouched either way: Appwrite, MinIO and
Postgres are the same stores in both.

## Afterwards

- Keep `backend/.env` for local development: `localhost` addresses, the
  tunnel for Postgres if the local API needs the Ledger search, and
  `ARKESEL_SANDBOX=true`.
- Schema scripts (`backend/scripts/create_*.py`) are safe to re-run; run them
  inside the API container (`python scripts/create_petitions.py --yes`) or from
  a machine with the production variables.
- Test data carries a `[TEST]` prefix and is removed with
  `scripts/delete_test_documents.py`, `delete_test_reports.py` and
  `delete_test_petitions.py` (dry runs by default; `--yes` deletes).
