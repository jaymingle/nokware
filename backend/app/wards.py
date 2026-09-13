"""AMA's electoral areas (the "wards" a report is located by) and sub-metros.

From AMA's own 2023 Monitoring and Evaluation Report (see ama_wards.json for
the citation). A civic report names a ward; a personal-safety report is located
no more finely than its sub-metro, or not at all.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

WARDS_FILE = Path(__file__).resolve().parent / "data" / "ama_wards.json"


@dataclass(frozen=True)
class Ward:
    id: str
    name: str
    sub_metro: str  # the sub-metro's id


@dataclass(frozen=True)
class SubMetro:
    id: str
    name: str


@lru_cache
def _load() -> tuple[dict[str, SubMetro], dict[str, Ward]]:
    raw = json.loads(WARDS_FILE.read_text(encoding="utf-8"))["sub_metros"]
    sub_metros = {entry["id"]: SubMetro(entry["id"], entry["name"]) for entry in raw}
    wards = {w["id"]: Ward(w["id"], w["name"], entry["id"]) for entry in raw for w in entry["wards"]}
    return sub_metros, wards


def sub_metros() -> dict[str, SubMetro]:
    return _load()[0]


def wards() -> dict[str, Ward]:
    return _load()[1]


def sub_metro_of(ward_id: str) -> str | None:
    ward = wards().get(ward_id)
    return ward.sub_metro if ward else None
