"""AMA's electoral areas (the "wards" a report is located by), its sub-metros, and who chairs each.

As given from ama.gov.gh (see ama_wards.json for the citation). Where AMA's
2023 Monitoring and Evaluation Report spells an area differently, that
spelling is kept as an alternate, and find_ward matches either. A civic report
names a ward; a personal-safety report is located no more finely than its
sub-metro, or not at all.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

WARDS_FILE = Path(__file__).resolve().parent / "data" / "ama_wards.json"


@dataclass(frozen=True)
class Ward:
    id: str
    name: str
    sub_metro: str  # the sub-metro's id
    alternates: tuple[str, ...] = ()  # other spellings in AMA's documents
    note: str | None = None


@dataclass(frozen=True)
class SubMetro:
    id: str
    name: str
    chairperson: str = ""
    chairperson_area: str = ""  # the electoral area the chairperson represents, as given
    office: str = ""  # where the sub-metro office is


def _ward(raw: dict[str, Any], sub_metro: str) -> Ward:
    return Ward(raw["id"], raw["name"], sub_metro, tuple(raw.get("alternates", ())), raw.get("note"))


def _sub_metro(raw: dict[str, Any]) -> SubMetro:
    return SubMetro(raw["id"], raw["name"], raw.get("chairperson", ""), raw.get("chairperson_area", ""), raw.get("office", ""))


@lru_cache
def _raw() -> dict[str, Any]:
    return json.loads(WARDS_FILE.read_text(encoding="utf-8"))


@lru_cache
def _load() -> tuple[dict[str, SubMetro], dict[str, Ward]]:
    raw = _raw()["sub_metros"]
    sub_metros = {entry["id"]: _sub_metro(entry) for entry in raw}
    wards = {w["id"]: _ward(w, entry["id"]) for entry in raw for w in entry["wards"]}
    return sub_metros, wards


def sub_metros() -> dict[str, SubMetro]:
    return _load()[0]


def wards() -> dict[str, Ward]:
    return _load()[1]


def source() -> dict[str, str]:
    """Where the electoral areas and chairpersons come from: a label and URL."""
    return {key: _raw()["source"][key] for key in ("label", "url")}


def sub_metro_of(ward_id: str) -> str | None:
    ward = wards().get(ward_id)
    return ward.sub_metro if ward else None


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def find_ward(text: str) -> Ward | None:
    """An electoral area by any of its spellings ("Bubuashie", "bubiashie", "Nmlitsa-Gonno", "Nmlitsagonno")."""
    key = _key(text)
    return next((w for w in wards().values() if key in {_key(w.name), *map(_key, w.alternates)}), None) if key else None


def _words(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def ward_mentioned(text: str) -> Ward | None:
    """The one electoral area a sentence names ("the drain at Kaneshie market"), by any spelling, as whole
    words. None if it names none, or more than one (then the citizen is asked)."""
    sentence = _words(text)
    named = [w for w in wards().values() if any(_words(name) in sentence for name in (w.name, *w.alternates))]
    return named[0] if len(named) == 1 else None
