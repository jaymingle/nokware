"""Charting a document's figures: every bar is proved against a cited passage, or nothing is drawn."""

import pytest

from app.services import ask_document_charts as documents
from app.services.ask_document_charts import _Extracted, _Pair, verified

FEES = """
2026 Fee-Fixing Resolution
31st December Market
Stores - A: 800.00
Stores - B: 200.00
Stores - C: 150.00
Outer Stalls (Open Stall): 30.00
"""
# A table flattened by pypdf: each row carries last year's fee and this year's, and a row can lose its column.
TWO_COLUMNS = """
Market fees 2025 2026
Stores - A 750.00 800.00
Stores - B 180.00 200.00
"""


def extracted(pairs: list[tuple[str, str]], chartable: bool = True, title: str = "Market stall fees, 2026 (GHS)") -> _Extracted:
    return _Extracted(chartable=chartable, title=title, pairs=[_Pair(label=label, value=value) for label, value in pairs])


def test_pairs_written_that_way_in_a_passage_are_charted() -> None:
    plotted = verified(extracted([("Stores - A", "800.00"), ("Stores - B", "200.00"), ("Stores - C", "150.00")]), [FEES])
    assert plotted is not None
    assert plotted.title == "Market stall fees, 2026 (GHS)"
    assert plotted.pairs == [("Stores - A", "800.00", 800.0), ("Stores - B", "200.00", 200.0), ("Stores - C", "150.00", 150.0)]


@pytest.mark.parametrize(("pairs", "passage", "why"), [
    ([("Stores - A", "800.00"), ("Stores - B", "250.00")], FEES, "a figure the passage doesn't give"),
    ([("Stores - A", "800.00"), ("Stores - B", "200.00")], TWO_COLUMNS, "a row whose column can't be told apart"),
    ([("Stores - A", "800.00"), ("Stores - Z", "150.00")], FEES, "a label the passage doesn't carry"),
    ([("Stores - A", "800.00")], FEES, "one bar is not a chart"),
    ([("Stores - A", "800.00"), ("Stores - A", "200.00")], FEES, "the same label twice"),
    ([("Stores - A", "eight hundred"), ("Stores - B", "200.00")], FEES, "a figure that isn't a number"),
])
def test_nothing_is_drawn_when_a_pair_cannot_be_proved(pairs: list[tuple[str, str]], passage: str, why: str) -> None:
    assert verified(extracted(pairs), [passage]) is None, why


def test_a_year_in_brackets_or_a_percentage_is_not_the_figure() -> None:
    passage = "Stores - A: 800.00 (2026), up 6.5%\nStores - B: 200.00 (2026), up 5%"
    plotted = verified(extracted([("Stores - A", "800.00"), ("Stores - B", "200.00")]), [passage])
    assert plotted is not None and [value for _, _, value in plotted.pairs] == [800.0, 200.0]


def test_thousands_separators_match_the_passage_either_way() -> None:
    passage = "CAT A - Mall (Large): 7,875.00\nCAT B - Mall (Small): 5250.00"
    plotted = verified(extracted([("CAT A - Mall (Large)", "7,875.00"), ("CAT B - Mall (Small)", "5,250.00")]), [passage])
    assert plotted is not None and [value for _, _, value in plotted.pairs] == [7875.0, 5250.0]


MARKETS = """
31st December Market
Stores - A                  800.00
Stores - B                  200.00
Ashiedu Keteke Central Market (Agbogbloshie)
Stores - A                  110.00
Stores - B                   90.00
"""


def test_a_label_the_answer_qualifies_is_tied_to_its_row_under_its_heading() -> None:
    """A fees answer names the market; the passage writes it as a heading above the row."""
    pairs = [("31st December Market Stores - A", "800.00"), ("31st December Market Stores - B", "200.00")]
    plotted = verified(extracted(pairs), [MARKETS])
    assert plotted is not None and [value for _, _, value in plotted.pairs] == [800.0, 200.0]
    other = [("Ashiedu Keteke Central Market (Agbogbloshie) Stores - A", "110.00"),
             ("Ashiedu Keteke Central Market (Agbogbloshie) Stores - B", "90.00")]
    assert [v for _, _, v in verified(extracted(other), [MARKETS]).pairs] == [110.0, 90.0]


def test_a_figure_from_another_heading_is_not_that_headings_figure() -> None:
    """800.00 is written under 31st December Market, so it is not Ashiedu Keteke's."""
    pairs = [("Ashiedu Keteke Central Market (Agbogbloshie) Stores - A", "800.00"),
             ("Ashiedu Keteke Central Market (Agbogbloshie) Stores - B", "90.00")]
    assert verified(extracted(pairs), [MARKETS]) is None


def test_a_number_in_a_name_is_not_the_figure() -> None:
    """"Chop Bars 1-6" carries numbers in its name; the fee is still the only amount on the row."""
    passage = "31st December Market\nChop Bars 1-6 40.00\nChop Bar 16-20,34-40 60.00"
    plotted = verified(extracted([("Chop Bars 1-6", "40.00"), ("Chop Bar 16-20,34-40", "60.00")]), [passage])
    assert plotted is not None and [value for _, _, value in plotted.pairs] == [40.0, 60.0]


def test_the_model_refusing_means_no_chart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(documents, "_extract", lambda question, answer, passages: None)
    assert documents.figures_to_chart("chart the fees", "Stores A cost 800.00 [S1].", [FEES]) is None


def test_a_reading_that_fails_is_no_chart_not_a_failed_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def with_structured_output(self, schema: type) -> "Broken":
            return self

        def invoke(self, prompt: str) -> None:
            raise TimeoutError("the model timed out")

    monkeypatch.setattr(documents, "get_quick_model", Broken)
    assert documents.figures_to_chart("chart the fees", "Stores A cost 800.00 [S1].", [FEES]) is None
