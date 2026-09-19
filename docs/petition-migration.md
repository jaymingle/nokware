# Moving petitions to the new process

The MCE no longer decides whether a petition exists. A petition publishes when its
creator publishes it, and a verified contributor can remove it on fixed grounds.
This records what was in the database before that change, how each record maps,
and what the migration actually did.

Nothing is deleted: the old status is kept on every record in `legacyStatus`.

## What was there, before anything ran

Read from the live database on 19 September 2026, before the migration.

| Code | Status | Signatures | Title |
| --- | --- | --- | --- |
| 504162 | `in_review` | 0 | The Assembly has not posted it's financials |

One petition. It was waiting for the MCE's review under the old process, so it
goes through the draft-time screen again and, if it passes, becomes `open` — a
petition nobody has to approve.

## The mapping

| Old status | New status | Note |
| --- | --- | --- |
| `in_review` | `open`, or `closed` if it fails the screen | Closed carries "Closed during the move to the new petition process: &lt;reason&gt;" |
| `open` | `open` | |
| `awaiting_response` | `awaiting_response` | The response clock keeps running |
| `responded` | `responded` | |
| `refused` | `closed` | Labelled publicly "Refused under the earlier review process", never as a contributor's removal, which would be untrue |
| `withdrawn`, `closed` | `closed` | |

Existing signatures become signatures on version 1.

A record that fits none of these is left exactly as it is and listed below.

## Dry run

`backend/.venv/bin/python backend/scripts/migrate_petitions.py`, 19 September 2026:

```
[dry run] 504162: in_review -> open, legacyStatus=in_review

1 petition(s) read, 1 to move, 0 untouched
```

## What ran

The schema first — `backend/scripts/create_petitions.py --yes` — which added the
version, removal and report collections, the `legacyStatus` field and the new
status values, leaving every existing attribute and index alone. Then:

`backend/.venv/bin/python backend/scripts/migrate_petitions.py --yes`

```
504162: in_review -> open, legacyStatus=in_review

1 petition(s) read, 1 moved, 0 untouched
```

Read back from the database afterwards:

| Code | Status | legacyStatus | Version | Signatures |
| --- | --- | --- | --- | --- |
| 504162 | `open` | `in_review` | 1 | 0 |

The one petition waiting for the MCE passed the draft-time screen and is now
public, as a petition nobody has to approve. Nothing was deleted, and nothing was
left untouched for want of a mapping.

The status and action enums still list the values the old process used
(`in_review`, `refused`, `withdrawn`), so a record written before this change
still fits its column, and the `cleanup` branch — which knows nothing of versions
or removals — keeps reading these rows.
