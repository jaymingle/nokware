"""A case's status as a phone message, from the same public_status() the web's status page shows.

A personal-safety case says only its stage: received, in progress or completed.
Anyone holding a reference sees this, and a phone can be shared. An everyday
case says what and where, who has it, what they said when they resolved it, how
many residents added their voice, and until when it can be escalated. The
compact form (a USSD screen) keeps to the first sentence.
"""

from datetime import datetime
from typing import Any

from app.services.sms_text import plain

NOTE_MAX = 200
PRIVATE_WORDS = {"received": "received", "in_progress": "in progress", "completed": "completed"}


def _day(iso: str) -> str:
    return f"{datetime.fromisoformat(iso):%-d %b}"


def _headline(status: dict[str, Any]) -> str:
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


def _details(status: dict[str, Any], site: str) -> list[str]:
    lines = []
    for note in status.get("resolution_notes") or []:
        text = note["note"] if len(note["note"]) <= NOTE_MAX else note["note"][: NOTE_MAX - 3].rstrip() + "..."
        lines.append(f'{note["recipient"]} said: "{text}"')
    if status.get("voices"):
        voices = status["voices"]
        lines.append(f"{voices} other resident{'s say' if voices > 1 else ' says'} it affects them too.")
    if status.get("escalate_until"):
        lines.append(f"Not fixed? You can escalate it until {_day(status['escalate_until'])} at {site}/report/status")
    return lines


def status_text(status: dict[str, Any], site: str, compact: bool = False) -> str:
    """The status as plain text: one sentence when compact, with the details otherwise."""
    if status["private"]:
        return f"Reference {status['reference']}: {PRIVATE_WORDS[status['stage']]}."
    headline = _headline(status)
    return plain(headline if compact else "\n".join([headline, *_details(status, site)]))
