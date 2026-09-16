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


# A report writes the figure before the thing it is for, and wraps mid-sentence. From AMA's 2023 Assembly
# minutes, which is where the refusal that prompted this was seen.
PROSE = """
the Assembly. In relation to the revenue performance for 2023 (up to the end of
August), the Assembly had mobilised 48.3 percent of its IGF budget, 19.0 percent
of its revenue from the Central Government and 10.03 percent from Donor  Funds.
Therefore, the Assembly had mobilised 31.9 percent of its total  budgeted revenue
for 2023 (up to the end of August).
"""


def test_a_report_that_writes_the_figure_before_its_label_is_charted() -> None:
    """"48.3 percent of its IGF budget" is as much a label and a figure as "Stores - A 800.00"."""
    plotted = verified(extracted([("IGF budget", "48.3"), ("Central Government", "19.0"), ("Donor Funds", "10.03")]), [PROSE])
    assert plotted is not None
    assert [value for _, _, value in plotted.pairs] == [48.3, 19.0, 10.03]


def test_a_label_tied_to_the_next_items_figure_is_refused() -> None:
    """Prose that reads correctly backwards also reads forwards, shifted by one, and every pair would tie.
    What tells them apart is the comma between one item and the next."""
    assert verified(extracted([("IGF budget", "19.0"), ("Central Government", "10.03")]), [PROSE]) is None


def test_a_figure_on_the_line_above_its_label_is_still_its_sentence_s() -> None:
    """"19.0 percent" ends one line and "the Central Government" begins the next: a sentence is prose's row."""
    plotted = verified(extracted([("IGF budget", "48.3"), ("Central Government", "19.0")]), [PROSE])
    assert plotted is not None and [value for _, _, value in plotted.pairs] == [48.3, 19.0]


def test_a_total_is_not_drawn_beside_its_own_parts() -> None:
    """A total is by definition the largest bar, so among its parts it reads as one of them and the biggest."""
    plotted = verified(extracted([("IGF budget", "48.3"), ("Central Government", "19.0"), ("Donor Funds", "10.03"),
                                  ("total budgeted revenue", "31.9")]), [PROSE])
    assert plotted is not None
    assert [label for label, _, _ in plotted.pairs] == ["IGF budget", "Central Government", "Donor Funds"]
    assert plotted.left_out == ("total budgeted revenue (31.9)",)  # still proved, and named in the chart's note


def test_a_total_with_one_part_left_is_no_chart() -> None:
    assert verified(extracted([("IGF budget", "48.3"), ("total budgeted revenue", "31.9")]), [PROSE]) is None


def test_totals_compared_with_each_other_are_charted() -> None:
    """Two totals side by side are peers; only a total among its own parts misleads."""
    passage = "Total revenue 2022: 36,500,000.00\nTotal revenue 2026: 124,760,805.00"
    plotted = verified(extracted([("Total revenue 2022", "36,500,000.00"), ("Total revenue 2026", "124,760,805.00")]), [passage])
    assert plotted is not None and plotted.left_out == ()


def test_the_chart_says_which_total_it_left_out() -> None:
    from app.services.ask_charts import document_chart
    from app.services.ask_document_charts import Plotted

    chart = document_chart("Show it as a chart", Plotted("Revenue mobilised", [("IGF", "48.3", 48.3), ("Donor Funds", "10.03", 10.03)],
                                                         left_out=("total budgeted revenue (31.9)",)))
    assert chart["categories"] == ["IGF", "Donor Funds"]
    assert chart["note"].startswith("total budgeted revenue (31.9) is left out of the chart")
    assert "in the answer above" in chart["note"]


def test_one_direction_has_to_tie_the_whole_chart() -> None:
    """Otherwise "Stores - A 800 Stores - B 900" proves Stores - B costs 800, reading each pair whichever way suits."""
    table = "Stores - A 800.00 Stores - B 900.00"
    assert verified(extracted([("Stores - A", "800.00"), ("Stores - B", "800.00")]), [table]) is None
    assert verified(extracted([("Stores - A", "800.00"), ("Stores - B", "900.00")]), [table]) is not None


def test_a_value_copied_with_its_currency_is_still_a_number() -> None:
    """The model copies the figure as the passage writes it, and the passage writes the unit with it."""
    passage = "Stores - A: GH¢ 800.00\nStores - B: GH¢ 200.00"
    plotted = verified(extracted([("Stores - A", "GH¢ 800.00"), ("Stores - B", "GH¢ 200.00")]), [passage])
    assert plotted is not None and [value for _, _, value in plotted.pairs] == [800.0, 200.0]
