"""BMS Africa SMS (mNotify's API), SMS_PROVIDER=bms, beside Arkesel.

"Nokware" is already an approved sender ID on BMS, so messages go out at once instead of being held for review,
which is what lets verification codes by SMS go live. USSD stays on Arkesel either way.

BMS has no sandbox, so every send is live and charged, and no delivery webhook, so delivery is polled
(bms_deliveries.py). Its campaign ID stands as the message's ID in the outbox.

BMS takes its API key as a query parameter, so the key is in every request's address. It is kept out of every
error raised here (so out of the outbox), and redacted from httpx's request log line.
"""

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.services.ledger_documents import utc_now
from app.services.report_contacts import GHANA_CODE
from app.services.sms import (
    SENDER_MAX,
    TIMEOUT_SECONDS,
    DailyBudget,
    SmsError,
    SmsNotConfigured,
    SmsUnreachable,
    _body,
    _MemoryCount,
    _RedisCount,
    _scrub,
)
from app.services.sms_text import is_gsm7, pages, plain

logger = logging.getLogger(__name__)

API = "https://api.mnotify.com/api"
SEND_URL = f"{API}/sms/quick"
BALANCE_URL = f"{API}/balance/sms"
CAMPAIGN_URL = f"{API}/campaign/{{campaign_id}}"
SENT = "2000"  # BMS's code for a campaign accepted
_KEY = re.compile(r"(key=)[^&\s\"']+")


class _RedactKey(logging.Filter):
    """httpx logs each request's full address at INFO."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_KEY.sub(r"\1[redacted]", str(a)) if "key=" in str(a) else a for a in record.args)
        record.msg = _KEY.sub(r"\1[redacted]", str(record.msg))
        return True


logging.getLogger("httpx").addFilter(_RedactKey())


def bms_number(number: str) -> str:
    """BMS's documented form for a Ghanaian number is local ("0241234567"); others go as digits."""
    digits = number.lstrip("+")
    return f"0{digits[len(GHANA_CODE):]}" if digits.startswith(GHANA_CODE) else digits


@dataclass
class BmsSms:
    api_key: str
    sender: str
    budget: DailyBudget
    client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=TIMEOUT_SECONDS))
    name: str = "bms"
    delivers: bool = True  # no sandbox: whatever is accepted is sent

    def _safe(self, text: str) -> str:
        """In case BMS ever echoes the address, and so the key."""
        return _scrub(_KEY.sub(r"\1[redacted]", text.replace(self.api_key, "[redacted]")))

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, url, params={"key": self.api_key}, **kwargs)
        except httpx.HTTPError as error:  # the type only: httpx's message can carry the address, and so the key
            # No answer at all: the campaign may have been created. Told apart from a refusal so the sweep can send again.
            raise SmsUnreachable(f"BMS couldn't be reached ({type(error).__name__}).") from None
        body = _body(response)
        if response.is_error or body.get("status") != "success":
            detail = self._safe(str(body.get("message") or body or response.reason_phrase))
            raise SmsError(f"BMS refused the request ({response.status_code}): {detail}")
        return body

    def _campaign(self, text: str, to: str) -> str:
        payload = {"recipient": [bms_number(to)], "sender": self.sender, "message": text, "is_schedule": False, "schedule_date": ""}
        body = self._request("POST", SEND_URL, json=payload)
        summary = body.get("summary") if isinstance(body.get("summary"), dict) else {}
        if str(body.get("code")) != SENT or not summary.get("_id") or not summary.get("total_sent"):
            detail = self._safe(str(body.get("message") or "no campaign"))
            raise SmsError(f"BMS didn't send the message ({body.get('code')}, {summary.get('total_rejected', '?')} rejected): {detail}")
        return str(summary["_id"])

    def send(self, to: str, body: str) -> str:
        """Returns BMS's campaign ID. Raises SmsError, SmsLimitReached."""
        text = plain(body)
        count = pages(text)
        if not is_gsm7(text):
            logger.warning("An SMS goes as Unicode: %d pages instead of GSM-7's fewer", count)
        today = utc_now().date()
        self.budget.take(count, today)
        try:
            return self._campaign(text, to)
        except SmsError:
            self.budget.give_back(count, today)
            raise

    def delivery_status(self, campaign_id: str) -> str | None:
        """DELIVERED, SUBMITTED, UNDELIVERED, FAILED or REJECTED; None if no report yet."""
        body = self._request("GET", CAMPAIGN_URL.format(campaign_id=quote(campaign_id, safe="")))
        report = body.get("report") if isinstance(body.get("report"), list) else []
        statuses = [str(entry.get("status") or "").upper() for entry in report if isinstance(entry, dict)]
        return next((status for status in statuses if status), None)

    def balance(self) -> dict[str, Any]:
        """Costs nothing."""
        body = self._request("GET", BALANCE_URL)
        return {k: v for k, v in body.items() if k in ("balance", "bonus")}


def _configured() -> tuple[str, str]:
    settings = get_settings()
    if not settings.bms_api_key or not settings.bms_sender_id:
        raise SmsNotConfigured("SMS_PROVIDER=bms needs BMS_API_KEY and BMS_SENDER_ID.")
    if len(settings.bms_sender_id) > SENDER_MAX:
        raise SmsNotConfigured(f"BMS_SENDER_ID must be at most {SENDER_MAX} characters.")
    return settings.bms_api_key, settings.bms_sender_id


@lru_cache
def bms() -> BmsSms:
    api_key, sender = _configured()
    settings = get_settings()
    return BmsSms(api_key, sender, DailyBudget(lambda: get_settings().sms_daily_limit, _RedisCount() if settings.redis_url else _MemoryCount()))


@lru_cache
def bms_codes() -> BmsSms:
    """Verification codes: the same account, on their own daily limit, as Arkesel's code client is."""
    api_key, sender = _configured()
    settings = get_settings()
    counter = _RedisCount("code-pages") if settings.redis_url else _MemoryCount()
    return BmsSms(api_key, sender, DailyBudget(lambda: get_settings().sms_code_daily_limit, counter))
