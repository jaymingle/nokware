"""Put back what a backup holds: the Appwrite rows and the photo objects, exactly as they were.

The Ledger's own database is restored with pg_restore, not from here; RESTORE.md in the backup gives that command.

A row is written back under the id it had, so a restore run twice leaves one copy, not two, and a row that survived
the reset is left as it is rather than overwritten. Object storage is the same: an object already there is kept.

A dry run by default, so the backup can be read and counted without writing anything:

    backend/.venv/bin/python backend/scripts/restore_backup.py backups/<timestamp> [--yes]
"""

import json
import sys
from pathlib import Path
from typing import Any

from appwrite.exception import AppwriteException

from app.config import get_settings
from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.storage import get_minio

ALREADY_EXISTS = 409
BAD_REQUEST = 400  # the schema refusing a row, not the restore failing
SYSTEM_FIELDS = ("$id", "$createdAt", "$updatedAt", "$permissions", "$collectionId", "$databaseId", "$sequence")


def rows(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def writable(row: dict[str, Any]) -> dict[str, Any]:
    """Appwrite sets its own system fields; sending them back is rejected."""
    return {key: value for key, value in row.items() if key not in SYSTEM_FIELDS}


def restore_collection(path: Path, apply: bool) -> tuple[int, int, list[str]]:
    """Returns how many rows the file holds, how many were missing, and the ones the schema now refuses.

    A refusal doesn't stop the restore. A backup can outlive the shape of the collection it came from — an enum
    narrowed since, an attribute made required — and one row the schema has moved past is no reason to abandon the
    other 257. They are named at the end instead, so a person decides what to do about each.
    """
    found = rows(path)
    database, missing, refused = get_databases(), 0, []
    for row in found:
        try:
            database.get_document(DATABASE_ID, path.stem, row["$id"])
            continue
        except AppwriteException as error:
            if error.code != 404:
                raise
        missing += 1
        if not apply:
            continue
        try:
            database.create_document(DATABASE_ID, path.stem, row["$id"], writable(row))
        except AppwriteException as error:
            if error.code != BAD_REQUEST:
                raise
            refused.append(f"{path.stem}/{row['$id']}: {error.message}")
    return len(found), missing, refused


def restore_storage(root: Path, apply: bool) -> tuple[int, int]:
    minio, bucket = get_minio(), get_settings().minio_photos_bucket
    files = sorted(path for path in (root / bucket).rglob("*") if path.is_file())
    missing = 0
    for path in files:
        name = str(path.relative_to(root / bucket))
        try:
            minio.stat_object(bucket, name)
            continue
        except Exception:  # any failure to stat means it isn't there to keep
            missing += 1
        if apply:
            minio.fput_object(bucket, name, str(path), content_type="image/jpeg")
    return len(files), missing


def main() -> int:
    quiet_sdk_deprecation_warnings()
    arguments = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    if not arguments:
        print(__doc__)
        return 2
    root, apply = Path(arguments[0]), "--yes" in sys.argv[1:]
    if not root.is_dir():
        print(f"No backup at {root}")
        return 1
    held = restored = 0
    refused: list[str] = []
    for path in sorted((root / "appwrite").glob("*.json")):
        if path.name.startswith("_"):
            continue
        total, missing, turned_away = restore_collection(path, apply)
        held, restored = held + total, restored + missing
        refused += turned_away
        print(f"{path.stem:34} {total:>6} in backup  {missing:>6} missing from the database")
    objects, gone = restore_storage(root / "storage", apply)
    print(f"{'photo objects':34} {objects:>6} in backup  {gone:>6} missing from storage")
    verb = "restored" if apply else "would be restored (dry run; --yes to write)"
    print(f"\n{held} rows and {objects} objects read from {root}; "
          f"{restored + gone - len(refused)} {verb}.")
    if refused:
        print(f"\n{len(refused)} row(s) the collection's shape no longer accepts, left out:")
        for line in refused:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
