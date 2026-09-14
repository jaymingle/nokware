"""Ask's answers laid out for a phone: WhatsApp text with numbered sources, or an SMS of two pages at most.

The answer comes from rag.answer_question() at the channel's length, with the
web's rules intact (sources, live figures, "fewer than 5", the safety refusal);
this only lays it out. Document citations become [1], [2] in the order they
first appear, with the documents listed underneath. Live report figures are
already named as such in the answer's own words, so their tags are dropped and
one line says what live report data is. An SMS keeps one source, the first cited.
"""

import re

from app.services.rag import NO_INFO_ANSWER, RagAnswer, Source
from app.services.sms_text import pages, plain

CHAT_TITLE_MAX = 90
SMS_PAGES = 2
SMS_TITLE_MAX = 40
LIVE_DATA_NOTE = (
    "Counts called live report data come from reports residents filed with Nokware, not from a published "
    'document, and a count from 1 to 4 reads "fewer than 5".'
)
_DOCUMENT_TAG = re.compile(r"\[(S\d+)\]")
_ANY_TAG = re.compile(r"\s*\[[SR]\d+\]")
_FIGURE_TAG = re.compile(r"\s*\[R\d+\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_HEADING = re.compile(r"^#+\s*", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[*-] ", re.MULTILINE)  # markdown bullets, which WhatsApp would show as stars


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _cited_order(text: str) -> list[str]:
    """Document labels in the order the answer first cites them."""
    return list(dict.fromkeys(_DOCUMENT_TAG.findall(text)))


def _documents(answer: RagAnswer) -> dict[str, Source]:
    """One source per document label (the retrieval returns a row per passage)."""
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
    """The answer as a WhatsApp message: WhatsApp's *bold*, numbered citations, and the sources listed."""
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
    if any(figure["cited"] for figure in answer["figures"]):
        parts.append(LIVE_DATA_NOTE)
    return "\n\n".join(parts)


def _fit(body: str, room: int) -> str:
    """The body cut to the room left, at a sentence end where one falls in the second half."""
    if len(body) <= room:
        return body
    cut = body[:room]
    sentence_end = cut.rfind(". ")
    if sentence_end > room // 2:
        return cut[: sentence_end + 1]
    return cut[: room - 3].rsplit(" ", 1)[0] + "..."


def _sms_source(answer: RagAnswer) -> str:
    order = _cited_order(answer["answer"])
    documents = _documents(answer)
    if order and order[0] in documents:
        return f" Source: {_describe(documents[order[0]], SMS_TITLE_MAX)}."
    return " Source: Nokware live report data." if any(f["cited"] for f in answer["figures"]) else ""


def for_sms(answer: RagAnswer, site: str) -> str:
    """The answer as one SMS of at most two pages, plain GSM-7: its first point and one source."""
    if answer["status"] == "no_information":
        return plain(f"Nokware: {NO_INFO_ANSWER} More at {site}/ask")
    flat = _ANY_TAG.sub("", answer["answer"])
    flat = plain(" ".join(_HEADING.sub("", _BOLD.sub(r"\1", _BULLET.sub(r"\1", flat))).replace("*", "").split()))
    prefix = "" if flat.startswith("Nokware") else "Nokware: "  # the sender ID may not say Nokware
    suffix = plain(_sms_source(answer))
    room = SMS_PAGES * 153 - len(prefix) - len(suffix)
    message = f"{prefix}{_fit(flat, room)}{suffix}"
    while pages(message) > SMS_PAGES:  # extended characters take two places: trim until it fits
        room -= 10
        message = f"{prefix}{_fit(flat, room)}{suffix}"
    return message
