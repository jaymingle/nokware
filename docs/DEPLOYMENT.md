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
2. **How Postgres and Redis run on the VPS: settled.** Both are Coolify-managed
   resources, and the API joins their Docker network and uses their internal
   hostnames. Postgres is `tstitagency-postgres` (Coolify resource
   `zim2p58t3nnkrjn0rrtirh3y`) on port 5432 — the same server the development
   tunnel on :5434 reaches, so the same database, user and password. Redis is
   `nokware-redis` on port 6379.
3. **Redis database number: settled, `/1`.** Development uses `/0` on the local
   `nokware-redis` container; production uses `/1`. Nokware's keys all start
   `nokware:` and every one of them expires.
4. **SMS on the first deploy: `SMS_PROVIDER=log`.** Nothing is sent and nothing
   is charged while the deployment itself is being checked. BMS is live and has
   no sandbox, so switching it on is a deliberate second step, taken once the
   site, the portal and the channels are known to work. See *Turning SMS on*
   below for what changes with it, and what is affected while it is off.

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
  (72-hour clocks), the petition clock (90-day close, 30-day
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
- **The first deploy sends no SMS (`SMS_PROVIDER=log`).** Every message the API
  would send is written to the log instead, and nothing is charged. BMS has no
  sandbox, so this is the only way to check a deployment without paying for it.
  What is affected while SMS is off: a resident who files a report by web or
  USSD gets no "received" text, an Ask answer can't be sent by SMS (it is still
  read on the USSD screen, free), and **confirming a number by SMS is not
  offered at all** — the API hides that choice when no provider would deliver
  the code, leaving WhatsApp and USSD, which both work. `SMS_VERIFICATION_CODES`
  can be left `true`: it takes effect when a real provider is configured.
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

- **Postgres**: the same database the development tunnel on :5434 reached
  (`nokware_rag`, user `nokware_user`, pgvector, table `document_chunks`, 7,537
  chunks over 154 documents). No data moves; only the address changes, from
  `localhost:5434` to `tstitagency-postgres:5432`. The API's container must join
  that resource's network (see *6a*).
- **Redis**: `nokware-redis:6379`, database `/1` in production and `/0` in
  development, so a local API and the deployed one never share a key. It holds
  only short-lived state (USSD menus, WhatsApp drafts, phone-confirmation codes,
  per-number limits, the day's SMS count, read-aloud audio for six hours); every
  key expires, and none of it is worth backing up.

## 5. Coolify: the API

New resource → **Application** → from the GitHub repository
`jaymingle/nokware`, branch **`petitions-rework`** (connect Coolify's GitHub
App, or a deploy key, since the repository is private). That is the branch this
deploy is cut from; it has not been merged to `main`.

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
| `POSTGRES_URL` | `postgresql+psycopg://nokware_user:…@localhost:5434/nokware_rag` (tunnel) | `postgresql+psycopg://nokware_user:…@tstitagency-postgres:5432/nokware_rag` — same database, user and password as development, reached by the internal hostname instead of the tunnel |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | `s3.tstitagency.com`, secrets | unchanged |
| `MINIO_LEDGER_BUCKET`, `MINIO_PHOTOS_BUCKET` | `nokware-ledger-files`, `nokware-report-photos` | unchanged |
| `GEMINI_API_KEY` | secret | unchanged |
| `CORS_ORIGINS` | empty | `https://nokware.tstitagency.com` |
| `CORS_ORIGIN_REGEX` | unset (default admits localhost on any port) | set to **empty**, so only the site above is admitted |
| `PUBLIC_API_URL` | the ngrok address | `https://api.nokware.tstitagency.com` |
| `PUBLIC_SITE_URL` | `http://localhost:3000` | `https://nokware.tstitagency.com` — **required**, no default: the API refuses to start without it rather than text residents a localhost link |
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://nokware-redis:6379/1` (add `:<password>@` before the host if the resource has one) |
| `SMS_PROVIDER` | `arkesel` | **`log`** for the first deploy: nothing sent, nothing charged. `bms` when SMS is turned on (see *Turning SMS on*) |
| `WHATSAPP_PROVIDER` | `twilio` | unchanged |
| `ARKESEL_API_KEY`, `ARKESEL_SENDER_ID`, `ARKESEL_WEBHOOK_SECRET` | secrets | unchanged |
| `ARKESEL_SANDBOX` | `true` | `true` (see *Constraints*) |
| `BMS_API_KEY`, `BMS_SENDER_ID` | secret, `Nokware` | the same (the sender ID is approved on BMS) |
| `BMS_DELIVERY_POLL_SECONDS` | `120` | `120`: BMS sends no delivery reports, so the API asks it |
| `SMS_DAILY_LIMIT` | `50` | **everyone's pages combined, not per number.** At 50, four residents using Ask by SMS (3 pages each, five answers) would spend the whole day's budget and report notifications would then be refused. Raise it, or keep `SMS_ANSWER_DAILY_LIMIT` low, before SMS goes live |
| `SMS_ANSWER_DAILY_LIMIT` | `5` | **`50`** while testing; **`5`** once SMS is live. Ask answers one number may have texted to it in a day, counted only when a real provider takes them. Each answer is up to 3 pages, and `SMS_DAILY_LIMIT` below is the whole service's daily page budget, so 50 is safe only while nothing is sent |
| `ARKESEL_USSD_TOKEN` | the development token | **the new, rotated token from step 3** |
| `USSD_SERVICE_CODE` | empty | empty until Arkesel confirms the dial code (e.g. `*920*123#`); then petition pages offer USSD |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | secrets | unchanged |
| `TWILIO_WHATSAPP_FROM` | `whatsapp:+14155238886` (the sandbox) | unchanged until an approved WhatsApp sender replaces it |
| `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE`, `VOICE_DAILY_LIMIT` | `gemini-3.1-flash-tts-preview`, `Charon`, `20` | unchanged (leave `GEMINI_TTS_MODEL` unset or set it to the 3.1 model: 2.5 stalls on read-aloud's longer text) |
| `READ_ALOUD_DAILY_LIMIT` | `300` | unchanged: fresh read-aloud parts (about 25 seconds each) made in a day across everyone (repeats come from a six-hour cache) |
| `PETITION_THRESHOLD_AREA`, `PETITION_THRESHOLD_METRO` | `150`, `500` | unchanged |
| `SMS_VERIFICATION_CODES`, `SMS_CODE_DAILY_LIMIT` | `false`, `30` | **`true`**, `30`. With `SMS_PROVIDER=log` this has no effect and the site doesn't offer SMS confirmation; it starts working the moment BMS is set |
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
   `Contact purge runs every 3600s`, `Missed-message sweep runs every 900s`.
   With `SMS_PROVIDER=log` the fifth line is `BMS delivery check is disabled`;
   it becomes `BMS delivery check runs every 120s` when BMS is set.
3. `SMS: log, up to 50 pages a day (30 for codes); WhatsApp: twilio` — check
   the provider named here is the one intended before anything is sent.
4. No `CORS_ORIGIN_REGEX still allows localhost` warning. If it appears,
   `CORS_ORIGIN_REGEX` was not set to empty and any localhost page can call
   the API.
5. `Application startup complete.`

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

**Build arguments — all three are build-time, not runtime.** In Coolify, tick
*Build Variable* on each. Next bakes a `NEXT_PUBLIC_*` value into the browser
bundle when the image is built, so changing one needs a **rebuild**; a restart
does nothing, and setting them as ordinary runtime variables leaves the browser
calling `http://localhost:8000`.

| Variable | Development | Production |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `https://api.nokware.tstitagency.com` |
| `NEXT_PUBLIC_APPWRITE_ENDPOINT` | `https://appwrite.tstitagency.com/v1` | unchanged |
| `NEXT_PUBLIC_APPWRITE_PROJECT_ID` | `APPWRITE_PROJECT_ID` in `backend/.env` | the same value |

The site has no server-side secrets, and the frontend branch is
`petitions-rework` too.

## 6a. Coolify: networks, health checks and the proxy

**Networks.** Both applications must join the Docker networks of the resources
they use, or the hostnames in `POSTGRES_URL` and `REDIS_URL` don't resolve and
the API starts but answers 503 on Ask:

| Application | Networks to join | Why |
|---|---|---|
| API | the network of `tstitagency-postgres` (`zim2p58t3nnkrjn0rrtirh3y`) and of `nokware-redis` | `POSTGRES_URL` and `REDIS_URL` use their internal hostnames |
| Site and portal | none beyond Coolify's default | it reaches the API over the public address |

In Coolify this is *Connect to Predefined Network* on the application, or the
`networks:` list if the resource is defined by compose. A quick check from
inside the running API container:

    docker exec -it <api-container> python -c "import socket; print(socket.gethostbyname('tstitagency-postgres'), socket.gethostbyname('nokware-redis'))"

**Health checks.** Both are already in the Dockerfiles; Coolify picks them up.

| Service | Path | Healthy response |
|---|---|---|
| API | `GET /health` | `{"status": "ok"}` |
| Site and portal | `GET /` | `200` |

The API's check runs inside the container against `127.0.0.1:8000`, so it keeps
passing even while DNS or the proxy is still settling. Give the API a start
period of at least 45 seconds: it checks the search index before it serves.

**The Traefik empty-`Host()` bug.** If an application's domain is left blank, or
saved with the scheme missing, Coolify generates a router rule of `Host()` with
nothing in it. Traefik then matches **every** request to that container, so
whichever service deployed last answers for both addresses — the symptom is the
API's JSON appearing at `nokware.tstitagency.com`, or the site appearing at the
API's address, with valid certificates for both. To spot it:

    docker inspect <container> --format '{{json .Config.Labels}}' | tr ',' '\n' | grep -i 'rule'

Every rule must read `Host(\`nokware.tstitagency.com\`)` or
`Host(\`api.nokware.tstitagency.com\`)`. `Host()` — empty parentheses — or a
rule mentioning a domain that isn't one of these two means the domain field is
wrong. Fix it by setting the full address including `https://` in the
application's *Domains* field and redeploying; editing the label by hand is
undone by the next deploy.

**Storage.** Neither service needs a Coolify volume. Everything durable lives
outside them: documents and photos in MinIO (`s3.tstitagency.com`), records in
Appwrite, the search index in Postgres, and short-lived state in Redis. The
containers are disposable, and a redeploy loses nothing. The read-aloud audio
cache lives in Redis with a six-hour expiry, so it warms again by itself.

## 6b. Turning SMS on

The first deploy runs with `SMS_PROVIDER=log`. When the site, portal and
channels are known to work, switch SMS on in one step:

1. Set `SMS_PROVIDER=bms` in Coolify.
2. Set `SMS_ANSWER_DAILY_LIMIT=5` (it was `50` for testing, which is only safe
   while nothing is sent).
3. Decide `SMS_DAILY_LIMIT`. It is the whole service's page budget for a day,
   everyone combined — not per number. At `50`, four residents using Ask by SMS
   could spend all of it and report notifications would then be refused.
4. Restart the API. Settings are read once at startup, so a change needs a
   restart, not just a save.

The startup log then says `SMS: bms, up to <n> pages a day (30 for codes)` and
`BMS delivery check runs every 120s`. From that moment every report
notification, petition update, Ask answer sent by SMS and verification code is
delivered and charged. `backend/scripts/sms_balance.py` shows the credit left
and sends nothing.

Confirming a number by SMS starts being offered at the same moment: the API
hides that choice while no provider would deliver the code, so nothing needs to
be switched on separately.

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
  for SMS if the API ever goes back to Arkesel; once `SMS_PROVIDER=bms`, SMS
  goes as the approved "Nokware" on BMS.
- **BMS** needs nothing configured on its side: no webhook exists, and the API
  polls for delivery. While `SMS_PROVIDER=log` the startup log says `BMS
  delivery check is disabled`; after the switch it says `BMS delivery check runs
  every 120s`. `scripts/sms_balance.py` shows the credit left (it sends
  nothing).

## 9. Order of operations

1. Settle the open *Decisions* (the fourth, live SMS, is settled).
2. Add the DNS records; wait until both names resolve to the VPS.
3. Add the Appwrite web platform.
4. Generate `PHONE_KEY_SECRET` and the new `ARKESEL_USSD_TOKEN`; store both.
5. Create the API in Coolify with every variable above; deploy. Check the
   startup log (search index reachable, the four jobs running, BMS disabled,
   no CORS warning) and `/health`.
6. Create the site in Coolify with its build arguments; deploy. Check:
   - the home page, Ask (a question that cites documents), and a document's PDF;
   - filing a report, and its status page (with `SMS_PROVIDER=log` no text is
     sent: the outbox row is written and the message body appears in the API
     log, which is what to check);
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
