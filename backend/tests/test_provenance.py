"""How a document entered the Ledger, as Ask states it."""

from app.services.ledger_documents import Provenance, provenance


def test_provenance_distinguishes_all_three_origins_and_never_guesses() -> None:
    assert provenance({"sourceType": "agency", "origin": "ama_website"}) == Provenance.AMA_WEBSITE
    assert provenance({"sourceType": "agency", "origin": "portal"}) == Provenance.DEPARTMENT_PORTAL
    assert provenance({"sourceType": "contributor", "origin": "portal"}) == Provenance.CONTRIBUTOR
    assert provenance({"sourceType": "agency"}) is None  # no origin recorded: say nothing rather than guess
