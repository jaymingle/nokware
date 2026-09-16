"""Things the public record would need to answer an ordinary question, that nobody publishes at all.

The publishing record asks whether a document the Assembly should publish
exists. "Figures that stop" asks whether a figure a document once gave is still
being given. This asks a third question, and it is the one the map of Accra's
electoral areas ran into: the thing was never published by anyone, so there is
no document to look for and no figure to go stale.

Each finding in app/data/unpublished_data.json names every source that was
checked and what it holds instead, with the date, so a reader can repeat the
search. A finding says what could not be found; it never says the Assembly broke
a duty.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data" / "unpublished_data.json"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    holds: str


@dataclass(frozen=True)
class Unpublished:
    id: str
    subject: str  # a short label, never slotted into a sentence
    headline: str  # the finding's own sentence, written out
    matters: str
    checked: list[Source]
    checked_on: str
    instead: str
    rti_document: str  # what to ask the Assembly for, in the RTI wording
    rti_period: str


@lru_cache
def _data() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def about() -> str:
    return str(_data()["about"])


def findings() -> list[Unpublished]:
    return [
        Unpublished(
            id=str(entry["id"]),
            subject=str(entry["subject"]),
            headline=str(entry["headline"]),
            matters=str(entry["matters"]),
            checked=[Source(str(s["name"]), str(s["url"]), str(s["holds"])) for s in entry["checked"]],
            checked_on=str(entry["checked_on"]),
            instead=str(entry["instead"]),
            rti_document=str(entry["rti_document"]),
            rti_period=str(entry["rti_period"]),
        )
        for entry in _data()["findings"]
    ]
