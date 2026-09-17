"""Who a citizen can call, and which of those numbers to show for a report.

The numbers live in data/contacts.json, each with where it comes from: a
national emergency line (tier 1), an official site checked on a given date
(tier 2; the file's date, unless the source carries its own), or a
social-media report shown as not independently verified (tier 3). Where a
number given to Nokware differs from the one on the cited page, both are shown
and the cited one is marked current. A number with no source at all is kept in
the file's "held" list and never shown.

Ghana's emergency hotlines often don't connect, so a report where someone may
be in danger shows every number we have for each service involved, in the order
to try them, so the citizen can work down the list. 112 comes first; then each
service the topic needs (EMERGENCY_TOPICS), and the ambulance for anything where
someone could be hurt. A personal-safety report gets the Police (with their
reporting lines, marked as not independently verified), DOVVSU (the Police's
Domestic Violence and Victim Support Unit), the Helpline of Hope, Social
Welfare (the citizen's sub-metro desk, or every desk if unknown, and the head
office) and the ambulance. Unverified numbers stay marked as such: in an
emergency a number worth trying beats none. Where a message can't hold the
list (an SMS about a report), short_line() gives two numbers per service; USSD
screens get the verified numbers that can be called (channel_contacts.call_lines).

An everyday report shows any numbers for its topic (ROUTES), or the Assembly's
switchboard. Safety reporters are never pointed to an Assembly Member: elected
politicians, not responders, and in a small area they may know the abuser.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.contacts import ContactDirectory, ContactSource, PublicContact, Service
from app.services.report_taxonomy import GNFS, POLICE, TOPICS_BY_ID, Category
from app.wards import sub_metros

CONTACTS_FILE = Path(__file__).resolve().parent / "data" / "contacts.json"

PUBLIC_EMERGENCY = "emergency-112"
SAFETY_DESK_FALLBACK = "sw-head-office"
# The emergency line of each agency a report can go to.
AGENCY_LINES = {POLICE: "police-191", GNFS: "fire-192"}
# Each emergency service's numbers, in the order to try them.
EMERGENCY_SERVICES: dict[str, tuple[str, ...]] = {
    "police": ("police-191", "police-18555", "police-main"),
    "police_reporting": ("police-mobile", "police-whatsapp"),  # reported via X: shown for personal safety
    "dovvsu": ("dovvsu",),  # the Police's Domestic Violence and Victim Support Unit
    "fire": ("fire-192", "gnfs"),
    "ambulance": ("ambulance-193", "nas"),
    "disaster": ("nadmo-emergency", "nadmo-whatsapp"),
    "helpline": ("helpline-of-hope",),
}
SERVICE_NAMES = {
    "emergency": "Any emergency", "police": "Police", "police_reporting": "Police reporting lines",
    "dovvsu": "DOVVSU (domestic violence)",
    "fire": "Fire service", "ambulance": "Ambulance",
    "disaster": "NADMO (floods and disasters)", "helpline": "Helpline of Hope (abuse and children)", "welfare": "Social Welfare",
}
SAFETY_SERVICES = ("police", "dovvsu", "police_reporting", "helpline", "welfare", "ambulance")
# The services an emergency topic needs; anything where someone could be hurt includes the ambulance.
EMERGENCY_TOPICS: dict[str, tuple[str, ...]] = {
    "fire": ("fire", "ambulance"),
    "disaster": ("disaster", "ambulance"),
    "structural_danger": ("fire", "ambulance"),  # rescue from a collapse is the fire service's
    "public_crime": ("police", "ambulance"),
    "road_accident": ("police", "ambulance"),
    **{t.id: SAFETY_SERVICES for t in TOPICS_BY_ID.values() if t.category == Category.PERSONAL_SAFETY},
}
# Numbers for a topic, after its emergency numbers. The waste route will add AMA
# Waste Management's own line once a source for it is found.
ROUTES = {
    "structural_danger": ("ama-general",),
    "solid_waste": ("ama-sanitation-whatsapp", "ama-general"),
    "sanitation_facilities": ("ama-sanitation-whatsapp", "ama-general"),
}
DEFAULT = ("ama-general",)
SHORT_PER_SERVICE = 2  # numbers per service where a screen can't hold them all
WITH_112 = ("police", "fire", "disaster")  # services whose short form leads with 112


def _contact(raw: dict[str, Any], sources: dict[str, Any], checked: str) -> PublicContact:
    fields = {k: v for k, v in raw.items() if k not in ("source", "sub_metro")}
    source = raw.get("source")
    contact = PublicContact(**fields, source=ContactSource(**{"checked": checked, **sources[source]}) if source else None)
    if (contact.tier == 2) != (contact.source is not None):
        raise ValueError(f"contact {contact.id}: tier 2 needs a source, and only tier 2 has one")
    if not any(n.current for n in contact.numbers) or any(not n.current and not n.note for n in contact.numbers):
        raise ValueError(f"contact {contact.id}: needs a current number, and a note on any that isn't")
    return contact


@lru_cache
def _load() -> tuple[dict[str, Any], dict[str, PublicContact]]:
    raw = json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
    contacts = {c["id"]: _contact(c, raw["sources"], raw["checked"]) for c in raw["contacts"]}
    return raw, contacts


def _desks() -> dict[str, str]:
    """Sub-metro ID -> the contact ID of its Social Welfare desk."""
    return {c["sub_metro"]: c["id"] for c in _load()[0]["contacts"] if c.get("sub_metro")}


def contacts() -> dict[str, PublicContact]:
    return _load()[1]


def directory() -> ContactDirectory:
    raw, by_id = _load()
    services = [
        Service(id=s["id"], name=s["name"], contacts=[c for c in by_id.values() if c.service == s["id"]])
        for s in raw["services"]
    ]
    return ContactDirectory(about=raw["about"], checked=raw["checked"], services=services)


def welfare_desk(sub_metro: str | None) -> PublicContact | None:
    """The Social Welfare desk of a sub-metro, if it has one."""
    desk = _desks().get(sub_metro or "")
    return contacts()[desk] if desk else None


def _welfare(sub_metro: str | None) -> list[str]:
    """The citizen's sub-metro desk, or every desk if we don't know it, then the head office."""
    desks = _desks()
    return [desks.get(sub_metro), *([] if sub_metro in desks else desks.values()), SAFETY_DESK_FALLBACK]


# A medical emergency isn't the Assembly's to act on: nothing is filed, but the numbers are given.
MEDICAL_SERVICES = ("ambulance",)


def emergency_groups(topic: str, sub_metro: str | None) -> list[tuple[str, list[PublicContact]]]:
    """Every number for each service an emergency topic needs, by service, 112 first. Empty for everyday topics."""
    return service_groups(EMERGENCY_TOPICS.get(topic, ()), sub_metro)


def service_groups(services: tuple[str, ...], sub_metro: str | None) -> list[tuple[str, list[PublicContact]]]:
    """112, then every number of each service, in the order to try them."""
    if not services:
        return []
    groups = [("emergency", [PUBLIC_EMERGENCY])]
    groups += [(s, _welfare(sub_metro) if s == "welfare" else list(EMERGENCY_SERVICES[s])) for s in services]
    return [(service, [contacts()[i] for i in ids if i]) for service, ids in groups]


def safety_contacts(sub_metro: str | None) -> list[PublicContact]:
    """For a report about a danger to a person: every number to try, in order."""
    return for_report("abuse", sub_metro)


def emergency_lines(topic: str) -> list[str]:
    """112 for anything that endangers the public, and the line of each agency the report goes to."""
    found = TOPICS_BY_ID[topic]
    lines = [PUBLIC_EMERGENCY] if found.category == Category.PUBLIC_SAFETY else []
    return lines + [AGENCY_LINES[r] for r in found.recipients if r in AGENCY_LINES]


def for_report(topic: str, sub_metro: str | None) -> list[PublicContact]:
    """The numbers to show a citizen for their report: every emergency number, then the topic's own."""
    urgent = [c.id for _, group in emergency_groups(topic, sub_metro) for c in group]
    extra = ROUTES.get(topic, () if urgent else DEFAULT)
    return [contacts()[i] for i in dict.fromkeys([*urgent, *extra])]


def short_line(topic: str, sub_metro: str | None) -> str:
    """Two numbers per service, for an SMS or a USSD screen: "Police: 112, 191. Ambulance: 193, 0501 614 877."."""
    parts = []
    for service, group in emergency_groups(topic, sub_metro)[1:]:
        if service == "police_reporting":
            continue
        if service == "welfare":  # one number: their desk, or the head office when we don't know where they are
            group = [contacts()[_desks().get(sub_metro or "", SAFETY_DESK_FALLBACK)]]
        numbers = (["112"] if service in WITH_112 else []) + [n.number for c in group for n in c.numbers if n.current and n.kind == "call"]
        label = {"helpline": "Helpline", "disaster": "NADMO", "fire": "Fire"}.get(service, SERVICE_NAMES[service])
        parts.append(f"{label}: {', '.join(numbers[: 1 if service == 'welfare' else SHORT_PER_SERVICE])}.")
    return " ".join(parts)


def _check() -> None:
    """Fail at import if a route names a contact or topic that doesn't exist."""
    known = contacts()
    named = {SAFETY_DESK_FALLBACK, *DEFAULT, PUBLIC_EMERGENCY, *AGENCY_LINES.values(),
             *(i for ids in ROUTES.values() for i in ids), *(i for ids in EMERGENCY_SERVICES.values() for i in ids)}
    missing = named - set(known)
    if missing or not set(ROUTES) | set(EMERGENCY_TOPICS) <= set(TOPICS_BY_ID):
        raise ValueError(f"contact routes name unknown contacts {sorted(missing)} or topics")
    services = {s["id"] for s in _load()[0]["services"]}
    if any(c.service not in services for c in known.values()):
        raise ValueError("a contact names an unknown service")
    if not set(_desks()) <= set(sub_metros()):
        raise ValueError("a Social Welfare desk names an unknown sub-metro")


_check()
