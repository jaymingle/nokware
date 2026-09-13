"""Edition preference and near-duplicate collapse used by retrieval."""

from app.services.retrieval import (
    Chunk,
    RetrievedChunk,
    apply_edition_preference,
    collapse_near_duplicates,
    question_years,
    series_key,
)

PROCEDURE = (
    "Procedure in Applying and Processing Requests. Section 18 of the RTI Act provides "
    "specific guidelines for applying. Applications must be made in writing or by using "
    "the standard RTI application form, submitted electronically or in person to the "
    "Information Unit of the Assembly, stating the date of the application. {year} Manual"
)


def candidate(doc_id: str, title: str, year: int | None, score: float, text: str | None = None) -> RetrievedChunk:
    chunk = Chunk(chunk_id=hash(doc_id) % 10_000, document_id=doc_id, chunk_index=0, text=text or f"{title} body")
    return RetrievedChunk(chunk=chunk, score=score, document={"title": title, "documentYear": year})


def ids(chunks: list[RetrievedChunk]) -> list[str]:
    return [c.chunk.document_id for c in chunks]


def test_series_key_ignores_years_and_case() -> None:
    assert series_key("RIGHT TO INFORMATION MANUAL 2024") == series_key("Right to Information Manual")
    assert series_key("2023 MONITORING AND EVALUATION REPORT") == "monitoring and evaluation report"


def test_question_years() -> None:
    assert question_years("How much revenue did AMA collect in 2023?") == {2023}
    assert question_years("Compare the 2022 and 2024 budgets") == {2022, 2024}
    assert question_years("Who collects waste?") == set()


def test_newest_edition_preferred_when_no_year_asked() -> None:
    older = candidate("rti-2024", "RTI Manual 2024", 2024, score=1.0)
    newest = candidate("rti-2025", "RTI Manual 2025", 2025, score=0.9)
    unrelated = candidate("roads", "Accra Road Safety Report", 2024, score=0.7)
    ranked = apply_edition_preference([older, newest, unrelated], asked_years=set())
    assert ids(ranked) == ["rti-2025", "roads", "rti-2024"]


def test_asked_year_edition_preferred_so_history_stays_retrievable() -> None:
    older = candidate("rti-2022", "Right to Information Manual", 2022, score=0.6)
    newest = candidate("rti-2025", "RIGHT TO INFORMATION MANUAL 2025", 2025, score=1.0)
    ranked = apply_edition_preference([newest, older], asked_years={2022})
    assert ids(ranked)[0] == "rti-2022"


def test_asked_year_without_matching_edition_falls_back_to_newest() -> None:
    older = candidate("fees-2024", "Fee-Fixing Resolution 2024", 2024, score=1.0)
    newest = candidate("fees-2026", "Fee-Fixing Resolution 2026", 2026, score=0.9)
    ranked = apply_edition_preference([older, newest], asked_years={2019})
    assert ids(ranked)[0] == "fees-2026"


def test_unknown_year_edition_ranks_as_older() -> None:
    undated = candidate("rti-undated", "RTI Manual", None, score=1.0)
    dated = candidate("rti-2025", "RTI Manual 2025", 2025, score=0.8)
    assert ids(apply_edition_preference([undated, dated], asked_years=set()))[0] == "rti-2025"


def test_near_duplicates_collapse_to_preferred_edition() -> None:
    editions = [
        candidate(f"rti-{year}", f"RTI Manual {year}", year, score=1.0 - 0.1 * i, text=PROCEDURE.format(year=year))
        for i, year in enumerate([2023, 2024, 2025])
    ]
    distinct = candidate("fees", "RTI fees", 2025, score=0.5, text="Fees and charges: photocopies cost GHS 1 per page.")
    no_year = collapse_near_duplicates(apply_edition_preference([*editions, distinct], asked_years=set()))
    assert ids(no_year) == ["rti-2025", "fees"]
    asked_2023 = collapse_near_duplicates(apply_edition_preference([*editions, distinct], asked_years={2023}))
    assert ids(asked_2023)[0] == "rti-2023"
    assert "rti-2024" not in ids(asked_2023) and "rti-2025" not in ids(asked_2023)
