"""Proving a phone number: what a resident does before starting a petition (and, from P2, signing one).

The web page asks for a challenge and gets a six-digit code plus a secret it
keeps. The resident then proves the number one of three ways:

- WhatsApp: the page opens a chat with "Nokware code 482173" already typed;
  sending it proves the number, because Twilio says who sent it. One reply
  confirms it.
- USSD: dial the service, choose "Confirm a web code" and type the code; the
  network says who dialled.
- SMS: type the number on the page, then the code that arrives by SMS. OFF by
  default (SMS_VERIFICATION_CODES), and it stays off until the Arkesel sender
  ID is registered: an unregistered sender ID's messages are held for about 15
  minutes, and a code arriving 15 minutes late is worse than no SMS option.
  Codes have a daily cap of their own (sms.code_sms).

Only Ghanaian mobile numbers qualify. Once proven, the page collects a proof: a
sealed token (AES-GCM, under a key only the server holds) carrying the number,
how it was proven and when it expires. The browser can't read it or change it.
So no phone number is ever in Redis, which holds only the challenge's code,
its state and, once proven, the sealed proof.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Any
from urllib.parse import quote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings
from app.services import channel_limits
from app.services.ledger_documents import parse_datetime
from app.services.redis_store import get_redis, key
from app.services.report_contacts import InvalidNumber, masked, normalise_phone
from app.services.sms import SmsError, code_sms

logger = logging.getLogger(__name__)

CHALLENGE_SECONDS = 15 * 60
PROOF_LIFETIME = timedelta(hours=12)
CODE_DIGITS = 6
SMS_ATTEMPTS = 5
_TYPED_CODE = re.compile(r"^\s*(?:nokware\s+)?code\W*([0-9]{3})[\s-]?([0-9]{3})\W*$", re.IGNORECASE)
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


class Channel(StrEnum):
    WHATSAPP = "whatsapp"
    USSD = "ussd"
    SMS = "sms"


class Claim(StrEnum):
    PROVEN = "proven"
    NOT_GHANAIAN = "not_ghanaian"
    UNKNOWN = "unknown"  # no challenge is waiting for that code: mistyped, used, or expired


class ProofError(Exception):
    """The proof or challenge can't be used; the message is safe to show."""

    status_code = 401


class SmsUnavailable(ProofError):
    status_code = 409


@dataclass(frozen=True)
class Challenge:
    secret: str
    code: str
    expires_in: int


@dataclass(frozen=True)
class Proof:
    number: str
    channel: Channel
    expires_at: datetime

    @property
    def hint(self) -> str:
        return masked(self.number)


@dataclass(frozen=True)
class ChallengeState:
    state: str  # waiting, proven or expired
    proof: str | None = None


@lru_cache
def _sealing_key() -> bytes:
    return hmac.new(get_settings().appwrite_api_key.encode(), b"nokware-phone-proofs", hashlib.sha256).digest()


def _seal(payload: dict[str, Any]) -> str:
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(_sealing_key()).encrypt(nonce, json.dumps(payload).encode(), b"phone-proof")
    return base64.urlsafe_b64encode(nonce + sealed).decode().rstrip("=")


def _unseal(token: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        return dict(json.loads(AESGCM(_sealing_key()).decrypt(raw[:12], raw[12:], b"phone-proof")))
    except (ValueError, InvalidTag, TypeError):
        raise ProofError("Confirm your phone number again.") from None


def issue_proof(number: str, channel: Channel, now: datetime) -> str:
    return _seal({"number": number, "channel": channel.value, "expires": (now + PROOF_LIFETIME).isoformat()})


def open_proof(token: str | None, now: datetime) -> Proof:
    """The number a proof carries, or ProofError if it's missing, altered or expired."""
    if not token:
        raise ProofError("Confirm your phone number first.")
    payload = _unseal(token)
    expires = parse_datetime(payload.get("expires"))
    if expires is None or expires <= now:
        raise ProofError("Your confirmation has expired. Confirm your phone number again.")
    return Proof(payload["number"], Channel(payload["channel"]), expires)


@lru_cache
def _phone_secret() -> bytes:
    configured = get_settings().phone_key_secret
    return configured.encode() if configured else hmac.new(
        get_settings().appwrite_api_key.encode(), b"nokware-verified-phones", hashlib.sha256).digest()


def phone_key(number: str) -> str:
    """A verified number as stored: a keyed hash, never the number, so it can be matched but not read back."""
    return hmac.new(_phone_secret(), number.encode(), hashlib.sha256).hexdigest()


def _challenge_key(secret: str) -> str:
    return key("phone", "challenge", hashlib.sha256(secret.encode()).hexdigest()[:32])


def _code_key(code: str) -> str:
    return key("phone", "code", code)


def new_challenge() -> Challenge:
    """A fresh code no other waiting challenge holds, and the secret the page keeps."""
    redis, secret = get_redis(), secrets.token_urlsafe(24)
    for _ in range(10):
        code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        if redis.set(_code_key(code), _challenge_key(secret), nx=True, ex=CHALLENGE_SECONDS):
            redis.hset(_challenge_key(secret), mapping={"state": "waiting", "code": code})
            redis.expire(_challenge_key(secret), CHALLENGE_SECONDS)
            return Challenge(secret, code, CHALLENGE_SECONDS)
    raise RuntimeError("No free verification code; try again.")


def _waiting(secret: str) -> dict[str, str]:
    if not _TOKEN.match(secret):
        raise ProofError("That confirmation has expired. Start again.")
    held = get_redis().hgetall(_challenge_key(secret))
    if not held:
        raise ProofError("That confirmation has expired. Start again.")
    return held


def _prove(challenge_key: str, code: str, number: str, channel: Channel, now: datetime) -> None:
    redis = get_redis()
    redis.hset(challenge_key, mapping={"state": "proven", "proof": issue_proof(number, channel, now)})
    redis.hdel(challenge_key, "sms")
    redis.delete(_code_key(code))  # a code proves one number, once


def claim(sent: str, raw_number: str, channel: Channel, now: datetime) -> Claim:
    """A code sent by WhatsApp or typed in USSD, from the number the provider vouches for."""
    code = "".join(ch for ch in sent if ch.isdigit())
    challenge_key = get_redis().get(_code_key(code)) if len(code) == CODE_DIGITS else None
    if not challenge_key or get_redis().hget(challenge_key, "state") != "waiting":
        return Claim.UNKNOWN
    try:
        number = normalise_phone(raw_number)
    except InvalidNumber:
        return Claim.NOT_GHANAIAN
    _prove(challenge_key, code, number, channel, now)
    logger.info("A phone number was confirmed by %s: %s", channel.value, masked(number))
    return Claim.PROVEN


def typed_code(text: str) -> str | None:
    """The code in a WhatsApp message such as "Nokware code 482173", or None if it isn't one."""
    match = _TYPED_CODE.match(text or "")
    return match.group(1) + match.group(2) if match else None


def state(secret: str) -> ChallengeState:
    """What the page polls for: still waiting, or proven with the proof to keep."""
    try:
        held = _waiting(secret)
    except ProofError:
        return ChallengeState("expired")
    return ChallengeState(held["state"], held.get("proof"))


def _sms_code_hash(secret: str, code: str) -> str:
    return hmac.new(_sealing_key(), f"{secret}:{code}".encode(), hashlib.sha256).hexdigest()


def sms_available() -> bool:
    return get_settings().sms_verification_codes


def send_sms_code(secret: str, raw_number: str, now: datetime) -> str:
    """Text a code to the number typed on the page. Returns the masked number it went to."""
    if not sms_available():
        raise SmsUnavailable("Confirming by SMS isn't available yet. Use WhatsApp or USSD.")
    held, number = _waiting(secret), normalise_phone(raw_number)  # InvalidNumber for anything not Ghanaian
    if held["state"] != "waiting":
        raise ProofError("This number is already confirmed.")
    if not channel_limits.SMS_CODES.allow(number, now.timestamp()):
        raise SmsUnavailable("Too many codes for this number. Try again in an hour, or use WhatsApp or USSD.")
    code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
    sealed = _seal({"number": number, "code": _sms_code_hash(secret, code)})
    get_redis().hset(_challenge_key(secret), mapping={"sms": sealed, "attempts": 0})
    _text_code(number, code)
    return masked(number)


def _text_code(number: str, code: str) -> None:
    body = f"Your Nokware code is {code}. It lasts 15 minutes. Don't share it."
    if get_settings().sms_provider != "arkesel":
        logger.warning("SMS code for %s not sent (SMS_PROVIDER isn't arkesel): %s", masked(number), code)
        return
    try:
        code_sms().send(number, body)
    except SmsError as error:
        raise SmsUnavailable(f"The code couldn't be sent: {error}") from None


def confirm_sms_code(secret: str, typed: str, now: datetime) -> ChallengeState:
    held = _waiting(secret)
    if held["state"] != "waiting" or "sms" not in held:
        raise ProofError("Ask for a code first.")
    attempts = get_redis().hincrby(_challenge_key(secret), "attempts", 1)
    sent = _unseal(held["sms"])
    code = "".join(ch for ch in typed if ch.isdigit())
    if attempts > SMS_ATTEMPTS:
        raise ProofError("Too many wrong codes. Start again.")
    if not hmac.compare_digest(sent["code"], _sms_code_hash(secret, code)):
        raise ProofError(f"That isn't the code. {SMS_ATTEMPTS - attempts} tries left.")
    _prove(_challenge_key(secret), held["code"], sent["number"], Channel.SMS, now)
    return state(secret)


def _whatsapp_number() -> str:
    return get_settings().twilio_whatsapp_from.removeprefix("whatsapp:").lstrip("+")


def whatsapp_available() -> bool:
    return _whatsapp_number().isdigit()


def whatsapp_link(code: str) -> str | None:
    """A link that opens WhatsApp with the code message typed, to Nokware's number; None without one."""
    return f"https://wa.me/{_whatsapp_number()}?text={quote(f'Nokware code {code}')}" if whatsapp_available() else None


def ussd_code() -> str | None:
    """The code to dial, when USSD is on and the code is set."""
    settings = get_settings()
    return settings.ussd_service_code if settings.arkesel_ussd_token and settings.ussd_service_code else None


CLAIM_REPLIES = {
    Claim.PROVEN: "Your number is confirmed for Nokware. Go back to the page to carry on.",
    Claim.NOT_GHANAIAN: "Petitions on Nokware are for Ghanaian mobile numbers (+233) only, so this number can't be used.",
    Claim.UNKNOWN: "That code isn't one we're waiting for, or it has expired: codes last 15 minutes. Get a new one on the page.",
}
