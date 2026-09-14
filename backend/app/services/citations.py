"""Label-based citations for Ask.

The model never sees document ids. Each retrieved document is shown under a
short label ([S1], [S2], ...), each live report figure under an R label ([R1],
...), and the model cites those labels. Afterwards,
sanitize_citations() keeps only labels that map to a retrieved document or figure and
deletes every other citation outright: an unknown label is never guessed at,
repaired, or matched to the nearest real one. A premise of verifiable sourcing
cannot survive a single fabricated citation.
"""

import re

LABEL_PREFIX = "S"

# One citation group: [S1], [S1, S3], [S1; S2], [S1 and S2], (S2), [s 4], [Sources S1, S2], [R1], [S2][R1] ...
_CITATION_GROUP = re.compile(
    r"[\[(]\s*(?:sources?\s*)?([SR]\s*\d+(?:\s*(?:,|;|&|and)\s*[SR]\s*\d+)*)\s*[\])]",
    re.IGNORECASE,
)
_LABEL = re.compile(r"([SR])\s*(\d+)", re.IGNORECASE)
# Raw document ids never appear in the prompt; strip any that show up anyway.
_DOCUMENT_ID = re.compile(r"\bama-[0-9a-f]{6,}\b", re.IGNORECASE)
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([.,;:!?])")
_REPEATED_SPACES = re.compile(r"(?<=\S)[ \t]{2,}")  # mid-line only: keeps list indentation


def make_label(position: int) -> str:
    """Label for the document at 1-based position in the retrieval ranking."""
    return f"{LABEL_PREFIX}{position}"


def sanitize_citations(answer: str, valid_labels: set[str]) -> tuple[str, set[str]]:
    """Return (answer with only valid citations, labels actually cited).

    Every citation group is rewritten to its valid labels in canonical form
    ([S1][S3]); a group with no valid label disappears entirely.
    """
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
