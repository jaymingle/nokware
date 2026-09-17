"""Label-based citations for Ask.

The model never sees document ids, only labels. A citation to an unknown label is deleted outright, never guessed at,
repaired, or matched to the nearest real one: verifiable sourcing cannot survive a single fabricated citation.
"""

import re

LABEL_PREFIX = "S"
# S a document, R a live report count, B a budget figure. Every module that finds, strips or renumbers citations
# builds its pattern from this, so a new kind can't be missed in some of them.
KINDS = "SRB"
FIGURE_KINDS = KINDS.replace(LABEL_PREFIX, "")  # the citations that are figures, not documents: R and B

# One citation group: [S1], [S1, S3], [S1; S2], [S1 and S2], (S2), [s 4], [Sources S1, S2], [R1], [S2][R1] ...
_CITATION_GROUP = re.compile(
    rf"[\[(]\s*(?:sources?\s*)?([{KINDS}]\s*\d+(?:\s*(?:,|;|&|and)\s*[{KINDS}]\s*\d+)*)\s*[\])]",
    re.IGNORECASE,
)
_LABEL = re.compile(rf"([{KINDS}])\s*(\d+)", re.IGNORECASE)
# Raw document ids never appear in the prompt; strip any that show up anyway.
_DOCUMENT_ID = re.compile(r"\bama-[0-9a-f]{6,}\b", re.IGNORECASE)
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([.,;:!?])")
_REPEATED_SPACES = re.compile(r"(?<=\S)[ \t]{2,}")  # mid-line only: keeps list indentation


def make_label(position: int) -> str:
    return f"{LABEL_PREFIX}{position}"


def sanitize_citations(answer: str, valid_labels: set[str]) -> tuple[str, set[str]]:
    """Returns the answer with only valid citations, in canonical form ([S1][S3]), and the labels actually cited."""
    cited: set[str] = set()

    def keep_valid(match: re.Match[str]) -> str:
        labels = [f"{kind.upper()}{number}" for kind, number in _LABEL.findall(match.group(1))]
        kept = list(dict.fromkeys(label for label in labels if label in valid_labels))
        cited.update(kept)
        return "".join(f"[{label}]" for label in kept)

    text = _CITATION_GROUP.sub(keep_valid, answer)
    text = _DOCUMENT_ID.sub("", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    text = _REPEATED_SPACES.sub(" ", text)
    return text.strip(), cited
