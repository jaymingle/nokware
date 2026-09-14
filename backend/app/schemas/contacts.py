"""The contact directory: numbers, and where each comes from."""

from typing import Literal

from pydantic import BaseModel

Tier = Literal[1, 2, 3]


class ContactNumber(BaseModel):
    number: str  # as written, e.g. "0302 665 951"
    kind: Literal["call", "whatsapp"]
    # False for a number given to Nokware that differs from the one on the cited page; shown, but not as current.
    current: bool = True
    note: str | None = None  # why a number isn't current


class ContactSource(BaseModel):
    label: str  # the site, e.g. "ama.gov.gh"
    url: str
    checked: str  # the date the number was checked against this page


class PublicContact(BaseModel):
    """One office or line. Tier 1: a national emergency line. Tier 2: on an official site (source).
    Tier 3: reported on social media only (reported_via), not independently verified."""

    id: str
    service: str
    tier: Tier
    name: str
    detail: str | None = None
    numbers: list[ContactNumber]
    email: str | None = None
    source: ContactSource | None = None  # tier 2
    reported_via: str | None = None  # tier 3: the platform, e.g. "Facebook"; None if not known
    reported_by: str | None = None  # tier 3: who posted it, e.g. "the Mayor of Accra"
    press_url: str | None = None  # tier 3: a press report of it, if there is one


class Service(BaseModel):
    id: str
    name: str
    contacts: list[PublicContact]


class ContactDirectory(BaseModel):
    about: str
    checked: str
    services: list[Service]
