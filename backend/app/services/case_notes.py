"""A staff note on a stage of a case, written for the resident who filed it.

Every stage takes a note: starting work, moving the case, resolving it, reopening it, and the MCE's answer to an
escalation. Moving and resolving require one — a resident must never be told "moved" or "resolved" with no reason.

A note goes through the same draft-time screen a petition's words do, for the same reason: a phone number, an email
address or a Ghana Card number does not belong on a page anyone holding a reference can open. It is refused with the
reason, never quietly stripped, so the person writing it knows what was wrong and decides how to say it instead.
"""

from app.services.petition_screen import personal_data, private_person
from app.services.workflow import MissingInput, WorkflowError

NOTE_MAX = 500


class NoteRefused(WorkflowError):
    """The note can't be saved as written. The message says exactly why."""

    status_code = 422


def clean_note(note: str | None, *, required: bool, ask: str = "") -> str | None:
    """The note as it will be stored, or None if none was given and none is needed.

    The cheap checks run before the case is so much as read, so a note that can't be saved costs nothing. Whether
    it names a private person is asked afterwards, by not_naming_anyone(), because the answer depends on the case.
    """
    text = (note or "").strip()
    if not text:
        if required:
            raise MissingInput(ask)
        return None
    if len(text) > NOTE_MAX:
        raise NoteRefused(f"Keep the note to {NOTE_MAX} characters; this one is {len(text)}.")
    found = personal_data(text)
    if found:
        raise NoteRefused(
            f"This note contains {found}. The resident reads this note on their status page, so take it out and "
            "say it another way."
        )
    return text


def not_naming_anyone(note: str | None, *, read_by_the_resident: bool) -> None:
    """A note the resident will read can't name a private person: their status page is opened by whoever holds the
    reference, which on a shared phone is not always them.

    A note on a personal-safety case is internal — kept in the audit trail, shown to nobody outside the portal —
    and naming who was involved is often exactly what a responder has to write down. The check is a model call and
    advisory: if it can't run, the note is saved, because a check nobody can run is no reason to stop someone
    working."""
    named = private_person(note) if note and read_by_the_resident else None
    if named:
        raise NoteRefused(
            f"This note seems to name a private person (“{named}”). The resident's status page is opened by whoever "
            "holds the reference, so say what was done without naming anyone."
        )
