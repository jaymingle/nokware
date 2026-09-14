"""Redis: short-lived channel state, per-number limits and the day's SMS page count.

Everything stored here expires. Keys start "nokware:" because production shares
a Redis server with another product (on a database number of its own as well).
A phone number never appears in a key or a value: subject_key() replaces it
with a keyed hash, so Redis alone can't turn a key back into a number.
"""

import hashlib
import hmac
from functools import lru_cache

import redis

from app.config import get_settings

PREFIX = "nokware"
TIMEOUT_SECONDS = 2.0


class RedisUnavailable(RuntimeError):
    """REDIS_URL isn't set, or Redis didn't answer."""


@lru_cache
def get_redis() -> redis.Redis:
    url = get_settings().redis_url
    if not url:
        raise RedisUnavailable("REDIS_URL is not set.")
    return redis.Redis.from_url(url, decode_responses=True, socket_timeout=TIMEOUT_SECONDS, socket_connect_timeout=TIMEOUT_SECONDS)


def key(*parts: str) -> str:
    return ":".join((PREFIX, *parts))


@lru_cache
def _subject_secret() -> bytes:
    # Derived from the Appwrite API key, a server-only secret the API already
    # holds: no new setting, and rotating that key only resets what expires anyway.
    return hmac.new(get_settings().appwrite_api_key.encode(), b"nokware-channel-subjects", hashlib.sha256).digest()


def subject_key(subject: str) -> str:
    """A phone number (or a USSD session ID) as a key part: a keyed hash, never the value itself."""
    return hmac.new(_subject_secret(), subject.encode(), hashlib.sha256).hexdigest()[:32]
