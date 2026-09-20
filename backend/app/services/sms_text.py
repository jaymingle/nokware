"""SMS text: the GSM-7 alphabet and pages, so a message costs what we expect.

In GSM-7 a message takes 160 characters on one page and 153 a page beyond that.
A single character outside it (a curly apostrophe, "·", an emoji) sends the
whole message as UCS-2 instead: 70 characters on one page, 67 beyond. Arkesel
charges a credit a page, so text is made plain before it is sent.
"""

import math
import re

GSM7_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = frozenset("^{}\\[~]|€\f")  # each takes the room of two characters
GSM_PAGE, GSM_PART = 160, 153
UCS2_PAGE, UCS2_PART = 70, 67

_PLAIN = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
    "…": "...", "·": "-", " ": " ", "•": "-",
})


# One cedi sign sends a whole budget answer as UCS-2, at less than half the words a page: GHS is the same amount.
_CEDI = re.compile(r"(?:GH)?\s*[¢₵]\s*(\d?)")


def plain(text: str) -> str:
    """Typographic punctuation and the cedi sign as their GSM-7 equivalents: the same words, a third of the cost."""
    return _CEDI.sub(lambda match: f"GHS {match[1]}" if match[1] else "GHS", text.translate(_PLAIN))


def is_gsm7(text: str) -> bool:
    return all(c in GSM7_BASIC or c in GSM7_EXTENDED for c in text)


def cost(text: str) -> int:
    """The places the text takes on a page: an extended GSM-7 character, like an emoji in UCS-2, takes two."""
    if is_gsm7(text):
        return len(text) + sum(c in GSM7_EXTENDED for c in text)
    return len(text.encode("utf-16-le")) // 2


def part_room(text: str) -> int:
    """How much one page of a multipart message holds, in the alphabet this text forces."""
    return GSM_PART if is_gsm7(text) else UCS2_PART


def pages(text: str) -> int:
    """How many SMS pages (Arkesel credits) the text takes."""
    page, part = (GSM_PAGE, GSM_PART) if is_gsm7(text) else (UCS2_PAGE, UCS2_PART)
    length = cost(text)
    return 1 if length <= page else math.ceil(length / part)


def bare_address(url: str) -> str:
    """A site address for a message, without "https://": eight characters saved, and phones still make it a link."""
    return url.split("://", 1)[-1].rstrip("/")
