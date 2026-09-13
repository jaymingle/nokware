"""One lock per record, so two changes to the same Ledger document or case never interleave.

Every change re-reads its record under the lock, applies a rule and writes the
result. The locks live in this process: run the API as a single worker until
changes move to Appwrite transactions.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


@contextmanager
def record_lock(record_id: str) -> Iterator[None]:
    with _locks_guard:
        lock = _locks.setdefault(record_id, threading.Lock())
    with lock:
        yield
