"""Things nobody publishes at all: a finding that names every source it checked, and can be repeated."""

from dataclasses import asdict

from app.schemas.accountability import UnpublishedData
from app.services import unpublished_data


def test_the_missing_electoral_area_boundaries_are_a_finding_in_their_own_right() -> None:
    """The map of Accra's areas draws tiles rather than shapes because of this; the record says why."""
    found = {finding.id: finding for finding in unpublished_data.findings()}
    boundaries = found["electoral-area-boundaries"]
    assert boundaries.headline and boundaries.subject.lower() not in boundaries.headline.lower().split(".")[0][:1]
    assert "20 electoral areas" in boundaries.headline


def test_a_finding_writes_its_own_sentence_rather_than_composing_one() -> None:
    """The same rule as the reporting gaps: a headline is written out, never spliced from a label."""
    for finding in unpublished_data.findings():
        assert "{" not in finding.headline and "}" not in finding.headline
        assert finding.headline[0].isupper() and finding.headline == finding.headline.strip()


def test_every_source_checked_is_named_with_what_it_holds_instead() -> None:
    """A reader has to be able to repeat the search, not take the absence on trust."""
    for finding in unpublished_data.findings():
        assert len(finding.checked) >= 3
        for source in finding.checked:
            assert source.name and source.holds
            assert source.url.startswith("https://")
        assert finding.checked_on and finding.instead


def test_a_finding_carries_the_wording_to_request_it() -> None:
    for finding in unpublished_data.findings():
        assert finding.rti_document and finding.rti_period
        assert not finding.rti_document[0].isupper()  # it is slotted into a sentence, so it starts lower case


def test_the_schema_carries_every_field_a_finding_has() -> None:
    """The route is exercised in test_accountability, where the Ledger it also serves is stubbed."""
    finding = UnpublishedData.model_validate(asdict(unpublished_data.findings()[0]))
    assert finding.checked and finding.checked[0].name and finding.rti_document
