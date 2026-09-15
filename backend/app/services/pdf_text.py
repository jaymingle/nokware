"""Text extracted from a PDF, mended: what some fonts leave behind, spelled out as the words they stand for.

Some PDFs set "fi" and "fl" as a single glyph that their font maps to a private character (U+F001, U+F002), so the
extracted text reads "\uf002ooding" and no search for "flooding" finds it. Symbol and Wingdings bullets arrive as
private characters too (U+F0B7 and neighbours), and a glyph with no Unicode mapping at all arrives as U+FFFD: in
the Ledger, one document's full stops, including its table-of-contents dot leaders.

What can be known is restored; what can't is not guessed. A ligature becomes its letters, a font bullet becomes
"•", and a lost character becomes a space: never a guessed full stop (right in that document, wrong in the next),
and never nothing, which would run "3.1" together as "31".
"""

import re
import unicodedata

_PRIVATE_LIGATURES = {"\uf001": "fi", "\uf002": "fl"}
_PRESENTATION_LIGATURES = re.compile("[\ufb00-\ufb06]")  # ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ, which NFKC spells out
_FONT_BULLETS = re.compile("[\uf020-\uf0ff]")  # Symbol and Wingdings bullets, arrows and ticks
_LOST = re.compile("[\ue000-\uf8ff\ufffd]+")  # anything else private, and characters extraction lost


def mend(text: str) -> str:
    """Ligatures spelled out, font bullets as bullets, and any run of lost characters as one space."""
    for private, letters in _PRIVATE_LIGATURES.items():
        text = text.replace(private, letters)
    text = _PRESENTATION_LIGATURES.sub(lambda m: unicodedata.normalize("NFKC", m[0]), text)
    return _LOST.sub(" ", _FONT_BULLETS.sub("•", text))


def needs_mending(text: str) -> bool:
    """Whether stored text still carries what mend() replaces: the chunks the re-index script looks for."""
    return mend(text) != text
