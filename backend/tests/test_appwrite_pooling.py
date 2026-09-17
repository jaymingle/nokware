"""The SDK's shared connection pool: never keeps cookies between calls, and survives Appwrite closing an idle
connection."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import appwrite.client as sdk_client_module
import pytest
import requests
from appwrite.models import Document

from app.services import appwrite_client  # installs the pool
from app.services.appwrite_client import as_record


class _SetsACookie(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Set-Cookie", "a_session_project=secret; Path=/")
        self.send_header("X-Cookie-Received", self.headers.get("Cookie", ""))
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


class _ClosesUnannounced(BaseHTTPRequestHandler):
    """Answers the first call on a connection and keeps it open; hangs up on the next without answering, as
    Appwrite's side did to a kept connection after a quiet spell ("Remote end closed connection without response")."""

    protocol_version = "HTTP/1.1"
    seen: list[str] = []

    def _answer(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.calls = getattr(self, "calls", 0) + 1
        if self.calls > 1:
            self.seen.append(f"{self.command} (hung up)")
            self.close_connection = True
            return
        self.seen.append(self.command)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST = _answer

    def log_message(self, *args: object) -> None:
        pass


def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)  # a kept connection must not hold up shutdown
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture
def server_url() -> Iterator[str]:
    yield from _serve(_SetsACookie)


@pytest.fixture
def closing_url() -> Iterator[str]:
    _ClosesUnannounced.seen = []
    yield from _serve(_ClosesUnannounced)


def test_cookies_set_by_one_call_are_not_sent_on_the_next(server_url: str) -> None:
    pooled = sdk_client_module.requests
    first = pooled.request("get", server_url)
    assert first.headers["Set-Cookie"]  # the server did try to set one
    second = pooled.request("get", server_url)
    assert second.headers["X-Cookie-Received"] == ""


def test_other_requests_attributes_still_resolve() -> None:
    assert sdk_client_module.requests.exceptions.RequestException


def test_a_connection_closed_at_appwrites_end_is_not_the_end_of_the_call(closing_url: str) -> None:
    pooled = appwrite_client._PooledRequests()
    assert pooled.request("get", closing_url).status_code == 200
    assert pooled.request("get", closing_url).status_code == 200  # hung up on, so sent once more on a new connection
    with pytest.raises(requests.ConnectionError):
        pooled.request("post", closing_url, data="x")  # never sent twice: the first may have been acted on
    pooled._last_call -= appwrite_client.IDLE_RESET_SECONDS + 1
    assert pooled.request("post", closing_url, data="x").status_code == 200  # after a quiet spell, kept ones are dropped
    assert _ClosesUnannounced.seen == ["GET", "GET (hung up)", "GET", "POST (hung up)", "POST"]


def test_a_document_from_the_sdk_becomes_a_record() -> None:
    """A stray @lru_cache once landed on as_record: SDK documents are unhashable, so every Appwrite write failed."""
    document = Document.with_data({"$id": "c1", "$sequence": "1", "$collectionId": "reports", "$databaseId": "db",
                                   "$createdAt": "2026-09-17T00:00:00Z", "$updatedAt": "2026-09-17T00:00:01Z",
                                   "$permissions": [], "caseId": "c1"})
    assert as_record(document) == {"caseId": "c1", "$id": "c1", "$createdAt": "2026-09-17T00:00:00Z",
                                   "$updatedAt": "2026-09-17T00:00:01Z"}
