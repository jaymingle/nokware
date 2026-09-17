"""A case's status as a phone message, from the same public_status() the web's status page shows.

A personal-safety case says only its stage: anyone holding a reference sees this, and a phone can be shared.
"""

from datetime import datetime
from typing import Any

from app.services.sms_text import plain

NOTE_MAX = 200
PRIVATE_WORDS = {"received": "received", "in_progress": "in progress", "completed": "completed"}


def _day(iso: str) -> str:
    return f"{datetime.fromisoformat(iso):%-d %b}"


def headline(status: dict[str, Any]) -> str:
    what = status["topic"] + (f" in {status['ward']}" if status.get("ward") else "")
    who = " and ".join(status["recipients"]) or "the Assembly"
    reference = status["reference"]
    if status["status"] == "escalated":
        return f"Report {reference} ({what}) is with the MCE's office for review."
    if status["status"] == "resolved":
        return f"Report {reference} ({what}) was resolved by {who}."
    if status["status"] == "in_progress":
        return f"Report {reference} ({what}) is in progress with {who}."
    return f"Report {reference} ({what}) was received and is with {who}."


def _details(status: dict[str, Any], site: str, where: str | None = None) -> list[str]:
    """`where` is where to escalate: the status page's address in a message."""
    lines = []
    for note in status.get("resolution_notes") or []:
        text = note["note"] if len(note["note"]) <= NOTE_MAX else note["note"][: NOTE_MAX - 3].rstrip() + "..."
        lines.append(f'{note["recipient"]} said: "{text}"')
    if status.get("voices"):
        voices = status["voices"]
        lines.append(f"{voices} other resident{'s say' if voices > 1 else ' says'} it affects them too.")
    if status.get("escalate_until"):
        lines.append(f"Not fixed? You can escalate it until {_day(status['escalate_until'])} {where or f'at {site}/report/status'}")
    return lines


def status_text(status: dict[str, Any], site: str, compact: bool = False) -> str:
    if status["private"]:
        return f"Reference {status['reference']}: {PRIVATE_WORDS[status['stage']]}."
    first = headline(status)
    return plain(first if compact else "\n".join([first, *_details(status, site)]))


def spoken_details(status: dict[str, Any]) -> list[str]:
    """The details as read aloud on the status page: escalation is "on this page", not an address."""
    return _details(status, "", where="on this page")
