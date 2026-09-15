"""SMS text: the GSM-7 alphabet and pages, so a message costs what we expect.

In GSM-7 a message takes 160 characters on one page and 153 a page beyond that.
A single character outside it (a curly apostrophe, "·", an emoji) sends the
whole message as UCS-2 instead: 70 characters on one page, 67 beyond. Arkesel
charges a credit a page, so text is made plain before it is sent.
"""

import math

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


def plain(text: str) -> str:
    """Typographic punctuation as its GSM-7 equivalent: the same words, a third of the cost."""
    return text.translate(_PLAIN)


def is_gsm7(text: str) -> bool:
    return all(c in GSM7_BASIC or c in GSM7_EXTENDED for c in text)


def pages(text: str) -> int:
    """How many SMS pages (Arkesel credits) the text takes."""
    if is_gsm7(text):
        length = len(text) + sum(c in GSM7_EXTENDED for c in text)
        page, part = GSM_PAGE, GSM_PART
    else:
        length = len(text.encode("utf-16-le")) // 2  # an emoji takes two UCS-2 units
        page, part = UCS2_PAGE, UCS2_PART
    return 1 if length <= page else math.ceil(length / part)


def bare_address(url: str) -> str:
    """A site address for a message, without "https://": eight characters saved, and phones still make it a link."""
    return url.split("://", 1)[-1].rstrip("/")
