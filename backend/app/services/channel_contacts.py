"""Emergency numbers laid out for a phone chat: every number, grouped by service, one per line.

The same numbers the web shows (contacts.emergency_groups), in the order to try
them. A number that isn't independently verified says so, as it does on the
web: in an emergency a number worth trying beats none. An earlier listing of a
number is kept too, marked as one that may not connect.
"""

from app.contacts import SERVICE_NAMES, emergency_groups
from app.schemas.contacts import ContactNumber, PublicContact
from app.wards import sub_metros

HEADING = "*If anyone is in danger now*, call. If a number doesn't connect, try the next one."
LABELS = {"police-main": "Police HQ, Accra", "gnfs": "GNFS Accra", "sw-head-office": "head office"}


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


def numbers_text(topic: str, sub_metro: str | None) -> str:
    """Every emergency number for the topic, grouped by service. Empty for everyday topics."""
    groups = emergency_groups(topic, sub_metro)
    return "\n\n".join([HEADING, *(_block(service, group) for service, group in groups)]) if groups else ""
