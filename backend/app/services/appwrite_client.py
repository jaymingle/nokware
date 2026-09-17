"""Singleton Appwrite client and service accessors.

The client is configured from application settings and cached so the whole
backend shares one instance. Service accessors are also cached; import the
accessor you need rather than building services ad hoc.
"""

import logging
import threading
import time
from functools import lru_cache
from http.cookiejar import DefaultCookiePolicy
from typing import Any

import appwrite.client as sdk_client_module
import requests
from appwrite.client import Client
from appwrite.exception import AppwriteException
from appwrite.models import Document
from appwrite.query import Query
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.services.teams import Teams
from appwrite.services.users import Users
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import get_settings

DATABASE_ID = "nokware"
_DEPRECATION_MARKER = "has been deprecated since"
# Appwrite's side closes a kept-alive connection left idle for a few minutes (seen at about four); after this long
# without a call, the kept connections are dropped rather than tried.
IDLE_RESET_SECONDS = 60


class _DropSdkDeprecations(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return _DEPRECATION_MARKER not in record.getMessage()


def quiet_sdk_deprecation_warnings() -> None:
    """Hide the SDK's per-call "Databases API is deprecated" warnings.

    The 'nokware' database is a legacy-type database, so the Databases API is
    the right one for it on this 1.9 server. The SDK forces these warnings on
    for every call (it resets warning filters itself, so warnings.filterwarnings
    cannot stop them); routing warnings through logging lets us drop just these
    while every other warning still shows.
    """
    logging.captureWarnings(True)
    logging.getLogger("py.warnings").addFilter(_DropSdkDeprecations())


class _PooledRequests:
    """Stands in for the requests module inside the SDK, reusing connections.

    The SDK sends every call through requests.request(), which opens a new TLS
    connection each time: about 430 ms per call to our Appwrite, against about
    140 ms on a reused connection. Routing that one function through a shared
    Session keeps connections alive; everything else falls through to requests.

    The Session must never carry cookies: calls made with different users' JWTs
    share it, so cookies are refused outright rather than stored.

    A kept connection can be closed at Appwrite's end while it sits idle, and
    the next call on it fails ("Remote end closed connection without
    response"). So after IDLE_RESET_SECONDS of quiet the kept connections are
    dropped first, and a call that meets a dropped connection anyway is sent
    once more on a new one, but only when repeating it is harmless (GET, PUT,
    DELETE): a create is never sent twice.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        once = Retry(total=1, connect=1, read=1, redirect=0, status=0, other=0, allowed_methods=Retry.DEFAULT_ALLOWED_METHODS)
        for scheme in ("https://", "http://"):
            self._session.mount(scheme, HTTPAdapter(max_retries=once))
        self._last_call = time.monotonic()
        self._lock = threading.Lock()

    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        with self._lock:
            now = time.monotonic()
            if now - self._last_call > IDLE_RESET_SECONDS:
                self._session.close()  # only idle connections close; a call in flight keeps its own
            self._last_call = now
        return self._session.request(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(requests, name)


sdk_client_module.requests = _PooledRequests()  # applies to every SDK client, including per-request JWT clients


@lru_cache
def get_client() -> Client:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return client


@lru_cache
def get_databases() -> Databases:
    return Databases(get_client())


@lru_cache
def get_teams() -> Teams:
    return Teams(get_client())


@lru_cache
def get_users() -> Users:
    return Users(get_client())


@lru_cache
def get_storage() -> Storage:
    return Storage(get_client())


def as_record(document: Document) -> dict[str, Any]:
    """A stored document's attributes plus its $id, $createdAt and $updatedAt."""
    return {**document.data, "$id": document.id, "$createdAt": document.createdat, "$updatedAt": document.updatedat}


def find_record(collection_id: str, document_id: str) -> dict[str, Any] | None:
    """One document as a record, or None if it doesn't exist."""
    try:
        return as_record(get_databases().get_document(DATABASE_ID, collection_id, document_id))
    except AppwriteException as exc:
        if exc.code == 404:
            return None
        raise


PAGE_SIZE = 500


def every_record(collection_id: str, queries: list[str]) -> list[dict[str, Any]]:
    """Every document matching the queries, read a page at a time."""
    found: list[dict[str, Any]] = []
    cursor: list[str] = []
    while True:
        page = [*queries, *cursor, Query.limit(PAGE_SIZE)]
        listing = get_databases().list_documents(DATABASE_ID, collection_id, queries=page)
        found.extend(as_record(d) for d in listing.documents)
        if len(listing.documents) < PAGE_SIZE:
            return found
        cursor = [Query.cursor_after(listing.documents[-1].id)]
