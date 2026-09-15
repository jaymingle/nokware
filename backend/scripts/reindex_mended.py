"""Re-index the Ledger documents whose stored chunks still carry what PDF fonts left behind.

Some PDFs' text came out with "fi" and "fl" as private characters ("\uf002ooding"), font bullets and lost
characters (see app/services/pdf_text.py). Ingestion now mends them; this re-ingests each document stored before
that, through the normal path (download, extract, mend, chunk, embed, replace its chunks atomically), so keyword
search finds "flooding" and embeddings see the words.

A dry run by default: it lists the documents, their chunks and the embedding cost, and changes nothing. Pass
--yes to re-index. Safe to re-run: a document already mended is no longer selected.

    backend/.venv/bin/python backend/scripts/reindex_mended.py          # dry run
    backend/.venv/bin/python backend/scripts/reindex_mended.py --yes    # re-index

Exits 0 when every document was re-indexed, 1 on any failure.
"""

import argparse
import sys
import time

from app.services import ledger_documents
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.ingestion import IngestionRefused, ingest_document
from app.services.vectorstore import CONTENT_COLUMN, DOCUMENT_ID_COLUMN, TABLE_NAME, connect

# What pdf_text.mend() replaces: private-use characters, U+FFFD and the presentation ligatures.
_UNMENDED = "[\ue000-\uf8ff\ufffd\ufb00-\ufb06]"
PRICE_PER_MILLION_TOKENS = 0.20  # gemini-embedding-2, text input, Gemini API list price (September 2026)
CHARS_PER_TOKEN = 4  # English prose; figures and tables run nearer 3, so the estimate is given as a range


def unmended() -> list[tuple[str, int, int, int]]:
    """Each document with unmended chunks: (id, unmended chunks, all its chunks, all its characters)."""
    sql = f"""
        SELECT "{DOCUMENT_ID_COLUMN}", count(*) FILTER (WHERE "{CONTENT_COLUMN}" ~ %(pattern)s),
               count(*), sum(length("{CONTENT_COLUMN}"))
        FROM "{TABLE_NAME}" GROUP BY 1
        HAVING count(*) FILTER (WHERE "{CONTENT_COLUMN}" ~ %(pattern)s) > 0 ORDER BY 1"""
    with connect() as conn:
        return [(d, int(u), int(n), int(c)) for d, u, n, c in conn.execute(sql, {"pattern": _UNMENDED}).fetchall()]


def _dollars(tokens: float) -> str:
    return f"${tokens / 1_000_000 * PRICE_PER_MILLION_TOKENS:.2f}"


def estimate(characters: int) -> str:
    low, high = characters / CHARS_PER_TOKEN, characters / (CHARS_PER_TOKEN - 1)
    return f"about {low / 1000:,.0f}k-{high / 1000:,.0f}k tokens, {_dollars(low)}-{_dollars(high)} to embed"


def reindex(documents: list[tuple[str, int, int, int]], titles: dict[str, str]) -> int:
    failed = 0
    for number, (document_id, _, before, _) in enumerate(documents, 1):
        started = time.monotonic()
        try:
            after = ingest_document(document_id).chunk_count
            print(f"[{number}/{len(documents)}] {titles[document_id][:60]}: {before} -> {after} chunks "
                  f"({time.monotonic() - started:.0f}s)")
        except IngestionRefused as refused:
            print(f"[{number}/{len(documents)}] skipped: {refused}")
        except Exception as exc:  # recorded on the document by ingest_document; carry on with the rest
            failed += 1
            print(f"[{number}/{len(documents)}] FAILED {document_id}: {type(exc).__name__}: {exc}")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-index Ledger documents whose chunks carry unmended PDF characters.")
    parser.add_argument("--yes", action="store_true", help="actually re-index (default: dry run)")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    documents = unmended()
    records = ledger_documents.get_documents(d for d, *_ in documents)
    titles = {d: (records.get(d) or {}).get("title") or d for d, *_ in documents}
    for document_id, broken, chunks, _ in documents:
        print(f"{document_id}  {broken:>4} of {chunks:>4} chunks unmended  {titles[document_id][:70]}")
    characters = sum(c for *_, c in documents)
    print(f"{len(documents)} document(s), {sum(b for _, b, _, _ in documents)} unmended chunk(s) of "
          f"{sum(n for _, _, n, _ in documents)}; re-embedding {characters:,} characters is {estimate(characters)}.")
    if not args.yes:
        print("Dry run: nothing changed. Re-run with --yes to re-index.")
        return 0
    started = time.monotonic()
    failed = reindex(documents, titles)
    left = unmended()
    print(f"Done in {(time.monotonic() - started) / 60:.1f} min: {failed} failed; "
          f"{sum(b for _, b, _, _ in left)} unmended chunk(s) left in {len(left)} document(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
