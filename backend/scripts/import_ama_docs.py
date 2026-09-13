"""Bulk-import the AMA document archive into Nokware.

Reads <docs-dir>/manifest.json plus scripts/ama_manifest_additions.json and, for
each unique PDF: uploads it to MinIO, creates its ledger_documents record
(sourceType=agency, status=published, uploadedBy = the department's seeded
user) and ingests it (chunk, embed, write to Postgres).

Resumable: a document's Appwrite ID and MinIO object name come from its content
hash, and each step is skipped when already done (file in MinIO, record in
Appwrite, ingestedAt set). Re-running after a failure or Ctrl-C continues where
it stopped without duplicating anything. Identical PDFs listed twice are
imported once; the extra copy is reported and skipped.

    backend/.venv/bin/python backend/scripts/import_ama_docs.py [--docs-dir DIR] [--limit N] [--only TEXT]
        [--dry-run] [--refresh-metadata]

--refresh-metadata also updates manifest-derived fields (title, department,
category, source URL, year) on records that already exist, without re-ingesting.

Exits 0 when every selected document succeeded, 1 on any failure, 130 if interrupted.
"""

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.categories import categories_by_id
from app.config import get_settings, settings_error_summary
from app.services.appwrite_client import get_teams, quiet_sdk_deprecation_warnings
from app.services.ingestion import ingest_document
from app.services.ledger_documents import (
    LedgerStatus,
    Origin,
    SourceType,
    create_document,
    find_document,
    now_iso,
    plausible_year,
    update_document,
    year_from_title,
)
from app.services.storage import ledger_file_exists, upload_ledger_file
from app.teams import DEPARTMENT_TEAMS
from ama_departments import ama_department

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_DOCS_DIR = Path.home() / "nokware-docs"
ADDITIONS_FILE = SCRIPTS_DIR / "ama_manifest_additions.json"
REQUIRED_FIELDS = ("file", "title", "category_id", "department", "year", "source_url")
ID_PREFIX = "ama-"  # Appwrite IDs allow at most 36 characters: prefix + 32 hex
MOJIBAKE_MARKERS = ("â€", "Ã", "Â")  # UTF-8 text that was decoded as Windows-1252


class ManifestError(Exception):
    """The manifest is invalid; nothing has been written."""


@dataclass(frozen=True)
class Entry:
    file: str
    title: str
    category: str
    team: str
    document_year: int | None
    source_url: str
    sha256: str

    @property
    def document_id(self) -> str:
        return f"{ID_PREFIX}{self.sha256[:32]}"

    @property
    def object_name(self) -> str:
        return f"ama/{self.sha256}.pdf"

    def metadata(self) -> dict[str, Any]:
        """Fields that come from the manifest, and that --refresh-metadata keeps current."""
        return {
            "title": self.title,
            "department": self.team,
            "category": self.category,
            "sourceUrl": self.source_url,
            "documentYear": self.document_year,
        }

    def record(self, uploaded_by: str) -> dict[str, Any]:
        return {
            **self.metadata(),
            "fileId": self.object_name,
            "sourceType": SourceType.AGENCY.value,
            "origin": Origin.AMA_WEBSITE.value,
            "uploadedBy": uploaded_by,
            "status": LedgerStatus.PUBLISHED.value,
            "publishedAt": now_iso(),
        }


@dataclass(frozen=True)
class Options:
    docs_dir: Path
    dry_run: bool
    refresh_metadata: bool


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 that was decoded as Windows-1252 (e.g. 'Letâ€™s' -> 'Let’s')."""
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text
    raw = bytearray()
    for ch in text:
        try:
            raw += ch.encode("cp1252")
        except UnicodeEncodeError:
            if ord(ch) > 0xFF:
                return text
            raw.append(ord(ch))  # bytes cp1252 leaves undefined (e.g. 0x9D) pass through
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return text


def clean_title(raw: str) -> str:
    return " ".join(fix_mojibake(raw).split())  # also turns non-breaking spaces into spaces


def document_year(raw_year: str, title: str) -> int | None:
    """The manifest year if plausible; otherwise the year stated in the title.

    The manifest year is the last year found in the title or filename, so a
    range like "Medium Term Development Plan, 2026-2029" yields a future 2029;
    the title fallback then gives the range's first year, 2026.
    """
    year = plausible_year(int(raw_year)) if str(raw_year).isdigit() else None
    return year or year_from_title(title)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_raw_entries(docs_dir: Path) -> list[dict[str, Any]]:
    manifest_path = docs_dir / "manifest.json"
    if not manifest_path.exists():
        raise ManifestError(f"{manifest_path} not found")
    entries = json.loads(manifest_path.read_text())
    listed = {entry.get("file") for entry in entries}
    additions = json.loads(ADDITIONS_FILE.read_text())
    return entries + [entry for entry in additions if entry["file"] not in listed]


def to_entry(raw: dict[str, Any], docs_dir: Path, categories: dict[int, str]) -> Entry:
    missing = [field for field in REQUIRED_FIELDS if raw.get(field) in (None, "")]
    if missing:
        raise ManifestError(f"{raw.get('file', '?')}: missing {', '.join(missing)}")
    path = docs_dir / raw["file"]
    if not path.is_file():
        raise ManifestError(f"{raw['file']}: file not found")
    if int(raw["category_id"]) not in categories:
        raise ManifestError(f"{raw['file']}: unknown category_id {raw['category_id']}")
    title = clean_title(raw["title"])
    category = categories[int(raw["category_id"])]
    team = ama_department(f"dept-{raw['department']}", category, title)  # the folder, on AMA's full list
    if team not in DEPARTMENT_TEAMS:
        raise ManifestError(f"{raw['file']}: unknown department '{raw['department']}'")
    return Entry(
        file=raw["file"],
        title=title,
        category=category,
        team=team,
        document_year=document_year(raw["year"], title),
        source_url=raw["source_url"],
        sha256=file_sha256(path),
    )


def build_entries(docs_dir: Path) -> tuple[list[Entry], list[tuple[str, str]]]:
    """Validate everything up front; returns (unique entries, (duplicate, original) pairs)."""
    categories = categories_by_id()
    entries, duplicates, seen, errors = [], [], {}, []
    for raw in load_raw_entries(docs_dir):
        try:
            entry = to_entry(raw, docs_dir, categories)
        except ManifestError as exc:
            errors.append(str(exc))
            continue
        if entry.sha256 in seen:
            duplicates.append((entry.file, seen[entry.sha256]))
        else:
            seen[entry.sha256] = entry.file
            entries.append(entry)
    if errors:
        raise ManifestError(f"{len(errors)} invalid entr{'y' if len(errors) == 1 else 'ies'}:\n  " + "\n  ".join(errors))
    return entries, duplicates


def resolve_uploaders(teams: set[str]) -> dict[str, str]:
    """Map each department team to its seeded user's ID; fail if any team has none."""
    uploaders, missing = {}, []
    for team in sorted(teams):
        memberships = get_teams().list_memberships(team).memberships
        if memberships:
            uploaders[team] = memberships[0].userid
        else:
            missing.append(team)
    if missing:
        raise ManifestError(f"no seeded user in team(s): {', '.join(missing)}. Run seed_users.py first.")
    return uploaders


def refresh_metadata(entry: Entry, document: dict[str, Any], dry_run: bool) -> str | None:
    """Bring an existing record's manifest fields up to date. Never touches status or ingestion."""
    changes = {key: value for key, value in entry.metadata().items() if document.get(key) != value}
    if not changes:
        return None
    if not dry_run:
        update_document(entry.document_id, changes)
    return f"{'would update' if dry_run else 'updated'} {', '.join(sorted(changes))}"


def import_entry(entry: Entry, uploaded_by: str, options: Options) -> tuple[str, str]:
    """Run every step not already done. Returns (outcome, detail)."""
    steps = []
    if not ledger_file_exists(entry.object_name):
        if not options.dry_run:
            upload_ledger_file((options.docs_dir / entry.file).read_bytes(), Path(entry.file).name, entry.object_name)
        steps.append("would upload" if options.dry_run else "uploaded")
    document = find_document(entry.document_id)
    if document is None:
        if not options.dry_run:
            create_document(entry.document_id, entry.record(uploaded_by))
        steps.append("would create record" if options.dry_run else "record created")
    else:
        note = refresh_metadata(entry, document, options.dry_run) if options.refresh_metadata else None
        if document.get("ingestedAt"):
            if not steps:
                return ("updated", note) if note else ("done", "already imported")
            return "imported", " · ".join([*steps, *filter(None, [note])])
        steps.extend(filter(None, [note]))
    if options.dry_run:
        return "imported", " · ".join([*steps, "would ingest"])
    result = ingest_document(entry.document_id)
    steps.append(f"{result.chunk_count} chunks" if result.searchable else "NOT SEARCHABLE (no text)")
    return ("imported" if result.searchable else "not_searchable"), " · ".join(steps)


def run(entries: list[Entry], uploaders: dict[str, str], options: Options) -> dict[str, list[str]]:
    outcomes: dict[str, list[str]] = {"imported": [], "updated": [], "done": [], "not_searchable": [], "failed": []}
    for number, entry in enumerate(entries, 1):
        label = f"[{number}/{len(entries)}] {entry.file[:62]:62}"
        try:
            outcome, detail = import_entry(entry, uploaders[entry.team], options)
        except Exception as exc:  # one bad document must not stop the import
            outcome, detail = "failed", f"FAILED {type(exc).__name__}: {str(exc)[:200]}"
        outcomes[outcome].append(f"{entry.file}: {detail}" if outcome == "failed" else entry.file)
        print(f"{label} {detail}", flush=True)
    return outcomes


def print_summary(outcomes: dict[str, list[str]], duplicates: list[tuple[str, str]]) -> None:
    print(
        f"\nImported {len(outcomes['imported'])}, metadata updated {len(outcomes['updated'])}, "
        f"already done {len(outcomes['done'])}, "
        f"not searchable {len(outcomes['not_searchable'])}, failed {len(outcomes['failed'])}, "
        f"duplicates skipped {len(duplicates)}."
    )
    for duplicate, original in duplicates:
        print(f"  duplicate: {duplicate} (same file as {original})")
    for item in outcomes["not_searchable"]:
        print(f"  not searchable: {item}")
    for item in outcomes["failed"]:
        print(f"  failed: {item}")


def select(entries: list[Entry], only: str | None, limit: int | None) -> list[Entry]:
    chosen = [entry for entry in entries if only is None or only in entry.file]
    return chosen[:limit] if limit else chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the AMA document archive into Nokware.")
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--limit", type=int, help="import at most N documents (manifest order)")
    parser.add_argument("--only", help="only files whose path contains this text")
    parser.add_argument("--dry-run", action="store_true", help="report what would happen without writing")
    parser.add_argument(
        "--refresh-metadata",
        action="store_true",
        help="update title, department, category, source URL and year on existing records",
    )
    args = parser.parse_args()
    options = Options(docs_dir=args.docs_dir, dry_run=args.dry_run, refresh_metadata=args.refresh_metadata)
    logging.basicConfig(level=logging.WARNING, format="    %(message)s")
    quiet_sdk_deprecation_warnings()
    try:
        get_settings()
        entries, duplicates = build_entries(args.docs_dir)
        entries = select(entries, args.only, args.limit)
        uploaders = resolve_uploaders({entry.team for entry in entries})
    except ValidationError as exc:
        print(settings_error_summary(exc))
        return 1
    except ManifestError as exc:
        print(f"Manifest error (nothing written): {exc}")
        return 1
    print(f"Importing {len(entries)} document(s){' (dry run, nothing written)' if args.dry_run else ''}\n")
    try:
        outcomes = run(entries, uploaders, options)
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run the same command to resume; finished steps are skipped.")
        return 130
    print_summary(outcomes, duplicates)
    return 1 if outcomes["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
