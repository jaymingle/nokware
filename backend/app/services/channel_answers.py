"""Ask's answers laid out for a phone: WhatsApp text with numbered sources, SMS parts, or USSD screens.

This only lays the answer out; the web's rules are already applied. Live report figures are named as such in the
answer's own words, so their tags are dropped and one line says what live report data is.

An answer is never truncated. Longer than one page, it is paged: numbered parts of whole sentences, the citation
and the web address in the last one. A reader who can't tell a short answer from a cut one doesn't know whether
to go looking for the rest.
"""

import logging
import re
from collections.abc import Callable

from app.services.citations import FIGURE_KINDS, KINDS
from app.services.rag import NO_INFO_ANSWER, RagAnswer, Source
from app.services.sms_text import bare_address, cost, part_room, plain

logger = logging.getLogger(__name__)

CHAT_TITLE_MAX = 90
SMS_PARTS = 3  # the ceiling: an answer costs the Assembly at most three credits
NUMBERING = len(" (1/3)")
SMS_TITLE_MAX = 40
SCREEN_MAX = 160  # Arkesel's USSD screen; ussd.SCREEN_MAX is the same limit, on the menus it adds to these screens
LIVE_DATA_NAME = "Nokware live report data"

Reask = Callable[[], RagAnswer]  # a shorter answer to the same question, asked for once when the first won't fit
LIVE_DATA_NOTE = (
    "Counts called live report data come from reports residents filed with Nokware, not from a published "
    'document, and a count from 1 to 4 reads "fewer than 5".'
)
# A budget figure is the opposite of a live count: it IS from a published document, so it needs its own note.
BUDGET_DATA_NOTE = "Budget figures are approved amounts from AMA's published budgets, not money released or spent."
_DOCUMENT_TAG = re.compile(r"\[(S\d+)\]")
_ANY_TAG = re.compile(rf"\s*\[[{KINDS}]\d+\]")
_FIGURE_TAG = re.compile(rf"\s*\[[{FIGURE_KINDS}]\d+\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^#+\s*", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[*-] ", re.MULTILINE)  # markdown bullets, which WhatsApp would show as stars
_CITED_TAG = re.compile(rf"\[([{KINDS}]\d+)\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_CLAUSE = re.compile(r"(?<=[,;:])\s+")


def _cited_order(text: str) -> list[str]:
    return list(dict.fromkeys(_DOCUMENT_TAG.findall(text)))


def _documents(answer: RagAnswer) -> dict[str, Source]:
    """The retrieval returns a row per passage."""
    documents: dict[str, Source] = {}
    for source in answer["sources"]:
        documents.setdefault(source["label"], source)
    return documents


def _title(title: str | None, limit: int = SMS_TITLE_MAX) -> str:
    """Clipped between words: half a word, or an ellipsis, reads as a cut message rather than a long title."""
    name = (title or "Untitled document").rstrip(" .")
    return name if len(name) <= limit else name[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")


def _describe(source: Source, title_max: int) -> str:
    title = _title(source["title"], title_max)
    detail = ", ".join(str(part) for part in (source["department_name"], source["document_year"]) if part)
    return f"{title} ({detail})" if detail else title


def _no_information(site: str) -> str:
    return f"{NO_INFO_ANSWER} See what the Ledger holds, or how to request a document under the RTI Act: {site}/ask"


def for_chat(answer: RagAnswer, site: str) -> str:
    if answer["status"] == "no_information":
        return _no_information(site)
    text = answer["answer"]
    numbers = {label: position for position, label in enumerate(_cited_order(text), 1)}
    body = _DOCUMENT_TAG.sub(lambda match: f"[{numbers[match[1]]}]", _FIGURE_TAG.sub("", text))
    parts = [_HEADING.sub("", _BOLD.sub(r"*\1*", _BULLET.sub("\\1\u2022 ", body))).strip()]
    documents = _documents(answer)
    if numbers:
        listed = [f"[{number}] {_describe(documents[label], CHAT_TITLE_MAX)}" for label, number in numbers.items() if label in documents]
        parts.append("Sources:\n" + "\n".join(listed))
    cited = {figure.get("source", "reports") for figure in answer["figures"] if figure["cited"]}
    parts += [note for kind, note in (("reports", LIVE_DATA_NOTE), ("documents", BUDGET_DATA_NOTE)) if kind in cited]
    return "\n\n".join(parts)


def flat_text(text: str) -> str:
    """One run of plain characters: no citation tags, no markdown, single spaces - what a small screen can show."""
    stripped = _HEADING.sub("", _BOLD.sub(r"\1", _BULLET.sub(r"\1", _ANY_TAG.sub("", text)))).replace("*", "")
    return plain(" ".join(stripped.split()))


def _broken(piece: str, room: int) -> list[str]:
    """A sentence too long for one page: its clauses, and a clause still too long, its words - never a word split."""
    bits: list[str] = []
    for clause in _CLAUSE.split(piece):
        if cost(clause) <= room:
            bits.append(clause)
            continue
        for word in clause.split(" "):
            if bits and cost(f"{bits[-1]} {word}") <= room:
                bits[-1] = f"{bits[-1]} {word}"
            else:
                bits.append(word)
    return bits


def _split(text: str, room: int) -> list[str]:
    """The text as sentences, none of them wider than a page."""
    pieces: list[str] = []
    for sentence in _SENTENCE.split(text):
        pieces += [sentence] if cost(sentence) <= room else _broken(sentence, room)
    return [piece for piece in pieces if piece]


def _pack(pieces: list[str], room: int, tail: str = "", limit: int | None = None) -> list[str] | None:
    """Whole pieces filled into pages of `room` places, `tail` fixed to the end of the last page.

    None when that takes more pages than `limit`, so the caller can ask for a shorter answer instead of cutting one.
    """
    parts = [""]
    for piece in pieces:
        joined = f"{parts[-1]} {piece}".strip()
        if cost(joined) <= room:
            parts[-1] = joined
        else:
            parts.append(piece)
    if cost(f"{parts[-1]}{tail}") <= room:
        parts[-1] += tail
    elif tail:
        parts.append(tail.strip())
    kept = [part for part in parts if part]
    return None if limit is not None and len(kept) > limit else kept


def _numbered(parts: list[str]) -> list[str]:
    """One part stands alone; more than one says which of how many, so nothing looks like the whole of it."""
    if len(parts) < 2:
        return parts
    return [f"{part} ({number}/{len(parts)})" for number, part in enumerate(parts, 1)]


def _named(answer: RagAnswer, detail: bool) -> list[str]:
    """What the answer cites, in the order it cites it: every document, and live report data where it was used."""
    documents, figures = _documents(answer), {figure["label"]: figure for figure in answer["figures"]}
    names: list[str] = []
    for label in dict.fromkeys(_CITED_TAG.findall(answer["answer"])):
        figure = figures.get(label)
        if label in documents:
            name = _describe(documents[label], SMS_TITLE_MAX) if detail else _title(documents[label]["title"])
        elif figure is None:
            continue
        elif figure.get("source", "reports") == "documents":
            year = f" ({figure['year']})" if detail and figure.get("year") else ""
            name = _title(figure.get("document_title")) + year
        else:
            name = LIVE_DATA_NAME
        if name not in names:
            names.append(name)
    return [plain(name) for name in names]


def _listed(names: list[str], hidden: int) -> str:
    if not names:
        return ""
    more = f" and {hidden} more" if hidden else ""
    label = "Source" if len(names) == 1 and not hidden else "Sources"
    return f" {label}: {'; '.join(names)}{more}."


def _sources_line(answer: RagAnswer, room: int) -> str:
    """Every document the answer cites, named. Naming the first and calling it the source of the whole answer
    tells the resident a figure came from a document it didn't; a count of the rest is honest where names don't fit.
    """
    full, short = (_named(answer, detail) for detail in (True, False))
    fewer = [(short[:keep], len(short) - keep) for keep in range(len(short) - 1, 0, -1)]
    for names, hidden in [(full, 0), (short, 0), *fewer]:
        line = _listed(names, hidden)
        if cost(line) <= room:
            return line
    return ""


def _sms_body(answer: RagAnswer) -> str:
    flat = flat_text(answer["answer"])
    return flat if flat.startswith("Nokware") else f"Nokware: {flat}"  # the sender ID may not say Nokware


def _sms_parts(answer: RagAnswer, site: str) -> list[str] | None:
    if answer["status"] == "no_information":
        return [plain(f"Nokware: {NO_INFO_ANSWER} More at {bare_address(site)}/ask")]
    body, ending = _sms_body(answer), plain(f" Also at {bare_address(site)}/ask")
    room = part_room(body + ending) - NUMBERING
    tail = _sources_line(answer, room - cost(ending)) + ending
    room = min(room, part_room(body + tail) - NUMBERING)  # one character outside GSM-7 halves every page
    parts = _pack(_split(body, room), room, tail, SMS_PARTS)
    return _numbered(parts) if parts else None


def for_sms(answer: RagAnswer, site: str, shorter: Reask | None = None) -> list[str]:
    """The answer in numbered parts of whole sentences, three SMS pages at most, its citation and address last.

    An answer that won't fit is asked for again, shorter, rather than cut; `shorter` re-asks the model.
    """
    parts = _sms_parts(answer, site)
    if parts is None and shorter is not None:
        answer = shorter()  # asked once only: a second re-ask costs a resident their answer to save a page
        parts = _sms_parts(answer, site)
    if parts is not None:
        return parts
    logger.warning("An SMS answer still needed more than %d pages after a shorter one was asked for", SMS_PARTS)
    return _as_much_as_fits(answer, site)


def _as_much_as_fits(answer: RagAnswer, site: str) -> list[str]:
    """Whole sentences as far as they go, and the last part says where the rest is: a sentence is dropped entire
    or kept entire, never half-sent."""
    ending = plain(f" More at {bare_address(site)}/ask")
    body = _sms_body(answer)
    room = part_room(body + ending) - NUMBERING
    sentences = _SENTENCE.split(body)
    for keep in range(len(sentences), 0, -1):
        kept = _split(" ".join(sentences[:keep]), room - cost(ending))
        parts = _pack(kept, room, ending, SMS_PARTS)
        if parts is not None:
            return _numbered(parts)
    # One sentence wider than the whole ceiling: it goes out complete over a page more, which is cheaper than
    # a resident acting on half of it. Already logged as rare.
    return _numbered(_pack(_split(sentences[0], room - cost(ending)), room, ending) or [body])


def screens(text: str, menu_cost: int, limit: int = SCREEN_MAX) -> list[str]:
    """The answer for USSD: screens split at sentence or clause boundaries, with room left for the caller's menu.

    `menu_cost` is what the lines the caller appends ("1 More / 0 Back") take. Joining the screens with a space
    gives back flat_text(text) exactly.
    """
    room = limit - menu_cost
    return _pack(_split(flat_text(text), room), room) or []
