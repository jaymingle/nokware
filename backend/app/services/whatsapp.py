"""WhatsApp through Twilio: sending, checking Twilio's signatures, media, and WhatsApp's 24-hour window.

Twilio signs a webhook over the exact public URL it called, so signatures are checked against PUBLIC_API_URL:
behind ngrok or a proxy the API's own URL differs.

WhatsApp allows free-form messages only within 24 hours of the citizen's last message; outside that window
notifications go by SMS instead (see notifications.py).
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
    """Broken between paragraphs, then lines, then words."""
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
        """Returns Twilio's message SID. A media message goes without text: WhatsApp drops any text sent with audio."""
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
        response = self.client.get(url, auth=(self.account_sid, self.auth_token), follow_redirects=True)
        response.raise_for_status()
        if len(response.content) > MEDIA_MAX_BYTES:
            raise WhatsAppError("The file is larger than 10 MB.")
        return response.content, response.headers.get("content-type", "")

    def delete_message(self, message_sid: str) -> None:
        url = f"{API}/Accounts/{self.account_sid}/Messages/{message_sid}.json"
        try:
            self.client.delete(url, auth=(self.account_sid, self.auth_token)).raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("Couldn't delete a WhatsApp message from Twilio's log (%s)", type(error).__name__)

    def delete_sent_media(self, message_sid: str) -> bool:
        """True once none of the message's files is left in Twilio's media store."""
        base = f"{API}/Accounts/{self.account_sid}/Messages/{message_sid}/Media"
        try:
            listed = self.client.get(f"{base}.json", auth=(self.account_sid, self.auth_token))
            if listed.status_code == 404:
                return True  # the message, and so its files, are already gone
            listed.raise_for_status()
            for media in listed.json().get("media_list", []):
                self.client.delete(f"{base}/{media['sid']}.json", auth=(self.account_sid, self.auth_token)).raise_for_status()
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("Couldn't delete a sent file from Twilio's media store (%s)", type(error).__name__)
            return False
        return True

    def delete_media(self, url: str) -> None:
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
    url, token = _public(path), get_settings().twilio_auth_token
    if not url or not token or not signature:
        return False
    return RequestValidator(token).validate(url, params, signature)


def open_window(number: str) -> None:
    try:
        get_redis().set(key("wa-window", subject_key(number)), "1", ex=WINDOW_SECONDS)
    except (redis.RedisError, RedisUnavailable):
        logger.warning("Couldn't note the WhatsApp window for %s", masked(number))


def window_open(number: str) -> bool:
    """Unknown (no Redis) counts as closed."""
    try:
        return bool(get_redis().exists(key("wa-window", subject_key(number))))
    except (redis.RedisError, RedisUnavailable):
        return False


def first_delivery(message_sid: str) -> bool:
    """Twilio may deliver a webhook twice."""
    try:
        return bool(get_redis().set(key("wa-seen", message_sid), "1", nx=True, ex=86400))
    except (redis.RedisError, RedisUnavailable):
        return True
