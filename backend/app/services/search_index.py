"""Is the Ledger's search index really there? Checked once, when the API starts.

Postgres is reached through a tunnel on a local port, and another program can
take that port: another project's database, say. Then nothing looks wrong
until a resident asks a question and the search fails 30 seconds later with
"password authentication failed", which says nothing about why. So at startup
the API connects once, quickly, and checks that it reached the database
POSTGRES_URL names and that the database holds the search index (the chunks
table and its embeddings). If not, it says plainly what answered instead.

It only reports. The API still starts, because reports, the portal and
petitions don't need the search index; Ask and the Ledger search answer 503
until it is fixed.
"""

import logging
from dataclasses import dataclass

import psycopg
from psycopg.conninfo import conninfo_to_dict

from app.config import get_settings
from app.services.vectorstore import EMBEDDING_COLUMN, EMBEDDING_DIMENSIONS, TABLE_NAME, libpq_url

logger = logging.getLogger(__name__)

CONNECT_SECONDS = 5
_EMBEDDINGS_SQL = """
SELECT format_type(a.atttypid, a.atttypmod)
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
WHERE c.relname = %s AND a.attname = %s AND NOT a.attisdropped
"""
_REFUSED = ("password authentication failed", "does not exist", "no pg_hba.conf entry")
_ABSENT = ("connection refused", "timeout expired", "could not connect", "connection timed out")


@dataclass(frozen=True)
class IndexCheck:
    ok: bool
    message: str


@dataclass(frozen=True)
class Target:
    where: str
    database: str
    user: str


def target(url: str) -> Target:
    params = conninfo_to_dict(libpq_url(url))
    return Target(f"{params.get('host', 'localhost')}:{params.get('port', '5432')}", str(params.get("dbname", "")),
                  str(params.get("user", "")))


def explain(error: str, to: Target) -> str:
    """A connection failure in plain words: nothing there, or something that isn't Nokware's database."""
    lowered = error.lower()
    if any(sign in lowered for sign in _REFUSED):
        return (f"Something answers on {to.where}, but it isn't Nokware's search index: it turned away user "
                f"{to.user} for database {to.database}. Another Postgres has probably taken the port (check `docker ps`), "
                "or the tunnel runs on a different port from the one in POSTGRES_URL.")
    if any(sign in lowered for sign in _ABSENT):
        return f"Nothing answers on {to.where}. Open the tunnel to Nokware's Postgres, or correct the port in POSTGRES_URL."
    return f"Postgres at {to.where} can't be used: {error.strip().splitlines()[0] if error.strip() else 'unknown error'}"


def inspect(connection: psycopg.Connection, to: Target) -> IndexCheck:
    """Connected: is this the database POSTGRES_URL names, and does it hold the search index?"""
    database = connection.execute("SELECT current_database()").fetchone()[0]
    embeddings = connection.execute(_EMBEDDINGS_SQL, (TABLE_NAME, EMBEDDING_COLUMN)).fetchone()
    expected = f"vector({EMBEDDING_DIMENSIONS})"
    if database != to.database:
        return IndexCheck(False, f"{to.where} answered as database {database}, not {to.database}: it isn't Nokware's search index.")
    if embeddings is None:
        return IndexCheck(False, f"{to.where} has a database called {database}, but no {TABLE_NAME} table with embeddings: "
                                 "it isn't Nokware's search index. Is another Postgres on this port?")
    if embeddings[0] != expected:
        return IndexCheck(False, f"{database}.{TABLE_NAME}.{EMBEDDING_COLUMN} is {embeddings[0]}, not {expected}.")
    return IndexCheck(True, f"The Ledger's search index is reachable: {database} at {to.where}.")


def check(url: str) -> IndexCheck:
    to = target(url)
    try:
        with psycopg.connect(libpq_url(url), connect_timeout=CONNECT_SECONDS) as connection:
            connection.read_only = True
            return inspect(connection, to)
    except psycopg.Error as error:
        return IndexCheck(False, explain(str(error), to))


def startup_check() -> IndexCheck:
    """Run the check and say what it found, loudly if the index isn't there."""
    result = check(get_settings().postgres_url)
    if result.ok:
        logger.info(result.message)
    else:
        logger.error("THE LEDGER'S SEARCH INDEX ISN'T REACHABLE. Ask and the Ledger search will fail until this is fixed. %s",
                     result.message)
    return result
