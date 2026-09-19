"""An unreachable search index has to fail before the page gives up, or the reader is told nothing useful.

The pool's checkout timeout is what a caller actually waits: left at psycopg_pool's 30s default it retried until
the page had already timed out, and the reader saw a generic "didn't answer in time" instead of the API's 503.
"""

from typing import Any

import psycopg

from app.services import search_index, vectorstore

PAGE_DEADLINE_SECONDS = 30  # the frontend gives up here; the API must have answered by then
URL = "postgresql+psycopg://nokware_user:secret@localhost:5434/nokware_rag"


def pool_arguments(monkeypatch: Any) -> dict[str, Any]:
    recorded: dict[str, Any] = {}

    class Recorder:
        check_connection = staticmethod(lambda conn: None)

        def __init__(self, conninfo: str, **kwargs: Any) -> None:
            recorded.update(kwargs, conninfo=conninfo)

        def close(self) -> None:
            return None

    monkeypatch.setattr(vectorstore, "ConnectionPool", Recorder)
    vectorstore.get_pool.cache_clear()
    monkeypatch.setattr(vectorstore.atexit, "register", lambda *_: None)
    vectorstore.get_pool()
    vectorstore.get_pool.cache_clear()
    return recorded


def test_the_pool_gives_up_well_before_the_page_does(monkeypatch: Any) -> None:
    timeout = pool_arguments(monkeypatch)["timeout"]
    assert timeout < PAGE_DEADLINE_SECONDS
    assert timeout == vectorstore.POOL_CONNECT_SECONDS + 1, "one connect attempt, not a retry loop"


def test_a_connect_attempt_is_still_allowed_to_finish(monkeypatch: Any) -> None:
    """A checkout timeout at or under connect_timeout would cut off a connection that was about to succeed."""
    recorded = pool_arguments(monkeypatch)
    assert recorded["kwargs"]["connect_timeout"] == vectorstore.POOL_CONNECT_SECONDS
    assert recorded["timeout"] > recorded["kwargs"]["connect_timeout"]


def test_the_startup_check_bounds_its_own_connection_and_never_goes_through_the_pool(monkeypatch: Any) -> None:
    """It connects directly, so the pool's checkout timeout can't apply: its own connect_timeout is the whole wait."""
    seen: dict[str, Any] = {}

    def record(conninfo: str, **kwargs: Any) -> None:
        seen.update(kwargs)
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(search_index.psycopg, "connect", record)
    monkeypatch.setattr(vectorstore, "ConnectionPool", None)  # touching the pool would raise
    assert search_index.check(URL).ok is False
    assert seen == {"connect_timeout": search_index.CONNECT_SECONDS}
