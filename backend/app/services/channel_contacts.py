"""Emergency numbers laid out for a phone: every number for a chat, and every number to call for a keypad.

A number that isn't independently verified is still listed, and says so: in an emergency a number worth trying beats
none.

On a keypad (USSD, SMS) only numbers callable from the phone in hand are listed. The unverified Police reporting lines
stay off it: USSD sessions time out, and the screen is better spent on DOVVSU's verified line.
"""

from app import safety_steps
from app.contacts import (
    MEDICAL_SERVICES,
    SAFETY_DESK_FALLBACK,
    SERVICE_NAMES,
    contacts,
    emergency_groups,
    service_groups,
    welfare_desk,
)
from app.schemas.contacts import ContactNumber, PublicContact
from app.wards import sub_metros

HEADING = "*If anyone is in danger now*, call. If a number doesn't connect, try the next one."
LABELS = {"police-main": "Police HQ, Accra", "gnfs": "GNFS Accra", "sw-head-office": "head office"}
CALL_ORDER = ("police", "dovvsu", "fire", "disaster", "ambulance", "helpline", "welfare")
CALL_LABELS = {"fire": "Fire", "disaster": "NADMO", "helpline": "Helpline of Hope (abuse, children)"}
# On a phone others may read: who each line is, not what it is for.
SMS_LABELS = {**CALL_LABELS, "helpline": "Helpline of Hope", "dovvsu": "DOVVSU"}
CALL_NOTES = {"police-main": "HQ"}
SMS_HEADING = "Call 112 first. If a number fails, try the next."


def _label(contact: PublicContact) -> str:
    """A short name where the heading doesn't already say it: "Police HQ, Accra", "Okaikoi South desk"."""
    desk = contact.id.removeprefix("sw-")
    return LABELS.get(contact.id) or (f"{sub_metros()[desk].name} desk" if desk in sub_metros() else "")


def _unverified(contact: PublicContact) -> str:
    by = f" by {contact.reported_by}" if contact.reported_by else ""
    via = f"reported via {contact.reported_via}{by}" if contact.reported_via else "reported on social media"
    return f"{via}, not independently verified"


def _line(contact: PublicContact, number: ContactNumber, note_each: bool) -> str:
    notes = [_label(contact), _unverified(contact) if note_each and contact.tier == 3 else "",
             "" if number.current else "an earlier listing, may not connect"]
    label = "; ".join(note for note in notes if note)
    prefix = "WhatsApp " if number.kind == "whatsapp" else ""
    return f"{prefix}{number.number}" + (f" ({label})" if label else "")


def _block(service: str, group: list[PublicContact]) -> str:
    all_unverified = all(contact.tier == 3 for contact in group)
    heading = f"*{SERVICE_NAMES[service]}*" + (f" ({_unverified(group[0])})" if all_unverified else "")
    lines = [_line(contact, number, not all_unverified) for contact in group for number in contact.numbers]
    return heading + "\n" + "\n".join(lines)


def _text(groups: list[tuple[str, list[PublicContact]]], heading: str = HEADING) -> str:
    return "\n\n".join([heading, *(_block(service, group) for service, group in groups)]) if groups else ""


def numbers_text(topic: str, sub_metro: str | None) -> str:
    return _text(emergency_groups(topic, sub_metro))


def _calls(contact: PublicContact) -> list[str]:
    note = f" ({CALL_NOTES[contact.id]})" if contact.id in CALL_NOTES else ""
    return [number.number + note for number in contact.numbers if number.current and number.kind == "call"]


def _welfare_calls(sub_metro: str | None) -> list[str]:
    desk, head = welfare_desk(sub_metro), _calls(contacts()[SAFETY_DESK_FALLBACK])
    return [*_calls(desk), *(f"head office {number}" for number in head)] if desk else head


def call_lines(topic: str, sub_metro: str | None, labels: dict[str, str] = CALL_LABELS) -> list[str]:
    """E.g. "Police: 191, 18555, 0302 779 300 (HQ)". 112 isn't a line: it leads the heading."""
    groups = dict(emergency_groups(topic, sub_metro)[1:])
    lines = []
    for service in (s for s in CALL_ORDER if s in groups):
        numbers = _welfare_calls(sub_metro) if service == "welfare" else [n for c in groups[service] for n in _calls(c)]
        lines.append(f"{labels.get(service, SERVICE_NAMES[service])}: {', '.join(numbers)}")
    return lines


def desk_line(sub_metro: str | None) -> str | None:
    desk = welfare_desk(sub_metro)
    return f"Your Social Welfare desk: {', '.join(_calls(desk))}" if desk else None


def numbers_sms(topic: str, sub_metro: str | None) -> str:
    """Nothing in it says what happened: others may read the phone."""
    return "\n".join([SMS_HEADING, *call_lines(topic, sub_metro, SMS_LABELS)])


def steps_text() -> str:
    return "\n".join(["*What to do now*", *(f"- {step}" for step in safety_steps.STEPS)])


def medical_text() -> str:
    heading = ("This isn't something the Assembly can act on, so Nokware won't file it. But here's who to call, "
               "and if a number doesn't connect, try the next one:")
    return _text(service_groups(MEDICAL_SERVICES, None), heading)
