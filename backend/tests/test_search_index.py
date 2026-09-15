"""The startup check: it says plainly when POSTGRES_URL doesn't reach Nokware's search index."""

from typing import Any

import psycopg
import pytest

from app.services import search_index
from app.services.search_index import Target, check, explain, inspect

URL = "postgresql+psycopg://nokware_user:secret@localhost:5434/nokware_rag"
TO = Target("localhost:5434", "nokware_rag", "nokware_user")


class FakeConnection:
    def __init__(self, database: str, embeddings: str | None) -> None:
        self.answers = [(database,), (embeddings,) if embeddings else None]
        self.read_only = False

    def execute(self, sql: str, params: Any = None) -> "FakeConnection":
        self.row = self.answers.pop(0)
        return self

    def fetchone(self) -> Any:
        return self.row

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_the_target_is_read_from_postgres_url_and_the_password_never_appears() -> None:
    assert search_index.target(URL) == TO
    assert "secret" not in explain('password authentication failed for user "nokware_user"', TO)


def test_another_database_on_the_port_is_named_as_that_not_as_a_bad_password() -> None:
    message = explain('connection failed: FATAL:  password authentication failed for user "nokware_user"', TO)
    assert message.startswith("Something answers on localhost:5434, but it isn't Nokware's search index") and "docker ps" in message
    assert "isn't Nokware's search index" in explain('FATAL:  database "nokware_rag" does not exist', TO)
    assert explain("connection refused", TO).startswith("Nothing answers on localhost:5434. Open the tunnel")


def test_a_database_without_the_search_index_is_caught_once_connected() -> None:
    assert inspect(FakeConnection("nokware_rag", "vector(768)"), TO).ok
    missing = inspect(FakeConnection("nokware_rag", None), TO)
    assert not missing.ok and "no document_chunks table" in missing.message
    assert "not vector(768)" in inspect(FakeConnection("nokware_rag", "vector(1536)"), TO).message


def test_a_failed_connection_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise psycopg.OperationalError('FATAL:  password authentication failed for user "nokware_user"')

    monkeypatch.setattr(search_index.psycopg, "connect", refuse)
    result = check(URL)
    assert not result.ok and "Another Postgres has probably taken the port" in result.message
    monkeypatch.setattr(search_index.psycopg, "connect", lambda *a, **k: FakeConnection("vult_dev", None))
    assert check(URL).message == "localhost:5434 answered as database vult_dev, not nokware_rag: it isn't Nokware's search index."
