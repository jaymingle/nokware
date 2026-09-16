"""Read the Assembly's budget documents into app/data/budget_lines.json, keeping only what proves itself.

    .venv/bin/python scripts/extract_budget_lines.py            what it would take, without writing
    .venv/bin/python scripts/extract_budget_lines.py --write    write the data file

Every published document is checked for the PBB "Budget Details by Chart of
Account" pages. Each block must add up to the fund-source total it states, and a
document is taken only if nearly all of its blocks do (budget_extract.py). Each
document's own "Total Cost Centre" lines give a second, independent check: the
rows kept are reported as a share of what the document says it details, so nobody
has to take the coverage on trust.

The rows are small (a few hundred) and never change once a document is published,
so they live in the repository beside the code, not in a database: what Nokware
publishes about a budget is reviewable in a diff.
"""

import io
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pdfplumber
from appwrite.query import Query

from app.services.appwrite_client import every_record
from app.services.budget_extract import MIN_VERIFIED, Extracted, read_pdf
from app.services.storage import download_ledger_file

DATA = Path(__file__).resolve().parents[1] / "app" / "data" / "budget_lines.json"
COST_CENTRE = re.compile(r"Total Cost Centre\s+([\d,]+(?:\.\d{2})?)")
ABOUT = ("Approved budget figures read from the Accra Metropolitan Assembly's programme-based budget documents "
         "(scripts/extract_budget_lines.py). Each row is one sub-programme's approved amount for one department and "
         "fund source, as the document prints it: nothing here is added up, converted or inferred. A block of the "
         "document is kept only where its rows add up to the fund-source total it states, and a document only where "
         f"at least {MIN_VERIFIED:.0%} of its blocks do. 'coverage' is what the kept rows come to as a share of the "
         "document's own Total Cost Centre lines, so what was left out is visible. One budget stands for each year, the "
         "latest revision of it; the others are named under 'set_aside'. These are approved amounts: released and "
         "actual spending are not in these documents.")


def stated_total(data: bytes) -> float:
    """What the document itself says it details: the sum of its Total Cost Centre lines."""
    total = 0.0
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            total += sum(float(found.replace(",", "")) for found in COST_CENTRE.findall(page.extract_text() or ""))
    return total


def budget_documents() -> list[dict[str, Any]]:
    published = every_record("ledger_documents", [Query.equal("status", "published")])
    return [record for record in published if "budget" in (record.get("title") or "").lower()]


def summarise(record: dict[str, Any], found: Extracted, stated: float) -> dict[str, Any]:
    kept = sum(row.amount for row in found.rows)
    return {
        "document_id": found.document_id,
        "title": record.get("title"),
        "year": found.rows[0].year if found.rows else record.get("documentYear"),
        "blocks": found.blocks,
        "verified_blocks": found.verified_blocks,
        "rows": len(found.rows),
        "kept": round(kept, 2),
        "stated": round(stated, 2),
        "coverage": round(kept / stated, 4) if stated else 0.0,
    }


def standing(title: str) -> int:
    """A revised budget supersedes the original it revises; the original supersedes anything else that year."""
    lowered = title.lower()
    return 2 if "revised" in lowered else 1 if "composite" in lowered or "ama budget" in lowered else 0


def main() -> None:
    write = "--write" in sys.argv
    read: list[tuple[dict[str, Any], Extracted]] = []
    for record in budget_documents():
        data = download_ledger_file(record["fileId"])
        found = read_pdf(data, record["$id"])
        if not found.blocks:
            continue
        summary = summarise(record, found, stated_total(data))
        mark = "read" if found.publishable else "LEFT OUT (blocks don't reconcile)"
        print(f"{mark:34} {summary['year']} {str(record.get('title'))[:40]:40} "
              f"blocks {found.verified_blocks}/{found.blocks} ({found.share:.1%}) "
              f"rows {len(found.rows):4} coverage {summary['coverage']:.1%}")
        if found.publishable:
            read.append((summary, found))
    # One budget for each year: two documents of the same year would double it in any comparison. The 2022 revised
    # budget really does revise the original (GH¢ 40.9m against 36.5m), so the later one stands and the other is named.
    documents, rows, set_aside = [], [], []
    for year in sorted({summary["year"] for summary, _ in read}):
        same = sorted([pair for pair in read if pair[0]["year"] == year],
                      key=lambda pair: (standing(str(pair[0]["title"])), pair[0]["coverage"]), reverse=True)
        (summary, found), rest = same[0], same[1:]
        documents.append(summary)
        rows.extend(asdict(row) for row in found.rows)
        for other, _ in rest:
            set_aside.append({"document_id": other["document_id"], "title": other["title"], "year": other["year"],
                              "why": f"superseded for {year} by {summary['title']}"})
            print(f"{'set aside':34} {year} {str(other['title'])[:40]:40} superseded by {summary['title']}")
    print(f"\n{len(rows)} rows from {len(documents)} documents, {len(set_aside)} set aside")
    if write:
        DATA.write_text(json.dumps({"about": ABOUT, "documents": documents, "set_aside": set_aside, "rows": rows}, indent=1) + "\n")
        print(f"wrote {DATA}")
    else:
        print("run again with --write to save")


if __name__ == "__main__":
    main()
