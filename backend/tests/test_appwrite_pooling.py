"""The SDK's shared connection pool must never keep cookies between calls."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import appwrite.client as sdk_client_module
import pytest

import app.services.appwrite_client  # noqa: F401  (installs the pool)


class _SetsACookie(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Set-Cookie", "a_session_project=secret; Path=/")
        self.send_header("X-Cookie-Received", self.headers.get("Cookie", ""))
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _SetsACookie)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


def test_cookies_set_by_one_call_are_not_sent_on_the_next(server_url: str) -> None:
    pooled = sdk_client_module.requests
    first = pooled.request("get", server_url)
    assert first.headers["Set-Cookie"]  # the server did try to set one
    second = pooled.request("get", server_url)
    assert second.headers["X-Cookie-Received"] == ""


def test_other_requests_attributes_still_resolve() -> None:
    assert sdk_client_module.requests.exceptions.RequestException
