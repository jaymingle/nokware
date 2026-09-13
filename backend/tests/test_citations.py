"""The citation guarantee: every label left in an answer maps to a retrieved source.

Unknown labels are deleted outright, never guessed at or repaired.
"""

import re

import pytest

from app.services.citations import make_label, sanitize_citations
from app.services.rag import NO_INFO_ANSWER

VALID = {"S1", "S2", "S3"}


@pytest.mark.parametrize(
    ("raw", "expected", "cited"),
    [
        ("Fees rose [S1].", "Fees rose [S1].", {"S1"}),
        ("Fees rose [S9].", "Fees rose.", set()),
        ("Fees rose [S1, S9, S2].", "Fees rose [S1][S2].", {"S1", "S2"}),
        ("Fees rose (s1) and fell [S 3].", "Fees rose [S1] and fell [S3].", {"S1", "S3"}),
        ("See [Sources S1; S2].", "See [S1][S2].", {"S1", "S2"}),
        ("Roads (S1 and S9) flooded.", "Roads [S1] flooded.", {"S1"}),
        ("[S7] Only an invalid label.", "Only an invalid label.", set()),
        ("Per ama-641be9d85874c34e3db672f7f0e02baa the fee is 50 [S2].", "Per the fee is 50 [S2].", {"S2"}),
        (NO_INFO_ANSWER, NO_INFO_ANSWER, set()),
        ("Unrelated (see section 5) text.", "Unrelated (see section 5) text.", set()),
    ],
)
def test_sanitize_citations(raw: str, expected: str, cited: set[str]) -> None:
    assert sanitize_citations(raw, VALID) == (expected, cited)


def test_only_valid_labels_survive() -> None:
    raw = "A [S1]. B [S4][S2]. C (S0). D [S12, S3]. E [S2; S5]. F [s99]."
    answer, cited = sanitize_citations(raw, VALID)
    remaining = set(re.findall(r"S\d+", answer))
    assert remaining == {"S1", "S2", "S3"}
    assert remaining <= VALID and cited == remaining
    assert "[]" not in answer and "()" not in answer


def test_no_valid_labels_at_all_removes_every_citation() -> None:
    answer, cited = sanitize_citations("Budget [S1]. Revenue [S2].", valid_labels=set())
    assert answer == "Budget. Revenue."
    assert cited == set()


def test_list_indentation_is_kept() -> None:
    raw = "- point one [S1]\n    - nested point [S2]"
    assert sanitize_citations(raw, VALID)[0] == raw


def test_make_label() -> None:
    assert [make_label(n) for n in (1, 2, 10)] == ["S1", "S2", "S10"]
