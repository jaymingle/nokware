"""Every match the publishing record's rules make, for a person to confirm before the page is relied on.

    backend/.venv/bin/python backend/scripts/publishing_record_matches.py

A free read of the Ledger. For each required document and period it prints what
counts as the document itself (held), what counts only as related, and anything
held without a year. A wrong match is corrected in app/data/statutory_documents.json
under "confirmed": the document's ID mapped to [requirement, year], or to null to
set it aside.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.ledger_documents import utc_now
from app.services.publishing_record import build, published_documents
from app.services.vectorstore import first_chunks


def main() -> None:
    quiet_sdk_deprecation_warnings()
    record = build(published_documents(), utc_now(), first_chunks())
    for group in record["groups"]:
        print(f"\n=== {group['name']}")
        for requirement in group["requirements"]:
            by = f"  (issued by {requirement['issued_by']})" if requirement["issued_by"] else ""
            print(f"\n{requirement['name']}{by}")
            for period in requirement["periods"]:
                print(f"  {period['label']:12} {period['state'].upper()}")
                for kind in ("documents", "related"):
                    for doc in period[kind]:
                        by = f" (year from {doc['year_source']})" if doc["year_source"] != "title" else ""
                        print(f"      {'held   ' if kind == 'documents' else 'related'}  {doc['title'][:70]}{by}  [{doc['id']}]")
                        if doc["note"]:
                            print(f"               {doc['note']}")
            for doc in requirement["undated"] + requirement["held"]:
                print(f"  {'no year' if requirement['undated'] else 'held':12} {doc['title'][:80]}  [{doc['id']}]")
    print("\nSummary:", record["summary"])


if __name__ == "__main__":
    main()
