"""Ask's answers laid out for a phone: WhatsApp text with numbered sources, or an SMS of two pages at most.

This only lays the answer out; the web's rules are already applied. Live report figures are named as such in the
answer's own words, so their tags are dropped and one line says what live report data is.
"""

import re

from app.services.citations import FIGURE_KINDS, KINDS
from app.services.rag import NO_INFO_ANSWER, RagAnswer, Source
from app.services.sms_text import bare_address, pages, plain

CHAT_TITLE_MAX = 90
SMS_PAGES = 2
MIN_BODY = 60  # however little room the pointer leaves, the answer still gets this much
SMS_TITLE_MAX = 40
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


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _cited_order(text: str) -> list[str]:
    return list(dict.fromkeys(_DOCUMENT_TAG.findall(text)))


def _documents(answer: RagAnswer) -> dict[str, Source]:
    """The retrieval returns a row per passage."""
    documents: dict[str, Source] = {}
    for source in answer["sources"]:
        documents.setdefault(source["label"], source)
    return documents


def _describe(source: Source, title_max: int) -> str:
    title = _clip((source["title"] or "Untitled document").rstrip(" ."), title_max)
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


def _fit(body: str, room: int) -> tuple[str, bool]:
    """(what fits, whether anything was left behind)."""
    if len(body) <= room:
        return body, False
    cut = body[:room]
    sentence_end = cut.rfind(". ")
    if sentence_end > room // 2:
        return cut[: sentence_end + 1], True
    return cut[: room - 3].rsplit(" ", 1)[0] + "...", True


def _sms_source(answer: RagAnswer) -> str:
    order = _cited_order(answer["answer"])
    documents = _documents(answer)
    if order and order[0] in documents:
        return f" Source: {_describe(documents[order[0]], SMS_TITLE_MAX)}."
    return " Source: Nokware live report data." if any(f["cited"] for f in answer["figures"]) else ""


def for_sms(answer: RagAnswer, site: str) -> str:
    """Two pages, and when the answer doesn't fit in them it says so rather than stopping mid-thought: a reader
    who can't tell a short answer from a cut one doesn't know whether to go looking for the rest."""
    if answer["status"] == "no_information":
        return plain(f"Nokware: {NO_INFO_ANSWER} More at {site}/ask")
    flat = _ANY_TAG.sub("", answer["answer"])
    flat = plain(" ".join(_HEADING.sub("", _BOLD.sub(r"\1", _BULLET.sub(r"\1", flat))).replace("*", "").split()))
    prefix = "" if flat.startswith("Nokware") else "Nokware: "  # the sender ID may not say Nokware
    suffix = plain(_sms_source(answer))
    more = plain(f" First part only. All of it: {bare_address(site)}/ask")
    room = SMS_PAGES * 153 - len(prefix) - len(suffix)
    message, cut = _compose(prefix, flat, suffix, more, room)
    while pages(message) > SMS_PAGES:  # extended characters take two places: trim until it fits
        room -= 10
        message, cut = _compose(prefix, flat, suffix, more, room)
    return message


def _compose(prefix: str, flat: str, suffix: str, more: str, room: int) -> tuple[str, bool]:
    """The pointer to the rest is paid for out of the room the answer has, never added on top of a full two pages."""
    body, cut = _fit(flat, room)
    if not cut:
        return f"{prefix}{body}{suffix}", False
    body, _ = _fit(flat, max(room - len(more), MIN_BODY))
    return f"{prefix}{body}{suffix}{more}", True
