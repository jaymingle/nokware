# The reset before the first deploy

What was in the stores on 2026-09-20, what the reset deletes, and what it leaves. Counts were taken twice: once
when the backup was written (`backups/20260920-015508/`) and again by the reset's dry run. They matched exactly,
which is the check that the backup covers everything the reset removes.

Run it with `backend/scripts/reset_before_deploy.py` — a dry run by default, `--yes` to delete.

## Appwrite collections

| Collection | Rows | | Why |
|---|---:|---|---|
| `citizen_reports` | 5 | **Delete** | every report residents filed, [TEST] or not |
| `case_assignments` | 7 | **Delete** | which department each case went to |
| `case_history` | 45 | **Delete** | the audit trail of those cases |
| `case_voices` | 0 | **Delete** | residents adding their voice to a case |
| `report_contacts` | 5 | **Delete** | residents' phone numbers, names and shared locations |
| `notifications` | 22 | **Delete** | the outbox and its delivery records |
| `petitions` | 2 | **Delete** | includes petition 504162 |
| `petition_signatures` | 1 | **Delete** | |
| `petition_versions` | 2 | **Delete** | each version keeps the image names it had |
| `petition_history` | 3 | **Delete** | |
| `petition_reports` | 1 | **Delete** | |
| `petition_comments` | 1 | **Delete** | |
| `petition_comment_reports` | 0 | **Delete** | |
| `petition_removals` | 0 | **Delete** | |
| `petition_shares` | 0 | **Delete** | petitions shared with departments, and their notes |
| `ledger_documents` | 164 | Keep | the Ledger itself |
| `document_history` | 0 | Keep | document disputes; none exist, so none are [TEST] |

94 rows go, 164 stay. No collection, attribute or index is created, altered or dropped.

## Object storage

| Bucket | Prefix | Objects | | |
|---|---|---:|---|---|
| `nokware-report-photos` | `reports/` | 6 | 544.2 KiB | **Delete** |
| `nokware-report-photos` | `petitions/` | 8 | 263.5 KiB | **Delete** |
| `nokware-report-photos` | anything else | 0 | — | Keep: never touched |
| `nokware-ledger-files` | all | 164 | 436.0 MiB | Keep: the Ledger's own files |

The script lists objects **by those two prefixes only**. It never enumerates the bucket as a whole, so an object
outside them cannot be reached even by mistake, and the ledger bucket is never opened for writing.

## Postgres (the Ledger's search index)

| Table | Rows | | |
|---|---:|---|---|
| `document_chunks` | 7,537 | Keep | chunks, embeddings (`vector`), and the full-text column, over 154 documents |

It is the only table in the database. **The reset never connects to Postgres.** Backed up all the same, because a
reset that goes wrong shouldn't leave the Ledger as the thing nobody has a copy of.

## Redis

| Prefix | Keys in db0 | | |
|---|---:|---|---|
| `nokware:limit:*` | 172 | Keep | per-number rate limits and the day's SMS counts |
| `nokware:wa-seen:*` | 14 | Keep | WhatsApp messages already handled |
| `nokware:speech:*` | 9 | Keep | read-aloud audio, six-hour expiry |
| `nokware:sms:*` | 4 | Keep | the day's SMS page budget |
| `nokware:wa-window:*` | 3 | Keep | WhatsApp 24-hour session windows |
| db1 | 0 | **Delete** | empty: nothing to delete |

**The reset deletes nothing from Redis, and this is deliberate.** The instruction was "Redis db 1 only", and db1
holds no keys. Two things are worth knowing:

- Development actually uses **db0**, not db1 (`REDIS_URL=redis://localhost:6379/0`). Production uses
  `redis://nokware-redis:6379/1`, which is the empty one, so the deploy starts with no Redis state either way.
- db0 is protected by a standing rule. On this machine it holds **only** `nokware:*` keys — there is one Redis
  container, `nokware-redis`, with no other database in use and nothing named `backup1`–`backup4` anywhere in it.
  Whatever that rule was written for is not here. Nothing was deleted on the strength of that observation.

Every one of the 202 keys carries a TTL, so they clear themselves within hours. None of them is a record.

## Things on the Delete list with no collection of their own

Each was traced to where it actually lives before anything was deleted.

| Named | Where it really lives | What the reset does |
|---|---|---|
| Escalations | fields on a `citizen_reports` row (`escalatedAt`, `escalationNote`) plus `escalated` entries in `case_history` | goes with the case |
| Location shares and views | fields on a `report_contacts` row (`exactLocation`, `exactLocationAt`); views are `case_history` entries | goes with the contact record |
| Petition department notes | a field on a `petition_shares` row | goes with the share |
| Petition replies (the MCE's response) | fields on the `petitions` row itself | goes with the petition |
| Phone proofs | Redis, `nokware:phone:challenge:*`, encrypted and short-lived | nothing: they expire |
| Verification codes | Redis, inside the same phone-challenge key | nothing: they expire |
| Preference tokens | fields on a `report_contacts` row (`preferencesTokenHash`, `preferencesExpiresAt`) | goes with the contact record |
| TTS / audio cache | Redis `nokware:speech:*` (six hours) and `nokware:wa-audio:*`; **there is no persistent one** | nothing: no durable cache exists |

None of these lives as a field inside a record that is being kept, so nothing had to be cleared in place.

## What is kept, and was checked afterwards

The Ledger (documents, files, chunks, embeddings, the search index), budget rows — which are
`backend/app/data/budget_lines.json` in git, not a database, so no reset can reach them — publishing-record data,
contacts, teams, departments, taxonomy, phrases, statutory-document rules, every Appwrite user and team membership,
and every schema.
