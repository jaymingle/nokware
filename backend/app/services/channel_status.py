"""A case's status as a phone message, from the same public_status() the web's status page shows.

A phone screen has no room for a whole trail, so it carries the last thing that happened — with the note staff
wrote at that step, trimmed to fit — and points at the web page for the rest. A USSD screen holds 160 characters
and nothing on it is tappable, so there the address loses its scheme and the step is cut to the note alone: the
headline above it has already said who holds the case and how far along it is, and what it has not said is why. If
even that will not fit, the step is what gives way, never the address — a resident left with a truncated link has
nowhere to go, whereas one left with the headline and the link still has everything.

A personal-safety case says only its stage: anyone holding a reference sees this, and a phone can be shared. Its
timeline is never read here at all.
"""

from datetime import datetime
from typing import Any

from app.services import case_timeline
from app.services.sms_text import bare_address, plain

NOTE_MAX = 200
LATEST_MIN = 24  # below this a trimmed step says nothing worth the room, so it is left off altogether
PRIVATE_WORDS = {"received": "received", "in_progress": "in progress", "completed": "completed"}


def _trimmed(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


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
        lines.append(f'{note["recipient"]} said: "{_trimmed(note["note"], NOTE_MAX)}"')
    if status.get("voices"):
        voices = status["voices"]
        lines.append(f"{voices} other resident{'s say' if voices > 1 else ' says'} it affects them too.")
    if status.get("escalate_until"):
        lines.append(f"Not fixed? You can escalate it until {_day(status['escalate_until'])} {where or f'at {site}/report/status'}")
    return lines


def latest_step(status: dict[str, Any], brief: bool = False) -> str | None:
    """The last thing that happened, and what staff wrote about it. Brief keeps the note alone: on a screen that
    small the step's own sentence mostly repeats the headline above it, and the note is the part that doesn't."""
    step = case_timeline.latest(status.get("timeline") or [])
    if step is None:
        return None
    if brief:
        return _trimmed(step.get("note") or step["description"], NOTE_MAX)
    said = f' "{_trimmed(step["note"], NOTE_MAX)}"' if step.get("note") else ""
    return f'{_day(step["at"])}: {step["description"]}{said}'


def status_text(status: dict[str, Any], site: str, compact: bool = False, limit: int | None = None) -> str:
    if status["private"]:
        return f"Reference {status['reference']}: {PRIVATE_WORDS[status['stage']]}."
    first = headline(status)
    if not compact:
        step = latest_step(status)
        rest = [*_details(status, site), *([f"Latest - {step}", f"Full history: {site}/report/status"] if step else [])]
        return plain("\n".join([first, *rest]))
    step = latest_step(status, brief=True)
    if step is None:
        return plain(first)
    whole = f"Full history: {bare_address(site)}/report/status"
    # What is left of the screen once the headline and the address have theirs, minus the two line breaks.
    room = (limit or len(first) + len(step) + len(whole) + 2) - len(plain(first)) - len(whole) - 2
    return plain("\n".join([first, *([_trimmed(step, room)] if room >= LATEST_MIN else []), whole]))


def spoken_details(status: dict[str, Any]) -> list[str]:
    """The details as read aloud on the status page: escalation is "on this page", not an address."""
    return _details(status, "", where="on this page")
