"""WhatsApp through Twilio: sending, checking Twilio's signatures, media, and WhatsApp's 24-hour window.

A message is a POST to Twilio's Messages API (form fields From, To, Body and,
when the API has a public address, StatusCallback). A reply longer than
WhatsApp's 1,600 characters goes as several messages, split between paragraphs.

Twilio signs every webhook with X-Twilio-Signature over the exact public URL it
called and the form fields; Twilio's own RequestValidator checks it, against
PUBLIC_API_URL (behind ngrok or a proxy the API's own URL differs).

WhatsApp allows free-form messages only within 24 hours of the citizen's last
message. Each inbound message opens that window in Redis (for a little under
24 hours, to be safe); outside it, notifications go by SMS instead (see
notifications.py). Incoming photos are fetched once and then deleted from Twilio.
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache

import httpx
import redis
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.services.redis_store import RedisUnavailable, get_redis, key, subject_key
from app.services.report_contacts import masked

logger = logging.getLogger(__name__)

API = "https://api.twilio.com/2010-04-01"
BODY_MAX = 1600
TIMEOUT_SECONDS = 15.0
MEDIA_MAX_BYTES = 10 * 1024 * 1024
WINDOW_SECONDS = 24 * 3600 - 15 * 60  # WhatsApp's 24 hours, less a margin
WEBHOOK_PATH = "/api/channels/whatsapp"
STATUS_PATH = "/api/channels/whatsapp/status"


class WhatsAppError(RuntimeError):
    """Twilio refused the message or couldn't be reached. The text is safe to store."""


class WhatsAppNotConfigured(RuntimeError):
    """WHATSAPP_PROVIDER=twilio without the settings it needs."""


def split(text: str, limit: int = BODY_MAX) -> list[str]:
    """Text in pieces of at most limit characters, broken between paragraphs, then lines, then words."""
    pieces: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind("\n\n"), window.rfind("\n")) if "\n" in window else -1
        cut = cut if cut > limit // 2 else window.rfind(" ")
        cut = cut if cut > 0 else limit
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return [*pieces, rest] if rest else pieces


@dataclass
class TwilioWhatsApp:
    account_sid: str
    auth_token: str
    sender: str  # "whatsapp:+14155238886"
    status_callback: str | None = None
    client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=TIMEOUT_SECONDS))
    name: str = "twilio"
    delivers: bool = True

    def send(self, to: str, body: str, media_url: str | None = None) -> str:
        """Send one WhatsApp message, or a file Twilio fetches from media_url (WhatsApp drops any text sent with
        audio, so a voice note goes without it); return Twilio's message SID. Raises WhatsAppError."""
        form = {"From": self.sender, "To": f"whatsapp:{to}", **({"MediaUrl": media_url} if media_url else {"Body": body[:BODY_MAX]})}
        if self.status_callback:
            form["StatusCallback"] = self.status_callback
        try:
            response = self.client.post(f"{API}/Accounts/{self.account_sid}/Messages.json", data=form, auth=(self.account_sid, self.auth_token))
        except httpx.HTTPError as error:
            raise WhatsAppError(f"Twilio couldn't be reached ({type(error).__name__}).") from None
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.is_error:
            raise WhatsAppError(f"Twilio refused the message ({response.status_code}, code {payload.get('code')}): {payload.get('message', '')[:200]}")
        return str(payload.get("sid", ""))

    def download(self, url: str) -> tuple[bytes, str]:
        """An incoming media file and its content type (Twilio's link redirects to storage)."""
        response = self.client.get(url, auth=(self.account_sid, self.auth_token), follow_redirects=True)
        response.raise_for_status()
        if len(response.content) > MEDIA_MAX_BYTES:
            raise WhatsAppError("The file is larger than 10 MB.")
        return response.content, response.headers.get("content-type", "")

    def delete_message(self, message_sid: str) -> None:
        """Remove an incoming message from Twilio's log (one that carried a location). Logged, not raised, on failure."""
        url = f"{API}/Accounts/{self.account_sid}/Messages/{message_sid}.json"
        try:
            self.client.delete(url, auth=(self.account_sid, self.auth_token)).raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("Couldn't delete a WhatsApp message from Twilio's log (%s)", type(error).__name__)

    def delete_media(self, url: str) -> None:
        """Remove an incoming file from Twilio once it has been used. A failure is logged, not raised."""
        try:
            self.client.delete(url, auth=(self.account_sid, self.auth_token)).raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("Couldn't delete a WhatsApp media file from Twilio (%s)", type(error).__name__)


def _public(path: str) -> str | None:
    base = get_settings().public_api_url
    return f"{base.rstrip('/')}{path}" if base else None


@lru_cache
def twilio() -> TwilioWhatsApp:
    settings = get_settings()
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_from):
        raise WhatsAppNotConfigured("WHATSAPP_PROVIDER=twilio needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM.")
    if not settings.twilio_whatsapp_from.startswith("whatsapp:+"):
        raise WhatsAppNotConfigured("TWILIO_WHATSAPP_FROM must look like whatsapp:+14155238886.")
    return TwilioWhatsApp(settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_from, _public(STATUS_PATH))


def signed_by_twilio(path: str, params: dict[str, str], signature: str) -> bool:
    """True only for a webhook Twilio signed for this public URL with this account's token."""
    url, token = _public(path), get_settings().twilio_auth_token
    if not url or not token or not signature:
        return False
    return RequestValidator(token).validate(url, params, signature)


def open_window(number: str) -> None:
    """The citizen just wrote: free-form messages to them are allowed for the next 24 hours."""
    try:
        get_redis().set(key("wa-window", subject_key(number)), "1", ex=WINDOW_SECONDS)
    except (redis.RedisError, RedisUnavailable):
        logger.warning("Couldn't note the WhatsApp window for %s", masked(number))


def window_open(number: str) -> bool:
    """Whether a free-form message can reach them now. Unknown (no Redis) counts as closed."""
    try:
        return bool(get_redis().exists(key("wa-window", subject_key(number))))
    except (redis.RedisError, RedisUnavailable):
        return False


def first_delivery(message_sid: str) -> bool:
    """False if this webhook was already handled (Twilio may deliver one twice)."""
    try:
        return bool(get_redis().set(key("wa-seen", message_sid), "1", nx=True, ex=86400))
    except (redis.RedisError, RedisUnavailable):
        return True
