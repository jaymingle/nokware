"""documentYear rules: a title's year range gives its first year."""

from app.services.ledger_documents import year_from_title
from import_ama_docs import document_year


def test_year_from_title_takes_first_year_of_a_range() -> None:
    assert year_from_title("MEDIUM TERM DEVELOPMENT PLAN, 2026-2029") == 2026
    assert year_from_title("Accra Road Safety Report, 2024") == 2024
    assert year_from_title("A Climate Commitment: A Pathway to Net Zero by 2050") is None
    assert year_from_title("Service Charter") is None


def test_import_document_year_only_falls_back_when_manifest_year_is_rejected() -> None:
    assert document_year("2029", "MEDIUM TERM DEVELOPMENT PLAN, 2026-2029") == 2026
    assert document_year("2024", "Road Safety Trends 2020-2024") == 2024  # plausible manifest year kept
    assert document_year("undated", "Service Charter") is None
    assert document_year("2050", "A Climate Commitment: A Pathway to Net Zero by 2050") is None
