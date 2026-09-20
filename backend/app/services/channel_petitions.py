"""A petition's standing as a phone message, from the same records the web page is built from.

Someone who signed on a keypad has no page to go back to, so the number they typed has to be enough to ask what
became of it. What comes back is what the public page says: the stage, the signatures and the closing date.

A removed petition answers from its removal record alone, exactly as its page does — the ground, the date, the
duplicate's number and how often it had come down before. The petition itself is never read for that, so no title,
body or image can reach a reader here through an oversight somewhere else.

A USSD screen holds 160 characters. The first line and the address always go; what sits between them is kept while
there is room, in the order it matters, because a resident left with a cut address has nowhere to go.
"""

from dataclasses import dataclass
from typing import Any

from app.services import petition_removals, petitions
from app.services.ledger_documents import parse_datetime
from app.services.petition_removals import Tombstone
from app.services.petition_rules import SIGNING, STATUS_WORDS, PetitionStatus, is_public
from app.services.phrases import phrase
from app.services.sms_text import bare_address, plain


@dataclass(frozen=True)
class Standing:
    """A petition as it stands, or the tombstone of one that was removed. Never both, and never neither."""

    code: str
    petition: dict[str, Any] | None
    tombstone: Tombstone | None


def standing(code: str) -> Standing:
    """Raises PetitionNotFound when no petition has that number, and when one has it but has never been public."""
    found = petitions.find(code)
    if is_public(found):
        return Standing(str(found["code"]), found, None)
    removal = petition_removals.latest_removal(found["$id"])
    if removal is None:
        raise petitions.PetitionNotFound(code)
    return Standing(str(found["code"]), None, petition_removals.tombstone(removal))


def _number(code: str) -> str:
    return f"{code[:3]} {code[3:]}"


def _day(iso: str | None, compact: bool) -> str | None:
    when = parse_datetime(iso)
    if when is None:
        return None
    return f"{when:%-d %b %Y}" if compact else f"{when:%-d %B %Y}"


def _fit(first: str, rest: list[str], address: str, limit: int | None) -> str:
    kept: list[str] = [first]
    room = (limit or 0) - len(first) - len(address) - 1
    for line in rest:
        if limit is None or len(line) + 1 <= room:
            kept.append(line)
            room -= len(line) + 1
    return plain("\n".join([*kept, address]))


def _counted(petition: dict[str, Any]) -> str:
    signatures, threshold = int(petition.get("signatureCount") or 0), petition.get("threshold")
    if not threshold:
        return phrase("petition.channel.signatures_only").format(signatures=f"{signatures:,}")
    return phrase("petition.channel.signatures").format(signatures=f"{signatures:,}", threshold=f"{int(threshold):,}")


def _open_lines(petition: dict[str, Any], compact: bool) -> list[str]:
    closes = _day(petition.get("closesAt"), compact) if petition.get("status") in SIGNING else None
    return [_counted(petition), *([phrase("petition.channel.closes").format(day=closes)] if closes else [])]


def _removed_lines(stone: Tombstone) -> list[str]:
    """The duplicate's number goes before the rest: on a screen with room for one line it is the one that sends a
    reader somewhere, and the ground above it has already said this petition duplicated another."""
    lines = []
    if stone.duplicate_of:
        lines.append(phrase("petition.channel.removed_duplicate").format(other=_number(stone.duplicate_of)))
    lines.append(phrase("petition.channel.removed_nothing_public"))
    if stone.previous_removals == 1:
        lines.append(phrase("petition.channel.removed_before_once"))
    elif stone.previous_removals > 1:
        lines.append(phrase("petition.channel.removed_before").format(count=stone.previous_removals))
    return lines


def standing_text(found: Standing, site: str, compact: bool = False, limit: int | None = None) -> str:
    """`compact` is the USSD form: nothing is tappable there, so the address loses its scheme."""
    address = f"{bare_address(site) if compact else site.rstrip('/')}/petitions/{found.code}"
    if found.tombstone is not None:
        stone = found.tombstone
        first = phrase("petition.channel.removed").format(
            number=_number(found.code), day=_day(stone.removed_at, compact), ground=stone.ground_words)
        return _fit(first, _removed_lines(stone), address, limit)
    petition = found.petition or {}
    stage = phrase(STATUS_WORDS[PetitionStatus(str(petition["status"]))])
    first = phrase("petition.channel.standing").format(number=_number(found.code), stage=stage)
    return _fit(first, _open_lines(petition, compact), address, limit)
