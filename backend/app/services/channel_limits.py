"""Per-number limits for the messaging channels, counted in Redis.

The web's limits count per client address in the API process (rate_limit.py).
A channel message arrives from the provider's servers, so here the count is per
citizen number, under a keyed hash, in fixed windows that expire on their own.
"""

from dataclasses import dataclass

from app.services.redis_store import get_redis, key, subject_key


@dataclass(frozen=True)
class NumberLimit:
    name: str
    limit: int
    window_seconds: int

    def allow(self, number: str, now: float) -> bool:
        """Count one use by this number; False once it is over the limit for this window."""
        window = int(now // self.window_seconds)
        counter = key("limit", self.name, subject_key(number), str(window))
        pipe = get_redis().pipeline()
        pipe.incr(counter)
        pipe.expire(counter, self.window_seconds)
        used, _ = pipe.execute()
        return int(used) <= self.limit


QUESTIONS = NumberLimit("questions", limit=20, window_seconds=3600)
SMS_ANSWERS = NumberLimit("sms-answers", limit=5, window_seconds=86400)  # each costs up to 2 credits
REPORTS = NumberLimit("reports", limit=5, window_seconds=3600)
LOOKUPS = NumberLimit("lookups", limit=30, window_seconds=3600)  # status by reference: no guessing
