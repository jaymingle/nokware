"""Where a conversation is: a USSD menu's place or a WhatsApp draft, kept in Redis until it goes quiet."""

import json
from typing import Any

from app.services.redis_store import get_redis, key, subject_key


def _key(channel: str, subject: str) -> str:
    return key("session", channel, subject_key(subject))


def load(channel: str, subject: str) -> dict[str, Any] | None:
    raw = get_redis().get(_key(channel, subject))
    return json.loads(raw) if isinstance(raw, str) else None


def save(channel: str, subject: str, state: dict[str, Any], ttl_seconds: int) -> None:
    get_redis().set(_key(channel, subject), json.dumps(state), ex=ttl_seconds)


def clear(channel: str, subject: str) -> None:
    get_redis().delete(_key(channel, subject))
