"""Arkesel SMS, behind citizen notifications.

In sandbox mode Arkesel accepts a request but delivers nothing and spends no credits. Outside it, a daily page limit
guards the credits; if Redis can't be reached to count, nothing is sent rather than sent uncounted. Text is made
plain GSM-7 first so a page holds 160 characters, and an error never carries the key or a whole number.
"""

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

import httpx
import redis

from app.config import get_settings
from app.services.ledger_documents import utc_now
from app.services.redis_store import RedisUnavailable, get_redis, key
from app.services.sms_text import is_gsm7, pages, plain

logger = logging.getLogger(__name__)

SEND_URL = "https://sms.arkesel.com/api/v2/sms/send"
BALANCE_URL = "https://sms.arkesel.com/api/v2/clients/balance-details"
TIMEOUT_SECONDS = 10.0
DELIVERY_REPORT_PATH = "/api/channels/sms/delivery"
SENDER_MAX = 11  # an alphanumeric sender ID is at most 11 characters
_NUMBERS = re.compile(r"\+?\d{7,}")


class SmsError(RuntimeError):
    """Arkesel refused the message or couldn't be reached. The text is safe to store."""


class SmsNothingSent(SmsError):
    """Our own side stopped before Arkesel was asked, so nothing reached anyone and sending it again is safe."""


class SmsLimitReached(SmsNothingSent):
    """Today's SMS pages are used up."""


class SmsUnreachable(SmsError):
    """The provider never answered. Whether the message went out can never be learned: no message ID came back, so
    no delivery report and no poll can ever settle it. The resident gets the message rather than the silence."""


class SmsNotConfigured(RuntimeError):
    """SMS_PROVIDER=arkesel without the settings it needs."""


def _scrub(text: str) -> str:
    return _NUMBERS.sub("[number]", text)[:300]


class _MemoryCount:
    """Only when there is no Redis; a restart resets it."""

    def __init__(self) -> None:
        self._counts: dict[date, int] = {}
        self._lock = threading.Lock()

    def add(self, today: date, count: int) -> int:
        with self._lock:
            self._counts = {today: self._counts.get(today, 0) + count}
            return self._counts[today]


class _RedisCount:
    def __init__(self, name: str = "pages") -> None:
        self.name = name

    def add(self, today: date, count: int) -> int:
        counter = key("sms", self.name, today.isoformat())
        try:
            pipe = get_redis().pipeline()
            pipe.incrby(counter, count)
            pipe.expire(counter, 2 * 86400)
            used, _ = pipe.execute()
        except (redis.RedisError, RedisUnavailable) as error:
            # Nothing was handed to the provider, so this is the daily limit's own kind of refusal: send it again.
            raise SmsNothingSent(f"The SMS limit can't be checked ({type(error).__name__}), so nothing was sent.") from None
        return int(used)


class DailyBudget:
    def __init__(self, limit: int, counter: "_MemoryCount | _RedisCount | None" = None) -> None:
        self.limit = limit
        self._counter = counter or _MemoryCount()

    def take(self, count: int, today: date) -> None:
        if self._counter.add(today, count) > self.limit:
            self._counter.add(today, -count)
            raise SmsLimitReached(f"Today's limit of {self.limit} SMS pages is reached.")

    def give_back(self, count: int, today: date) -> None:
        self._counter.add(today, -count)


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _message_id(data: Any) -> str:
    """Arkesel returns a list of {recipient, id} or a single {id}."""
    first = data[0] if isinstance(data, list) and data else data
    return str(first.get("id", "")) if isinstance(first, dict) else ""


@dataclass
class ArkeselSms:
    api_key: str
    sender: str
    sandbox: bool
    budget: DailyBudget
    callback_url: str | None = None
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
            # No answer at all: the request may have arrived. Told apart from a refusal so the sweep can send again.
            raise SmsUnreachable(f"Arkesel couldn't be reached ({type(error).__name__}).") from None
        body = _body(response)
        if response.is_error or body.get("status") != "success":
            detail = _scrub(str(body.get("message") or body or response.reason_phrase))
            raise SmsError(f"Arkesel refused the request ({response.status_code}): {detail}")
        return body

    def send(self, to: str, body: str) -> str:
        text = plain(body)
        count = pages(text)
        if not is_gsm7(text):
            logger.warning("An SMS goes as Unicode: %d pages instead of GSM-7's fewer", count)
        today = utc_now().date()
        if not self.sandbox:
            self.budget.take(count, today)
        payload = {"sender": self.sender, "message": text, "recipients": [to.lstrip("+")], "sandbox": self.sandbox}
        if self.callback_url:
            payload["callback_url"] = self.callback_url
        try:
            return _message_id(self._request("POST", SEND_URL, json=payload).get("data"))
        except SmsError:
            if not self.sandbox:
                self.budget.give_back(count, today)
            raise

    def balance(self) -> dict[str, Any]:
        """Costs nothing."""
        data = self._request("GET", BALANCE_URL).get("data")
        return data if isinstance(data, dict) else {}


@lru_cache
def arkesel() -> ArkeselSms:
    """One client per process, so the daily budget is shared by every message."""
    settings = get_settings()
    if not settings.arkesel_api_key or not settings.arkesel_sender_id:
        raise SmsNotConfigured("SMS_PROVIDER=arkesel needs ARKESEL_API_KEY and ARKESEL_SENDER_ID.")
    if len(settings.arkesel_sender_id) > SENDER_MAX:
        raise SmsNotConfigured(f"ARKESEL_SENDER_ID must be at most {SENDER_MAX} characters.")
    return ArkeselSms(
        api_key=settings.arkesel_api_key,
        sender=settings.arkesel_sender_id,
        sandbox=settings.arkesel_sandbox,
        budget=DailyBudget(settings.sms_daily_limit, _RedisCount() if settings.redis_url else _MemoryCount()),
        callback_url=delivery_report_url(),
    )


@lru_cache
def code_sms() -> ArkeselSms:
    """A daily cap of its own, so verification codes never use up the pages report notifications need, nor the reverse."""
    settings = get_settings()
    report_sms = arkesel()
    return ArkeselSms(
        api_key=report_sms.api_key,
        sender=report_sms.sender,
        sandbox=report_sms.sandbox,
        budget=DailyBudget(settings.sms_code_daily_limit, _RedisCount("code-pages") if settings.redis_url else _MemoryCount()),
    )


def delivery_report_url() -> str | None:
    """Only when reports can reach the API and be verified."""
    settings = get_settings()
    if not settings.public_api_url or not settings.arkesel_webhook_secret:
        return None
    return f"{settings.public_api_url.rstrip('/')}{DELIVERY_REPORT_PATH}"
