"""Test isolation: no test sends a message or reaches the network, whatever backend/.env says.

The environment wins over .env in pydantic-settings, so the messaging settings
are pinned here, before any app module reads them. A test that needs a
provider builds one with a mock transport, and one that needs Redis uses
fakeredis. Only this machine (a test's own local server) can be reached.
"""

import os
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
import requests

for _name in ("ARKESEL_API_KEY", "ARKESEL_SENDER_ID", "ARKESEL_WEBHOOK_SECRET", "BMS_API_KEY", "PUBLIC_API_URL",
              "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "REDIS_URL"):
    os.environ[_name] = ""
os.environ["SMS_PROVIDER"] = "log"
os.environ["WHATSAPP_PROVIDER"] = "log"
os.environ["ARKESEL_SANDBOX"] = "true"
os.environ["SMS_VERIFICATION_CODES"] = "false"  # the default; a test that needs codes switches them on itself

LOCAL = {"127.0.0.1", "localhost", "::1"}
_httpx_handle = httpx.HTTPTransport.handle_request
_requests_request = requests.Session.request


def _refuse(host: str | None) -> None:
    if host not in LOCAL:
        raise RuntimeError(f"A test tried to reach {host}: stub it instead.")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def guarded_httpx(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        _refuse(request.url.host)
        return _httpx_handle(self, request)

    def guarded_requests(self: requests.Session, method: str, url: str, *args: Any, **kwargs: Any) -> requests.Response:
        _refuse(urlsplit(url).hostname)
        return _requests_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", guarded_httpx)
    monkeypatch.setattr(requests.Session, "request", guarded_requests)
