# Nokware

Nokware is a civic-transparency platform for the Accra Metropolitan Assembly. It
pairs a public **Ledger** — searchable department documents answered by a
Retrieval-Augmented Generation (RAG) assistant that cites its sources — with a
**citizen reporting** system for civic-service, public-safety, and
personal-safety cases routed to the responsible department. Residents reach it
on the web, WhatsApp, USSD and SMS. Data lives across
Appwrite (auth, teams, document metadata, reports, case history), a
Postgres/pgvector store (RAG chunks and embeddings), and MinIO (document and
photo files).

This repository is a monorepo with two applications:

- [`backend/`](backend/README.md) — Python 3.11 · FastAPI · LangChain · Gemini ·
  Appwrite SDK · MinIO · pgvector.
- [`frontend/`](frontend/README.md) — Next.js 16 (App Router, TypeScript,
  Tailwind) with shadcn/ui.

Deployment is described in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Languages

**Today.** Nokware's screens and channel messages are in English. Ask on the web
answers in the language it was asked in: the question is read into English, the
answer is written and checked in English, then translated back, and it falls back
to the English if a figure or a citation doesn't survive the translation. The fixed
text around an answer comes from a hand-written catalogue
(`backend/app/data/phrases/`), and text someone may act on while in danger stays
in English in every language until a named person has reviewed the translation.
See [Languages, and the rule for text someone acts on](backend/README.md#languages-and-the-rule-for-text-someone-acts-on).

**Roadmap.** The catalogue exists so that adding a language is a file, not a
rebuild. What is left, and why it isn't in this release:

- **A language switcher on the site.** The site's text is written in its
  components, not yet in the catalogue; moving roughly a thousand strings is the
  bulk of the work.
- **Languages on WhatsApp.** Following the language a person writes in and
  remembering it for their number. Ask's answers already come back in that
  language on the web; the fixed WhatsApp replies would move into the catalogue.
- **A language screen on USSD, and SMS updates in the report's language.**
  English and French first, with every French screen kept within 160 characters
  and the characters feature phones can't show (ê, â, ô, î, û, ç, ë, ï, œ) written
  as their plain forms.
- **Twi, once a speaker has written it.** Nobody has written the Twi catalogue,
  and Nokware won't draft it: machine Twi drops ɛ and ɔ, mixes dialects and can
  lose a negative. A Twi option that opens English screens is worse than no
  option, so none is offered.
- **Arabic, on the site and WhatsApp only.** Arabic can't go on USSD or SMS. One
  Arabic character switches a message to UCS-2, which roughly halves the room on
  a screen (70 characters an SMS instead of 160). Many feature phones have no
  Arabic font. And the invisible direction marks that keep a phone number,
  reference or amount in left-to-right order inside Arabic text are exactly what
  old handsets show as boxes. A reordered emergency number is dangerous.

## Petitions

A petition is public the moment its creator publishes it. Nobody in the Assembly
approves it first — the office a petition is usually about cannot decide whether
it exists.

A **verified contributor** is the referee instead: not Assembly staff, no stake in
the outcome. A contributor may remove a petition only on four fixed grounds — it
names or attacks a private individual, incites violence, carries personal data, or
duplicates an open petition, which must cite the other petition's number. Never
their own petition, and never one they signed. "Not the Assembly's
responsibility" is a judgement on the merits and belongs in the MCE's response,
not in a removal.

A removal is public and anonymous: the ground in plain words, the date, and
"Removed by a verified contributor". The identity stays in the audit trail,
because naming the person exposes them to whoever wanted the petition up. What
replaces the petition is built from the removal record rather than by hiding the
petition's fields, so it cannot leak the title, the text, the images, the
comments, the signature count or the MCE's response.

Any reader can **report** a petition on the same grounds. A report hides nothing:
it joins the contributor's queue. Removals are counted publicly by ground, so a
contributor removing too freely becomes visible.

The creator can **edit and republish** at any time, including after a removal.
Each edit is a version: the history is public, signatures carry over, each
remembering the version it was given on, and the removal count is shown.

The **MCE responds** to a petition that reaches its threshold, within 30 days, or
shares it with a department, which can add one note shown publicly under its name.
The petitioner can reply to the response. Signatures, thresholds and the response
clock are unchanged.

Comments are open to anyone who can sign, under a display name and never a phone
number, screened like everything else and removable one at a time without taking
the petition down.

## Roadmap

### Voice notes on a petition

A petition can be written but not spoken. The voice path exists for reports and
for Ask; petitions would need the same transcription, the same confirmation of
what was heard, and the same rule that a machine transcription is labelled.

### Restoring a removal without republishing

A contributor who removes a petition in error can only wait for its creator to
edit and republish it. Undoing a removal, with the undo itself public, is the
missing half of that power.

### Language switchers

On WhatsApp (following the language someone writes in), on the site, and on USSD
before the menu. See the Languages section above for what each costs and why Twi
and Arabic wait.

### Department-initiated escalation

Escalation today is the resident's to make, once, within 14 days of a resolution.
A department cannot send a case upward — if it needs the MCE, the only route is to
resolve it and wait for the resident to disagree. Building it means a new action on
a documented state machine (`escalated` currently freezes every recipient action),
its own history entry and message, and a rule for who may do it and when.

### A fixed vocabulary for resolution notes

Staff notes on a case are free text today, screened but unconstrained. A short
fixed vocabulary ("cleared", "repaired", "referred to a contractor", "not the
Assembly's to act on") offered alongside the free text would make resolutions
comparable across departments without flattening what staff can say.

## Known limitations

Things that work, with their edges named:

- **Reading an answer aloud starts after about 7 seconds.** Almost all of it is
  the speech model: it takes roughly 0.7 seconds for every second of audio it
  makes, and the first chunk can't be shorter than a sentence without sounding
  cut. Hovering Listen starts the audio early, so a press usually plays at once,
  but a cold press waits. Streaming synthesis would fix it properly.
- **A message a resident is owed is repaired, with two gaps left.** Repairs are
  per channel, so someone who agreed to both SMS and WhatsApp and was failed on
  one is sent on that one alone. A row stuck at "queued" after a crash can be
  settled but never *learned about*: the process died before the provider's
  message id existed, so no delivery report can say what happened. And messages
  recorded while `SMS_PROVIDER=log` are never backfilled when a real provider is
  configured.
- **Escalation photos are web only.** A resident escalating by USSD or WhatsApp
  can write, but not attach; the browser is where the shrinking and EXIF-stripping
  happen.
- **Comments are web only.** USSD and WhatsApp show how many there are and point
  at the page; writing one needs a browser.
- **Moderation depends on contributors being active.** Nothing hides a petition
  automatically: if no contributor reads the queue, a reported petition stays up.
  That is the trade for an institution not deciding what may be said about it.
- **Verification codes by SMS are off by default** (`SMS_VERIFICATION_CODES`),
  pending a live sender ID, so a phone is confirmed over WhatsApp or USSD.
- **No screen-reader test with a real user**, and the report form's photo field
  has a duplicate tab stop (see [`frontend/README.md`](frontend/README.md)).

## Future work: structure

The code was cleaned up before submission without restructuring it. These are
the improvements that would mean moving responsibilities between modules, left
for after the deadline:

- **Shared SMS plumbing.** `services/sms_bms.py` imports private helpers from
  `services/sms.py`; they belong in a public module both providers use.
  `services/petition_updates.py` also repeats the send-log-report delivery step of
  `services/notifications.py`.
- **One cache.** `report_dashboard._Cache` is imported privately by
  `publishing_record` and `department_responsiveness`, and `stats` has its own.
- **Answer types defined once.** `services/rag.py` builds its answers as
  TypedDicts that `schemas/ask.py` defines again as models.
- **Schema scripts.** `scripts/create_citizen_reports.py` is both a runnable
  script and the helper library the other schema scripts import; its
  `ensure`/wait-for-attributes/index helpers are also rewritten in
  `create_document_history.py` and `add_document_origin.py`.
- **Small shared helpers repeated in the backend:** Redis daily counters
  (`read_aloud`, `whatsapp_voice`, `sms`), deriving keys from the Appwrite secret
  (`redis_store`, `phone_proof`, `ask_export` — the purpose strings must stay
  byte-identical or existing keys stop working), GH¢ amount parsing in four
  places, and three sets of Markdown-stripping patterns.
- **Contact wording in one place.** `contacts.short_line` and
  `channel_contacts` label the same numbers differently ("Helpline" and "Helpline
  of Hope"); one label map should serve both, checked against every USSD screen's
  160-character limit.
- **`services/report_followups.py`** handles a resident's actions on a case and
  the scheduled purge of contact numbers; those are two jobs.
- **The frontend repeats rules the API owns:** petition durations (72 hours, 30
  and 90 days) and form limits are written into components, though the API returns
  or enforces them; the emergency numbers on the report and emergency pages are
  written in rather than read from the contacts API.
- **Frontend dialogs.** Seven dialogs rewrite the same open/reset/error/cancel
  handling that `cases/case-dialog.tsx` already has as a hook.
- **`frontend/src/lib/petitions.ts`** holds both petition wording and browser
  storage for phone proofs and drafts; `lib/report/dashboard.ts` mixes date
  formatting with the "fewer than 5" rules.
