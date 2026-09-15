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


MESSAGES = NumberLimit("messages", limit=60, window_seconds=3600)  # every WhatsApp reply costs money
QUESTIONS = NumberLimit("questions", limit=20, window_seconds=3600)
SMS_ANSWERS = NumberLimit("sms-answers", limit=5, window_seconds=86400)  # each costs up to 2 credits
REPORTS = NumberLimit("reports", limit=5, window_seconds=3600)
LOOKUPS = NumberLimit("lookups", limit=30, window_seconds=3600)  # status by reference: no guessing
VOICE_NOTES = NumberLimit("voice-notes", limit=10, window_seconds=3600)  # each is transcribed by Gemini
SIGNATURES = NumberLimit("signatures", limit=30, window_seconds=86400)  # petitions one number signs in a day
PETITIONS = NumberLimit("petitions", limit=3, window_seconds=86400)  # started by one verified number
NUMBERS_SMS = NumberLimit("numbers-sms", limit=3, window_seconds=86400)  # emergency numbers by SMS: 2 credits each
SMS_CODES = NumberLimit("sms-codes", limit=3, window_seconds=3600)  # each verification code is an SMS credit
CODE_CLAIMS = NumberLimit("code-claims", limit=10, window_seconds=3600)  # each WhatsApp claim is answered
SPOKEN_REPLIES = NumberLimit("spoken-replies", limit=10, window_seconds=86400)  # each is an extra WhatsApp message
