"""Who a citizen can call, and which of those numbers to show for a report.

The numbers live in data/contacts.json, each with where it comes from: a
national emergency line (tier 1), an official site checked on a given date
(tier 2), or a social-media report shown as not independently verified
(tier 3). Numbers whose stated source didn't hold up are kept in its "held"
list and never shown.

A report's confirmation shows the numbers for where it went (ROUTES below). A
personal-safety report also gets the Social Welfare desk for the sub-metro the
citizen gave, or the head office if they gave none.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.schemas.contacts import ContactDirectory, ContactSource, PublicContact, Service
from app.services.report_taxonomy import TOPICS_BY_ID, Category
from app.wards import sub_metros

CONTACTS_FILE = Path(__file__).resolve().parent / "data" / "contacts.json"

SAFETY = ("emergency-112", "police-191", "police-18555", "helpline-of-hope")
SAFETY_DESK_FALLBACK = "sw-head-office"
# By topic; any topic not listed gets DEFAULT. The waste route will add AMA
# Waste Management's own line once a source for it is found.
ROUTES = {
    "fire": ("emergency-112", "fire-192", "gnfs"),
    "disaster": ("emergency-112", "nadmo-emergency"),
    "solid_waste": ("ama-sanitation-whatsapp", "ama-general"),
    "sanitation_facilities": ("ama-sanitation-whatsapp", "ama-general"),
}
DEFAULT = ("ama-general",)


def _contact(raw: dict[str, Any], sources: dict[str, Any], checked: str) -> PublicContact:
    fields = {k: v for k, v in raw.items() if k not in ("source", "sub_metro")}
    source = raw.get("source")
    contact = PublicContact(**fields, source=ContactSource(**sources[source], checked=checked) if source else None)
    if (contact.tier == 2) != (contact.source is not None):
        raise ValueError(f"contact {contact.id}: tier 2 needs a source, and only tier 2 has one")
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


def safety_contacts(sub_metro: str | None) -> list[PublicContact]:
    """For a report about a danger to a person: emergency lines, the helpline, and the nearest Social Welfare desk."""
    desk = _desks().get(sub_metro or "", SAFETY_DESK_FALLBACK)
    return [contacts()[i] for i in (*SAFETY, desk)]


def for_report(topic: str, sub_metro: str | None) -> list[PublicContact]:
    """The numbers to show a citizen for where their report went."""
    if TOPICS_BY_ID[topic].category == Category.PERSONAL_SAFETY:
        return safety_contacts(sub_metro)
    return [contacts()[i] for i in ROUTES.get(topic, DEFAULT)]


def _check() -> None:
    """Fail at import if a route names a contact or topic that doesn't exist."""
    known = contacts()
    named = {*SAFETY, SAFETY_DESK_FALLBACK, *DEFAULT, *(i for ids in ROUTES.values() for i in ids)}
    missing = named - set(known)
    if missing or not set(ROUTES) <= set(TOPICS_BY_ID):
        raise ValueError(f"contact routes name unknown contacts {sorted(missing)} or topics")
    services = {s["id"] for s in _load()[0]["services"]}
    if any(c.service not in services for c in known.values()):
        raise ValueError("a contact names an unknown service")
    if not set(_desks()) <= set(sub_metros()):
        raise ValueError("a Social Welfare desk names an unknown sub-metro")


_check()
