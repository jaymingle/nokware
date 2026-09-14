"""Arkesel SMS: the provider behind citizen notifications.

A message is a POST to Arkesel's v2 send endpoint with the api-key header. In
sandbox mode (ARKESEL_SANDBOX, on by default) Arkesel accepts the request but
delivers nothing and spends no credits. Outside it, a daily page limit
(SMS_DAILY_LIMIT) guards the credits. Text is made plain GSM-7 first, so a page
holds 160 characters, and an error never carries the key or a whole number.
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings
from app.services.ledger_documents import utc_now
from app.services.sms_text import is_gsm7, pages, plain

logger = logging.getLogger(__name__)

SEND_URL = "https://sms.arkesel.com/api/v2/sms/send"
BALANCE_URL = "https://sms.arkesel.com/api/v2/clients/balance-details"
TIMEOUT_SECONDS = 10.0
SENDER_MAX = 11  # an alphanumeric sender ID is at most 11 characters
_NUMBERS = re.compile(r"\+?\d{7,}")


class SmsError(RuntimeError):
    """Arkesel refused the message or couldn't be reached. The text is safe to store."""


class SmsLimitReached(SmsError):
    """Today's SMS pages are used up."""


class SmsNotConfigured(RuntimeError):
    """SMS_PROVIDER=arkesel without the settings it needs."""


def _scrub(text: str) -> str:
    """Arkesel's own words, without any phone number it may echo."""
    return _NUMBERS.sub("[number]", text)[:300]


class DailyBudget:
    """SMS pages sent today (UTC) outside the sandbox. Kept in this process: a restart resets it."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._day: date | None = None
        self._used = 0
        self._lock = threading.Lock()

    def take(self, count: int, today: date) -> None:
        with self._lock:
            if self._day != today:
                self._day, self._used = today, 0
            if self._used + count > self.limit:
                raise SmsLimitReached(f"Today's limit of {self.limit} SMS pages is reached.")
            self._used += count

    def give_back(self, count: int) -> None:
        with self._lock:
            self._used = max(0, self._used - count)


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _message_id(data: Any) -> str:
    """Arkesel's ID for the message: data is a list of {recipient, id} or a single {id}."""
    first = data[0] if isinstance(data, list) and data else data
    return str(first.get("id", "")) if isinstance(first, dict) else ""


@dataclass
class ArkeselSms:
    api_key: str
    sender: str
    sandbox: bool
    budget: DailyBudget
    client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=TIMEOUT_SECONDS))

    @property
    def name(self) -> str:
        return "arkesel-sandbox" if self.sandbox else "arkesel"

    @property
    def delivers(self) -> bool:
        return not self.sandbox

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, url, headers={"api-key": self.api_key}, **kwargs)
        except httpx.HTTPError as error:
            raise SmsError(f"Arkesel couldn't be reached ({type(error).__name__}).") from None
        body = _body(response)
        if response.is_error or body.get("status") != "success":
            detail = _scrub(str(body.get("message") or body or response.reason_phrase))
            raise SmsError(f"Arkesel refused the request ({response.status_code}): {detail}")
        return body

    def send(self, to: str, body: str) -> str:
        """Send one SMS; return Arkesel's message ID. Raises SmsError, SmsLimitReached."""
        text = plain(body)
        count = pages(text)
        if not is_gsm7(text):
            logger.warning("An SMS goes as Unicode: %d pages instead of GSM-7's fewer", count)
        if not self.sandbox:
            self.budget.take(count, utc_now().date())
        payload = {"sender": self.sender, "message": text, "recipients": [to.lstrip("+")], "sandbox": self.sandbox}
        try:
            return _message_id(self._request("POST", SEND_URL, json=payload).get("data"))
        except SmsError:
            if not self.sandbox:
                self.budget.give_back(count)
            raise

    def balance(self) -> dict[str, Any]:
        """The account's SMS and main balances. Costs nothing."""
        data = self._request("GET", BALANCE_URL).get("data")
        return data if isinstance(data, dict) else {}


@lru_cache
def arkesel() -> ArkeselSms:
    """The one Arkesel client for this process, so the daily budget is shared by every message."""
    settings = get_settings()
    if not settings.arkesel_api_key or not settings.arkesel_sender_id:
        raise SmsNotConfigured("SMS_PROVIDER=arkesel needs ARKESEL_API_KEY and ARKESEL_SENDER_ID.")
    if len(settings.arkesel_sender_id) > SENDER_MAX:
        raise SmsNotConfigured(f"ARKESEL_SENDER_ID must be at most {SENDER_MAX} characters.")
    return ArkeselSms(
        api_key=settings.arkesel_api_key,
        sender=settings.arkesel_sender_id,
        sandbox=settings.arkesel_sandbox,
        budget=DailyBudget(settings.sms_daily_limit),
    )
