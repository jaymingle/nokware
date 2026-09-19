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

## Roadmap

### Petitions, reworked

Petitions today wait for the MCE to publish or refuse them. The agreed design
removes that gate and gives the referee's part to a verified contributor, who is
not Assembly staff and has no stake in the outcome — an institution that can
remove petitions against itself taints every removal, however honest the reason.

- **A petition publishes when its creator publishes it.** No approval gate.
- **A verified contributor can remove a published petition**, only on fixed
  grounds: it names a private individual, incites violence, contains personal
  data, or duplicates an open petition — and a duplicate must cite the other
  petition's code, shown and linked. "Not the Assembly's responsibility" is a
  judgement on merit: it belongs in the MCE's response, never in a removal.
- **The reason is public**, on the page where the petition was, as "Removed by a
  verified contributor". The identity stays in the audit trail: naming the person
  exposes them to whoever wanted the petition up.
- **The tombstone shows the reason and the date, and nothing else** — not the
  text, not the title, since a title can name someone just as easily.
- **Removals are counted publicly by reason**, as document disputes are, so a
  contributor removing too freely becomes visible. Repeat removals of the same
  petition are counted, not capped: "removed twice for naming a private
  individual" is itself information.
- **The petitioner can edit and republish.** Signatures carry over, with the page
  saying "signed before the edit of 19 September" and the edit history shown.
- **Any reader can report a petition** on the same grounds. Removal power nobody
  can trigger is not a remedy.
- **The MCE responds, or shares a petition with a department**, and sees the
  petitioner's reply. No power over whether a petition exists.
- Each petition on its own page, with comments (named or anonymous), images, and
  a creator who can find and edit their petitions with the code they were given.

### Language switchers

On WhatsApp (following the language someone writes in), on the site, and on USSD
before the menu. See the Languages section above for what each costs and why Twi
and Arabic wait.

### A fixed vocabulary for resolution notes

Staff notes on a case are free text today, screened but unconstrained. A short
fixed vocabulary ("cleared", "repaired", "referred to a contractor", "not the
Assembly's to act on") offered alongside the free text would make resolutions
comparable across departments without flattening what staff can say.

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
