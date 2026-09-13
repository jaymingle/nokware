"""Verify live connectivity to every external service the backend uses.

Read-only: every check lists or reads metadata; nothing is written anywhere.
The Postgres session is opened read-only as an extra guard.

Run from anywhere with the backend virtualenv:

    backend/.venv/bin/python backend/scripts/verify_connections.py

Exits 0 when every check passes, 1 otherwise. Secret values from .env are
redacted from any error text that gets printed.
"""

import sys
from collections.abc import Callable
from dataclasses import dataclass

import psycopg
from appwrite.query import Query
from minio.error import S3Error
from psycopg.conninfo import conninfo_to_dict
from pydantic import ValidationError

from app.config import get_settings, settings_error_summary
from app.services.appwrite_client import (
    DATABASE_ID,
    get_databases,
    get_teams,
    quiet_sdk_deprecation_warnings,
)
from app.services.llm import CHAT_MODEL, get_chat_model
from app.services.storage import get_minio
from app.services.vectorstore import (
    CONTENT_COLUMN,
    EMBEDDING_COLUMN,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    ID_COLUMN,
    METADATA_COLUMNS,
    TABLE_NAME,
    get_embeddings,
    libpq_url,
)
from app.teams import ALL_TEAMS

EXPECTED_TEAMS = ALL_TEAMS
EXPECTED_COLLECTIONS = ("ledger_documents", "citizen_reports", "case_history")
EXPECTED_COLUMNS = (ID_COLUMN, CONTENT_COLUMN, EMBEDDING_COLUMN, *METADATA_COLUMNS)
PSYCOPG_SCHEME = "postgresql+psycopg://"
MINIO_PROBE_OBJECT = "__nokware_permission_probe__/does-not-exist"

_COLUMNS_SQL = """
    SELECT attname, format_type(atttypid, atttypmod)
    FROM pg_attribute
    WHERE attrelid = to_regclass(%s) AND attnum > 0 AND NOT attisdropped
"""


class CheckFailed(Exception):
    """A check reached the service but found something wrong."""


@dataclass
class Result:
    name: str
    passed: bool
    detail: str


def _redact(text: str) -> str:
    settings = get_settings()
    password = conninfo_to_dict(libpq_url(settings.postgres_url)).get("password")
    secrets = [
        settings.postgres_url, password, settings.appwrite_api_key,
        settings.minio_access_key, settings.minio_secret_key, settings.gemini_api_key,
    ]
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def check_teams() -> str:
    teams = get_teams().list(queries=[Query.limit(100)]).teams
    missing = sorted(set(EXPECTED_TEAMS) - {team.name for team in teams})
    if missing:
        raise CheckFailed(f"missing {len(missing)} team(s): {', '.join(missing)}")
    return f"all {len(EXPECTED_TEAMS)} teams present"


def check_database() -> str:
    # Listing collections proves the database exists (404 otherwise). databases.get()
    # is avoided: SDK 17's Database model requires fields a self-hosted 1.9.0
    # server doesn't return, so parsing it fails.
    listing = get_databases().list_collections(DATABASE_ID, queries=[Query.limit(100)])
    found = {collection.id for collection in listing.collections}
    missing = [c for c in EXPECTED_COLLECTIONS if c not in found]
    if missing:
        raise CheckFailed(f"database '{DATABASE_ID}' is missing: {', '.join(missing)}")
    return f"database '{DATABASE_ID}' has {', '.join(EXPECTED_COLLECTIONS)}"


def _connect(url: str) -> tuple[psycopg.Connection, str]:
    params = conninfo_to_dict(libpq_url(url))
    where = f"{params.get('host', 'localhost')}:{params.get('port', '5432')}"
    try:
        return psycopg.connect(libpq_url(url), connect_timeout=5), where
    except psycopg.OperationalError as exc:
        raise CheckFailed(
            f"could not connect to Postgres at {where}. Is the SSH tunnel open? ({exc})"
        ) from exc


def check_postgres() -> str:
    url = get_settings().postgres_url
    conn, where = _connect(url)
    with conn:
        conn.read_only = True
        columns = dict(conn.execute(_COLUMNS_SQL, (TABLE_NAME,)).fetchall())
        chunks = conn.execute(f'SELECT count(*) FROM "{TABLE_NAME}"').fetchone()[0] if columns else 0
    if not columns:
        raise CheckFailed(f"connected to {where}, but table '{TABLE_NAME}' does not exist")
    missing = [c for c in EXPECTED_COLUMNS if c not in columns]
    if missing:
        raise CheckFailed(f"'{TABLE_NAME}' is missing column(s): {', '.join(missing)}")
    if columns[EMBEDDING_COLUMN] != f"vector({EMBEDDING_DIMENSIONS})":
        raise CheckFailed(f"'{EMBEDDING_COLUMN}' is {columns[EMBEDDING_COLUMN]}, expected vector({EMBEDDING_DIMENSIONS})")
    if not url.startswith(PSYCOPG_SCHEME):
        raise CheckFailed(f"table OK, but POSTGRES_URL must start with {PSYCOPG_SCHEME} for vectorstore.py")
    return f"{where}: '{TABLE_NAME}' has all {len(EXPECTED_COLUMNS)} columns, vector({EMBEDDING_DIMENSIONS}), {chunks} chunk(s)"


def _assert_readable(bucket: str) -> None:
    """Stat a key that never exists: NoSuchKey proves GetObject is permitted."""
    try:
        get_minio().stat_object(bucket_name=bucket, object_name=MINIO_PROBE_OBJECT)
    except S3Error as exc:
        if exc.code != "NoSuchKey":
            raise


def check_minio() -> str:
    settings = get_settings()
    buckets = (settings.minio_ledger_bucket, settings.minio_photos_bucket)
    problems = []
    for bucket in buckets:
        if not get_minio().bucket_exists(bucket_name=bucket):
            problems.append(f"'{bucket}' does not exist")
            continue
        _assert_readable(bucket)
    if problems:
        raise CheckFailed("; ".join(problems))
    return f"buckets reachable and readable: {', '.join(buckets)}"


def check_embeddings() -> str:
    vector = get_embeddings().embed_query("Nokware connectivity check")
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise CheckFailed(f"{EMBEDDING_MODEL} returned {len(vector)} dims, expected {EMBEDDING_DIMENSIONS}")
    return f"{EMBEDDING_MODEL} returned a {len(vector)}-dim vector"


def check_chat() -> str:
    reply = get_chat_model(0.0).invoke("Reply with exactly one word: pong").text.strip()
    if not reply:
        raise CheckFailed(f"{CHAT_MODEL} returned an empty response")
    return f"{CHAT_MODEL} replied {reply[:60]!r}"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("Appwrite teams", check_teams),
    ("Appwrite database + collections", check_database),
    ("Postgres document_chunks", check_postgres),
    ("MinIO buckets", check_minio),
    ("Gemini embeddings", check_embeddings),
    ("Gemini chat", check_chat),
]


def run_check(number: int, name: str, check: Callable[[], str]) -> Result:
    try:
        result = Result(name, True, check())
    except Exception as exc:  # diagnostic script: record every failure, keep going
        result = Result(name, False, _redact(f"{type(exc).__name__}: {exc}"))
    status = "PASS" if result.passed else "FAIL"
    summary = result.detail if result.passed else result.detail.splitlines()[0][:160]
    print(f"[{status}] {number}. {name}: {summary}", flush=True)
    return result


def print_summary(results: list[Result]) -> None:
    failures = [(i, r) for i, r in enumerate(results, 1) if not r.passed]
    print(f"\nSummary: {len(results) - len(failures)} passed, {len(failures)} failed")
    for number, result in failures:
        print(f"\n  {number}. {result.name}\n     {result.detail}")


def main() -> int:
    quiet_sdk_deprecation_warnings()
    try:
        get_settings()
    except ValidationError as exc:
        print(settings_error_summary(exc))
        return 1
    print("Nokware connection checks (read-only)\n")
    results = [run_check(i, name, check) for i, (name, check) in enumerate(CHECKS, 1)]
    print_summary(results)
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
